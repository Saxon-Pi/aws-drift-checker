# CloudFormation Drift Checker (AWS Config + SNS + Scheduler)

AWS Config のマネージドルール  
`CLOUDFORMATION_STACK_DRIFT_DETECTION_CHECK` を用いたドリフト検出・通知システム

- CloudFormation スタックの **ドリフトを自動検知**
- **即時通知**（ドリフト発生時 ※ Config の周期によってタイミングは変化）
- **定時通知**（平日10時にドリフトが残っていれば毎回通知）

---

## 全体構成

システムは **2つの CloudFormation スタック**で構成されている

### ① Drift Detector Stack（親スタック）
- AWS Config マネージドルール作成
- EventBridge（Compliance Change）
- SNS 通知
- IAM（Config 用ロール）

→ **「ドリフトが発生した瞬間」を検知して通知**

### ② Drift Reminder Stack（子スタック）
- EventBridge Scheduler（平日10:00 JST）
- Lambda
- ①のスタックの Outputs を Import して使用

→ **「ドリフトが残っている間、毎日通知」**

---

## 前提条件

- 対象リージョンで **AWS Config が有効化されていること**
  - Configuration Recorder: 有効
  - Delivery Channel: 設定済み
- 記録対象リソースに `AWS::CloudFormation::Stack` が含まれていること

> AWS Config の有効化は **コンソール or CLI で事前に実施**すること  
>（この構成では AWS Config 自体は CloudFormation で作成しない）

---

## スタック①：Drift Detector Stack

### 役割
- CloudFormation スタックのドリフト検知
- **COMPLIANT → NON_COMPLIANT に変化した瞬間**を通知

### 主なリソース
- `AWS::Config::ConfigRule`
  - `CLOUDFORMATION_STACK_DRIFT_DETECTION_CHECK`
- `AWS::Events::Rule`
  - Config Rules Compliance Change
- `AWS::SNS::Topic`

### Outputs（Export あり）
このスタックは以下を **Export** する：

- `<StackName>-ConfigRuleName`
- `<StackName>-SnsTopicArn`

※ `<StackName>` は CloudFormation のスタック名そのものを指す

---

## スタック②：Drift Reminder Stack（定時通知）

### 役割
- 平日10:00（JST）に実行
- Config ルールをチェック
- **NON_COMPLIANT のスタックがあれば毎回通知**

### 特徴
- 親スタックの Outputs を **ImportValue** で自動取得
- ConfigRuleName / SNS ARN を **手入力しない**
- StackName ベースで安全に連携

---

## デプロイ手順

### ① 親スタックをデプロイ

```bash
aws cloudformation deploy \
  --stack-name drift-checker-aws-config \
  --template-file drift-detector.yaml \
  --capabilities CAPABILITY_NAMED_IAM
```

※ SNS のメール購読が届くので Confirm subscription すること

### ② 子スタックをデプロイ（ParentStackName を指定）
```bash
aws cloudformation deploy \
  --stack-name drift-checker-daily-reminder \
  --template-file drift-reminder.yaml \
  --parameter-overrides ParentStackName=drift-checker-aws-config \
  --capabilities CAPABILITY_NAMED_IAM
```
→ ParentStackName には ① で指定した CloudFormation スタック名をそのまま指定すること  

---

## 通知の種類

### 即時通知（既存）
**トリガー：**  
COMPLIANT → NON_COMPLIANT  

**手段：**  
AWS Config → EventBridge → SNS  

**特徴：**  
ドリフトが発生した瞬間だけ通知  

### 定時通知（追加）
**トリガー：**  
平日 10:00（Asia/Tokyo）  

**手段：**  
EventBridge Scheduler → Lambda → SNS  

**特徴：**  
ドリフトが残っている間、毎回通知  

---
