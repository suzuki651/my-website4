# GitHub Secrets 設定ガイド

このガイドに従って、GitHub ActionsでAzure App Serviceにデプロイするための環境変数を設定してください。

## 🔐 設定が必要なSecrets

以下の8つのSecretsをGitHubリポジトリに追加してください。

### 1. アプリケーション環境変数（7つ）

| Secret名 | 値 | 説明 |
|---------|-----|------|
| `SECRET_KEY` | `c9ddd3522cbcc3cffd4d1b1f254d7f079373ce4f93eecec6642690d8493b41c8` | セッション暗号化キー |
| `FLASK_ENV` | `production` | Flask環境設定 |
| `SMTP_SERVER` | `smtp.gmail.com` | SMTPサーバー |
| `SMTP_PORT` | `587` | SMTPポート |
| `EMAIL_USERNAME` | `suzuki651iris1@gmail.com` | メール送信元アドレス |
| `EMAIL_PASSWORD` | `fznzjqvafwrpnmkv` | Gmailアプリパスワード |
| `ADMIN_EMAIL` | `suzuki651iris1@gmail.com` | 管理者メールアドレス |

### 2. Azure デプロイ認証情報（1つ）

| Secret名 | 値の取得方法 |
|---------|------------|
| `AZURE_WEBAPP_PUBLISH_PROFILE` | 下記の手順で取得 |

## 📝 設定手順

### ステップ1: GitHub Secretsページにアクセス

1. ブラウザで以下のURLを開く：
   ```
   https://github.com/suzuki651/my-website4/settings/secrets/actions
   ```

2. ログインを求められた場合はログイン

### ステップ2: 環境変数Secretsを追加（7つ）

各Secretを1つずつ追加します：

#### 2-1. SECRET_KEY

1. **「New repository secret」** をクリック
2. **Name**: `SECRET_KEY`
3. **Secret**: `c9ddd3522cbcc3cffd4d1b1f254d7f079373ce4f93eecec6642690d8493b41c8`
4. **「Add secret」** をクリック

#### 2-2. FLASK_ENV

1. **「New repository secret」** をクリック
2. **Name**: `FLASK_ENV`
3. **Secret**: `production`
4. **「Add secret」** をクリック

#### 2-3. SMTP_SERVER

1. **「New repository secret」** をクリック
2. **Name**: `SMTP_SERVER`
3. **Secret**: `smtp.gmail.com`
4. **「Add secret」** をクリック

#### 2-4. SMTP_PORT

1. **「New repository secret」** をクリック
2. **Name**: `SMTP_PORT`
3. **Secret**: `587`
4. **「Add secret」** をクリック

#### 2-5. EMAIL_USERNAME

1. **「New repository secret」** をクリック
2. **Name**: `EMAIL_USERNAME`
3. **Secret**: `suzuki651iris1@gmail.com`
4. **「Add secret」** をクリック

#### 2-6. EMAIL_PASSWORD

1. **「New repository secret」** をクリック
2. **Name**: `EMAIL_PASSWORD`
3. **Secret**: `fznzjqvafwrpnmkv`
4. **「Add secret」** をクリック

#### 2-7. ADMIN_EMAIL

1. **「New repository secret」** をクリック
2. **Name**: `ADMIN_EMAIL`
3. **Secret**: `suzuki651iris1@gmail.com`
4. **「Add secret」** をクリック

### ステップ3: Azure発行プロファイルを取得

#### 3-1. Azure Portalにアクセス

1. https://portal.azure.com にアクセス
2. **App Services** をクリック
3. **tmsystem** を選択

#### 3-2. 発行プロファイルをダウンロード

1. 上部メニューから **「発行プロファイルの取得」** をクリック
2. `tmsystem.PublishSettings` ファイルがダウンロードされます

#### 3-3. ファイルの内容をコピー

1. ダウンロードした `tmsystem.PublishSettings` をメモ帳で開く
2. **ファイル全体の内容をコピー**（Ctrl+A → Ctrl+C）

#### 3-4. GitHub Secretに追加

1. GitHubのSecretsページに戻る
2. **「New repository secret」** をクリック
3. **Name**: `AZURE_WEBAPP_PUBLISH_PROFILE`
4. **Secret**: コピーした発行プロファイルの内容を貼り付け
5. **「Add secret」** をクリック

### ステップ4: 設定確認

すべてのSecretsが追加されたら、以下の8つが表示されているか確認：

- ✅ ADMIN_EMAIL
- ✅ AZURE_WEBAPP_PUBLISH_PROFILE
- ✅ EMAIL_PASSWORD
- ✅ EMAIL_USERNAME
- ✅ FLASK_ENV
- ✅ SECRET_KEY
- ✅ SMTP_PORT
- ✅ SMTP_SERVER

## 🚀 デプロイの実行

Secretsの設定が完了すると、自動的にGitHub Actionsがトリガーされ、Azureへのデプロイが開始されます。

### デプロイ状況の確認

1. https://github.com/suzuki651/my-website4/actions にアクセス
2. 最新のワークフロー実行を確認
3. 緑色のチェックマークが表示されたら成功

### デプロイ後の確認

1. https://tmsystem.azurewebsites.net にアクセス
2. アプリケーションが正常に動作しているか確認

## ⚠️ トラブルシューティング

### デプロイが失敗した場合

1. **GitHub Actions のログを確認**
   - https://github.com/suzuki651/my-website4/actions
   - 失敗したワークフローをクリック
   - エラーメッセージを確認

2. **Secretsの値を再確認**
   - スペースや改行が入っていないか
   - コピー&ペーストが正確か

3. **Azure App Service のログを確認**
   - Azure Portal → tmsystem → ログストリーム

### よくあるエラー

#### エラー: "SECRET_KEY is not set"

- `SECRET_KEY` Secretが正しく設定されているか確認
- 値にスペースが含まれていないか確認

#### エラー: "AZURE_WEBAPP_PUBLISH_PROFILE invalid"

- 発行プロファイルの内容を再度コピー
- ファイル全体（XML形式）がコピーされているか確認

#### エラー: "App Service not found"

- Azure App Serviceの名前が `tmsystem` で正しいか確認
- Azure サブスクリプションが有効か確認

## 📞 サポート

問題が解決しない場合は、以下の情報を添えてお問い合わせください：

- GitHub Actions のエラーログ
- Azure App Service のログ
- 実行したステップ

---

**最終更新**: 2025-01-07
