# CloudFormation Template Drift Checker (GitHub vs CFN)

## 概要
**GitHub で管理している CloudFormation テンプレート**と  
**実際に AWS CloudFormation スタックに登録されているテンプレート**を定期的に比較し、  
**意味的に差分がある場合に通知する**ためのシステム

CloudFormation の運用方針として、

> 「CloudFormation スタックは GitHub Actions の CI/CD 経由でのみデプロイされるべき」

という前提を守れているかを継続的にチェックすることが目的

---

## システムの目的
- GitHub Actions 以外（手動 CLI / コンソール）で  
  スタックが更新されると **GitHub と実環境で乖離が発生**
- AWS Config の Drift Detection は  
  - スタック作成時テンプレと実リソースの差分検知は可能  
  - GitHub上のテンプレ との一致までは保証しない
- そのため **「GitHub 上のテンプレと完全に一致しているか」**を  
  別途チェックする必要がある

---

## 全体構成
```
EventBridge Scheduler
        |
        v
    CodeBuild
        |
        |-- GitHub テンプレ取得
        |-- CFN スタックテンプレ取得
        |-- canonical JSON に正規化
        |-- 意味的差分を比較
        v
        S3（結果保存）
        |
        v
      Lambda
        |
        v
       SNS（メール通知）
```

---

## 処理フロー
1. **EventBridge Scheduler**
   - 定期的に CodeBuild を起動

2. **CodeBuild**
   - GitHub リポジトリを clone
   - 指定されたテンプレート一覧を読み込み
   - 各テンプレートに対応する CloudFormation スタックのテンプレを取得
   - 両者を **canonical JSON（意味的に同一な構造）** に変換
   - 一致 / 不一致を判定
   - 結果を S3 に保存

3. **S3**
   - 比較結果（`_meta.json`）
   - GitHub / CFN の canonical JSON を保存

4. **Lambda**
   - S3 上の結果を読み取り
   - 差分（equal=false）がある場合のみ SNS 通知

5. **SNS**
   - メールで差分テンプレート一覧を通知

---

## 「意味的に一致」で比較している理由
この仕組みでは **テンプレートの完全なテキスト一致ではなく、意味的な一致**を比較している

理由は以下の通り：

- 空白・改行・インデント・キー順は CloudFormation の意味に影響しない
- CFN の `get-template` では  
  - YAML / JSON / 内部構造に変換されて返る場合があり  
  - テキスト完全一致は現実的でない
- 検知したいのは  
  - リソース追加・削除  
  - プロパティ追加・削除  
  - 値の変更  
  といった **デプロイ結果が変わる差分**

---

## チェック対象のテンプレート指定
以下の環境変数で制御

| 変数名 | 説明 |
|------|------|
| `GITHUB_BRANCH` | 環境名（例: develop / main） |
| `TEMPLATE_LIST` | チェック対象のテンプレートパス（カンマ区切り） |
| `STACK_PREFIX` | CloudFormation スタック名の prefix |
| `S3_BUCKET` | 結果保存用 S3 バケット |
| `S3_PREFIX` | S3 上の保存 prefix |

### スタック名の対応ルール
```
<STACK_PREFIX>-<ENV>-<テンプレ名(拡張子除外)>
```

---

## 差分確認方法（手動）
```bash
aws s3 cp s3://<bucket>/<prefix>/github/s3-lifecycle.json - > /tmp/gh.json
aws s3 cp s3://<bucket>/<prefix>/cfn/s3-lifecycle.json - > /tmp/cfn.json
diff -u /tmp/gh.json /tmp/cfn.json | less
```

---

## 通知例（SNS）
```
CloudFormation テンプレート差分検知（canonical JSON 比較）

Repo: Saxon-Pi/aws-drift-checker
Branch/Env: develop

DIFF:
- s3-lifecycle.yaml
- s3-versioning.yaml
```

---
