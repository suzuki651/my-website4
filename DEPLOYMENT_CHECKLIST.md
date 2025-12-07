# 🚀 デプロイメント チェックリスト

このチェックリストに従って、Azure App ServiceへのGitHub Actions自動デプロイを設定してください。

## ✅ 事前準備

- [x] ローカル開発環境で動作確認済み
- [x] GitHubリポジトリ作成済み (https://github.com/suzuki651/my-website4)
- [x] Azure App Service作成済み (tmsystem)
- [x] `.gitignore` で `.env` が除外されている
- [x] GitHub Actions ワークフローファイル作成済み (`.github/workflows/azure-deploy.yml`)

## 📋 GitHub Secrets 設定（全8個）

### アプリケーション環境変数（7個）

- [ ] **SECRET_KEY** を追加
  - 値: `c9ddd3522cbcc3cffd4d1b1f254d7f079373ce4f93eecec6642690d8493b41c8`

- [ ] **FLASK_ENV** を追加
  - 値: `production`

- [ ] **SMTP_SERVER** を追加
  - 値: `smtp.gmail.com`

- [ ] **SMTP_PORT** を追加
  - 値: `587`

- [ ] **EMAIL_USERNAME** を追加
  - 値: `suzuki651iris1@gmail.com`

- [ ] **EMAIL_PASSWORD** を追加
  - 値: `fznzjqvafwrpnmkv`

- [ ] **ADMIN_EMAIL** を追加
  - 値: `suzuki651iris1@gmail.com`

### Azure デプロイ認証情報（1個）

- [ ] **AZURE_WEBAPP_PUBLISH_PROFILE** を追加
  - 値: Azure Portalから取得した発行プロファイル

## 🔧 設定手順

### 1. GitHub Secrets設定ページを開く

```
https://github.com/suzuki651/my-website4/settings/secrets/actions
```

または、`open_github_secrets.bat` をダブルクリック

### 2. 各Secretを追加

`SECRETS_VALUES.txt` を参照しながら、1つずつ追加：

1. **「New repository secret」** をクリック
2. **Name** に Secret名を入力
3. **Secret** に値を貼り付け
4. **「Add secret」** をクリック
5. 次のSecretも同様に追加

### 3. Azure発行プロファイルを取得

1. https://portal.azure.com にアクセス
2. App Services → tmsystem を選択
3. 「発行プロファイルの取得」をクリック
4. ダウンロードした `.PublishSettings` ファイルをメモ帳で開く
5. ファイル全体の内容をコピー
6. GitHub Secrets に `AZURE_WEBAPP_PUBLISH_PROFILE` として追加

### 4. 設定確認

すべてのSecretsが追加されたか確認：

```
https://github.com/suzuki651/my-website4/settings/secrets/actions
```

以下の8つが表示されているはず：

- ADMIN_EMAIL
- AZURE_WEBAPP_PUBLISH_PROFILE
- EMAIL_PASSWORD
- EMAIL_USERNAME
- FLASK_ENV
- SECRET_KEY
- SMTP_PORT
- SMTP_SERVER

## 🚀 デプロイ実行

### 自動デプロイのトリガー

Secretsが設定されると、次回の`main`ブランチへのプッシュ時に自動的にデプロイが開始されます。

または、手動でトリガー：

1. https://github.com/suzuki651/my-website4/actions にアクセス
2. 「Deploy to Azure App Service」ワークフローを選択
3. 「Run workflow」をクリック

### デプロイ状況の監視

```
https://github.com/suzuki651/my-website4/actions
```

- 🟡 黄色のアイコン: 実行中
- 🟢 緑色のチェックマーク: 成功
- 🔴 赤色のバツマーク: 失敗

## ✅ デプロイ後の確認

### 1. アプリケーションにアクセス

```
https://tmsystem.azurewebsites.net
```

### 2. 管理画面にログイン

```
https://tmsystem.azurewebsites.net/admin/login
```

### 3. Azure App Service のログ確認

1. Azure Portal → tmsystem → ログストリーム
2. 以下のメッセージが表示されているか確認：

```
勤怠管理システム - Azure App Service版を起動しています...
データベース初期化完了
システム起動完了！
```

### 4. 環境変数の確認

Azure Portal → tmsystem → 環境変数（または構成）

以下の7つが設定されているか確認：

- SECRET_KEY
- FLASK_ENV
- SMTP_SERVER
- SMTP_PORT
- EMAIL_USERNAME
- EMAIL_PASSWORD
- ADMIN_EMAIL

## 🐛 トラブルシューティング

### デプロイが失敗する場合

#### 1. GitHub Actions のログを確認

```
https://github.com/suzuki651/my-website4/actions
```

失敗したワークフローをクリックして、エラーメッセージを確認

#### 2. よくあるエラーと対処法

**エラー: "The subscription is not registered to use namespace 'Microsoft.Web'"**
- Azure サブスクリプションでWeb Appsが有効になっているか確認

**エラー: "Publish profile is invalid"**
- 発行プロファイルを再度ダウンロードして設定

**エラー: "SECRET_KEY is not set"**
- GitHub Secretsが正しく設定されているか確認
- Secretの値にスペースや改行が含まれていないか確認

### アプリケーションにアクセスできない場合

#### 1. Azure App Service が起動しているか確認

Azure Portal → tmsystem → 概要

**状態**: 実行中 ✓

#### 2. ログを確認

Azure Portal → tmsystem → ログストリーム

エラーメッセージがないか確認

#### 3. 環境変数が設定されているか確認

Azure Portal → tmsystem → 環境変数

7つの環境変数が正しく設定されているか確認

## 📞 サポート

問題が解決しない場合は、以下のリンクからサポートを受けてください：

- GitHub Issues: https://github.com/suzuki651/my-website4/issues
- Azure サポート: https://portal.azure.com/#blade/Microsoft_Azure_Support/HelpAndSupportBlade

## 🎉 完了！

すべてのチェックが完了したら、以下が実現されています：

✅ GitHubにコードをプッシュするだけで自動デプロイ
✅ 環境変数はGitHub Secretsで安全に管理
✅ Azure App Serviceで本番環境が稼働
✅ メール機能が正常に動作

---

**最終更新**: 2025-01-07
**バージョン**: 1.0
