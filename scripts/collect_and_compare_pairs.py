import os
import json
import hashlib
import datetime
import subprocess
import pathlib
from cfn_flip import load_yaml
from botocore.exceptions import ClientError

# ===== env =====
GIT_BRANCH = os.environ.get("GIT_BRANCH", "")
PAIRS_JSON_PATH = os.environ["PAIRS_JSON_PATH"]          # repo path
SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]
STACK_NAME_LABEL = os.environ.get("STACK_NAME_LABEL", "")  # optional (CloudFormation stack name label)

def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def load_pairs(repo_path: str):
    p = pathlib.Path(repo_path)
    if not p.exists():
        raise RuntimeError(f"Pairs JSON not found: {repo_path}")

    text = p.read_text(encoding="utf-8").strip()
    pairs = json.loads(text)

    if not isinstance(pairs, list):
        raise RuntimeError("Pairs JSON must be a JSON array")

    # validate
    for idx, pair in enumerate(pairs, start=1):
        if not isinstance(pair, dict):
            raise RuntimeError(f"Pairs JSON item #{idx} must be an object")
        if not pair.get("GithubPath") or not pair.get("StackName"):
            raise RuntimeError(f"Pairs JSON item #{idx} requires GithubPath and StackName")

    return pairs

def get_cfn_template(stack_name: str):
    """
    Fetch template body from CloudFormation and normalize to Python object.
    - TemplateBody may be dict (rare) or string (JSON or YAML)
    """
    cmd = ["aws", "cloudformation", "get-template", "--stack-name", stack_name, "--output", "json"]
    p = subprocess.run(cmd, capture_output=True, text=True)

    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or f"get-template failed: {stack_name}")

    data = json.loads(p.stdout)
    body = data.get("TemplateBody")

    if isinstance(body, dict):
        return body

    if isinstance(body, str):
        body = body.strip()
        # Try JSON string
        try:
            return json.loads(body)
        except Exception:
            # YAML string (supports !Ref, !Sub etc. via cfn_flip)
            return load_yaml(body)

    raise RuntimeError(f"Unexpected TemplateBody type: {type(body)}")

def load_github_template(path_in_repo: str):
    """
    Load a template file in repo, support YAML or JSON.
    """
    p = pathlib.Path(path_in_repo)
    if not p.exists():
        raise RuntimeError(f"GitHub template not found in repo: {path_in_repo}")

    text = p.read_text(encoding="utf-8").strip()

    # If it's JSON
    if text.startswith("{") or text.startswith("["):
        try:
            return json.loads(text)
        except Exception:
            pass

    # Otherwise treat as YAML
    return load_yaml(text)

def sns_publish(subject: str, message: str):
    cmd = [
        "aws", "sns", "publish",
        "--topic-arn", SNS_TOPIC_ARN,
        "--subject", subject,
        "--message", message
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or "sns publish failed")

def main():
    pairs = load_pairs(PAIRS_JSON_PATH)

    checked_at = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat()

    results = []
    diffs = []
    errors = []

    for pair in pairs:
        gh_path = pair["GithubPath"]
        stack_name = pair["StackName"]

        try:
            gh_obj = load_github_template(gh_path)
            gh_canon = canonical_json(gh_obj)

            cfn_obj = get_cfn_template(stack_name)
            cfn_canon = canonical_json(cfn_obj)

            equal = (gh_canon == cfn_canon)

            item = {
                "status": "ok",
                "githubPath": gh_path,
                "stackName": stack_name,
                "equal": equal,
                "githubSha256": sha256(gh_canon),
                "cfnSha256": sha256(cfn_canon),
            }
            results.append(item)

            if not equal:
                diffs.append(item)

        except Exception as e:
            item = {
                "status": "error",
                "githubPath": gh_path,
                "stackName": stack_name,
                "equal": False,
                "error": str(e)[:500],
            }
            results.append(item)
            errors.append(item)

    # ---- Output to logs (CodeBuild logs will keep it)
    meta = {
        "checkedAtUtc": checked_at,
        "branch": GIT_BRANCH,
        "stackNameLabel": STACK_NAME_LABEL,
        "diffCount": len(diffs),
        "errorCount": len(errors),
        "items": results,
    }
    print(json.dumps(meta, ensure_ascii=False, indent=2))

    # ---- Notify only when diffs/errors exist
    if not diffs and not errors:
        print("✔ No diffs/errors. (No notification)")
        return

    lines = []
    lines.append("CloudFormation テンプレート差分検知（canonical JSON 比較）")
    lines.append(f"CheckedAt(UTC): {checked_at}")
    if STACK_NAME_LABEL:
        lines.append(f"SystemStack: {STACK_NAME_LABEL}")
    if GIT_BRANCH:
        lines.append(f"Branch: {GIT_BRANCH}")
    lines.append("")

    if diffs:
        lines.append(f"DIFF: {len(diffs)}")
        for i, d in enumerate(diffs, start=1):
            lines.append(f"{i}. github={d['githubPath']}  stack={d['stackName']}")
        lines.append("")

    if errors:
        lines.append(f"ERROR: {len(errors)}")
        for i, e in enumerate(errors, start=1):
            lines.append(f"{i}. github={e['githubPath']}  stack={e['stackName']}  err={e.get('error')}")
        lines.append("")

    subject = f"[CFN Template Diff] {GIT_BRANCH or 'branch'} diffs={len(diffs)} errors={len(errors)}"
    sns_publish(subject=subject, message="\n".join(lines))

    print("✔ Notification published to SNS")

if __name__ == "__main__":
    main()
