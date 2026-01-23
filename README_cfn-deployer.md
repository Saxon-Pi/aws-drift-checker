# CloudFormation ChangeSet Deployer (CodeBuild)

GitHub 上の CloudFormation テンプレートを **CodeBuild 単体**で取得し、  
**変更セット（ChangeSet）の作成まで**を行うデプロイ基盤  
※ 変更セットの実行（ExecuteChangeSet）は **人手／別プロセス**で行う  

---

## Code

- ./cfn-deploy-codebuild.yml  

---

## 構成概要

```
GitHub (private repo)
   ↑  (Deploy Key / SSH)
CodeBuild
   ├─ git clone
   ├─ テンプレート探索
   ├─ StackName / params.json 自動解決
   └─ CloudFormation ChangeSet 作成
```

---

## 特徴

- ✅ CodePipeline 不要（CodeBuild 単体）
- ✅ GitHub へのアクセスは **Deploy Key**
- ✅ CREATE / UPDATE を自動判定
- ✅ テンプレ未変更時は **No changes** を成功扱い
- ✅ account / all 両パス対応
- ✅ 変更セットのみ作成（安全）

---

## リポジトリ構成例

```
cfn/
└─ templates/
   ├─ all/
   │  └─ alb/
   │     ├─ alb.yaml
   │     └─ hoge-fuga-dev-alb.params.json
   └─ account/
      └─ stg/
         └─ sns/
            ├─ sns.yaml
            └─ hoge-fuga-sns.params.json
```

---

## StackName / params.json の決定ルール

### ① Metadata.StackName がある場合
```yaml
Metadata:
  StackName: !Sub ${ProjectName}-sns
```

- StackName  
  `hoge-fuga-sns`
- params.json  
  `hoge-fuga-sns.params.json`

---

### ② Metadata.StackName がない場合
- StackName  
  `<ProjectName>-<EnvName>-<yaml名>`
- params.json  
  `<ProjectName>-<EnvName>-<yaml名>.params.json`

例：
```
hoge-fuga-dev-alb
hoge-fuga-dev-alb.params.json
```

---

## CodeBuild 環境変数

### スタック作成時（固定）

| 変数名 | 説明 |
|------|------|
| PROJECT_NAME | プロジェクト名（例: hoge-fuga） |
| ENV_NAME | 環境名（dev / dev2 / stg / prd 等、自由入力） |
| GIT_SSH_REPO | GitHub SSH URL |
| DEFAULT_GIT_REF | 対象ブランチ |
| DEPLOY_KEY_SSM_PARAM | Deploy Key を格納した SSM Parameter |

---

### ビルド実行時（必須）

| 変数名 | 説明 |
|------|------|
| TEMPLATE | テンプレート相対パス（例: all/alb/alb.yaml） |

---

## 実行例

```bash
aws codebuild start-build \
  --project-name hoge-fuga-dev-cfn-changeset-deployer \
  --environment-variables-override \
    name=TEMPLATE,value=all/alb/alb.yaml,type=PLAINTEXT
```

---

## Deploy Key 作成（CloudShell）

```bash
ssh-keygen -t ed25519 -f github-deploy-key-prd -C "codebuild-cfn-deployer-prd"
```

- `github-deploy-key-prd.pub` → GitHub に登録
- `github-deploy-key-prd` → SSM SecureString に保存

---

## SSM 登録例

```bash
aws ssm put-parameter \
  --name /cfn-deployer/github/deploykey \
  --type SecureString \
  --value "$(cat github-deploy-key-prd)" \
  --overwrite
```

---

## よくあるエラーと対処

| エラー | 原因 |
|------|------|
| Parameters must have values | params.json に不足 |
| No changes detected | テンプレ差分なし（正常） |
| Template not found | TEMPLATE パス誤り |

---

## 運用メモ

- 変更セットが `FAILED (No changes)` は **仕様通り**
- 実リソース変更は CloudFormation Console から実行
- Deploy Key は **環境ごとに分離推奨**

---
