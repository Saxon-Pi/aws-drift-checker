import os
import json
import pathlib
import hashlib
import datetime
import subprocess
from cfn_flip import load_yaml

# ===== env =====
TEMPLATE_LIST = [t.strip() for t in os.environ["TEMPLATE_LIST"].split(",") if t.strip()]
ENV = os.environ["GITHUB_BRANCH"]
STACK_PREFIX = os.environ["STACK_PREFIX"]
S3_BUCKET = os.environ["S3_BUCKET"]
S3_PREFIX = os.environ["S3_PREFIX"]

# ===== paths =====
OUT_ROOT = pathlib.Path("/tmp/out")
GH_DIR = OUT_ROOT / "github"
CFN_DIR = OUT_ROOT / "cfn"
GH_DIR.mkdir(parents=True, exist_ok=True)
CFN_DIR.mkdir(parents=True, exist_ok=True)

def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def stack_name_from_template(tpath: str) -> str:
    base = tpath.split("/")[-1]
    name = base.rsplit(".", 1)[0]
    return f"{STACK_PREFIX}-{ENV}-{name}"

def get_cfn_template(stack_name: str):
    cmd = ["aws", "cloudformation", "get-template", "--stack-name", stack_name, "--output", "json"]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"get-template failed for {stack_name}: {p.stderr.strip()}")

    data = json.loads(p.stdout)
    body = data.get("TemplateBody")

    # TemplateBody が dict ならそのまま返す
    if isinstance(body, dict):
        return body

    # TemplateBody が str の場合：
    # - JSON文字列なら JSON として読む
    # - YAML文字列なら cfn_flip で読む（!Ref なども解釈される）
    if isinstance(body, str):
        body = body.strip()
        try:
            return json.loads(body)
        except Exception:
            return load_yaml(body)

    raise RuntimeError(f"Unexpected TemplateBody type: {type(body)}")

meta = {
    "checkedAtUtc": datetime.datetime.utcnow().isoformat() + "Z",
    "branch": ENV,
    "items": []
}

for tpath in TEMPLATE_LIST:
    stack = stack_name_from_template(tpath)
    base = tpath.split("/")[-1]
    name = base.rsplit(".", 1)[0]

    # GitHub template
    with open(tpath, "r", encoding="utf-8") as f:
        gh_obj = load_yaml(f.read())
    gh_canon = canonical_json(gh_obj)
    (GH_DIR / f"{name}.json").write_text(gh_canon + "\n", encoding="utf-8")

    # CFN template
    cfn_obj = get_cfn_template(stack)
    cfn_canon = canonical_json(cfn_obj)  # 文字列分岐は消す
    (CFN_DIR / f"{name}.json").write_text(cfn_canon + "\n", encoding="utf-8")

    meta["items"].append({
        "template": tpath,
        "stack": stack,
        "equal": gh_canon == cfn_canon,
        "githubSha256": hashlib.sha256(gh_canon.encode()).hexdigest(),
        "cfnSha256": hashlib.sha256(cfn_canon.encode()).hexdigest()
    })

# meta.json
(OUT_ROOT / "_meta.json").write_text(
    json.dumps(meta, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

# upload to S3
subprocess.run(
    ["aws", "s3", "cp", str(OUT_ROOT / "_meta.json"), f"s3://{S3_BUCKET}/{S3_PREFIX}_meta.json"],
    check=True
)
subprocess.run(
    ["aws", "s3", "cp", str(GH_DIR), f"s3://{S3_BUCKET}/{S3_PREFIX}github/", "--recursive"],
    check=True
)
subprocess.run(
    ["aws", "s3", "cp", str(CFN_DIR), f"s3://{S3_BUCKET}/{S3_PREFIX}cfn/", "--recursive"],
    check=True
)

print("✔ GitHub vs CloudFormation template comparison completed")
