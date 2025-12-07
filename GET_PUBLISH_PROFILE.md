# 発行プロファイルの取得手順

## エラーの原因

「基本認証は無効になっています」というエラーは、Azure App Serviceの発行プロファイルが無効化されているか、基本認証が無効になっている場合に発生します。

## 解決方法: 基本認証を有効化

### 方法1: Azure Portal で有効化（推奨）

1. **Azure Portal を開く**
   ```
   https://portal.azure.com
   ```

2. **App Service を選択**
   - **App Services** をクリック
   - **tmsystem** を選択

3. **基本認証を有効化**
   - 左メニューから **「構成」** をクリック
   - **「全般設定」** タブを選択
   - **「基本認証」** セクションを探す
   - **「SCM基本認証」** を **「オン」** に変更
   - **「保存」** をクリック

4. **発行プロファイルをダウンロード**
   - 上部メニューから **「発行プロファイルの取得」** をクリック
   - `tmsystem.PublishSettings` ファイルがダウンロードされます

5. **ファイルの内容をコピー**
   - ダウンロードした `tmsystem.PublishSettings` をメモ帳で開く
   - **ファイル全体の内容をコピー**（Ctrl+A → Ctrl+C）

6. **GitHub Secrets に設定**
   - https://github.com/suzuki651/my-website4/settings/secrets/actions を開く
   - 既存の `AZURE_WEBAPP_PUBLISH_PROFILE` を削除（あれば）
   - **「New repository secret」** をクリック
   - **Name**: `AZURE_WEBAPP_PUBLISH_PROFILE`
   - **Secret**: コピーした内容を貼り付け
   - **「Add secret」** をクリック

### 方法2: Azure CLI で有効化

PowerShellまたはコマンドプロンプトで以下を実行：

```powershell
# Azure にログイン
az login

# 基本認証を有効化
az resource update --ids /subscriptions/{subscription-id}/resourceGroups/{resource-group}/providers/Microsoft.Web/sites/tmsystem/basicPublishingCredentialsPolicies/scm --set properties.allow=true

# 発行プロファイルを取得
az webapp deployment list-publishing-profiles --name tmsystem --resource-group {resource-group} --xml
```

出力された XML をコピーして、GitHub Secrets に設定してください。

## 代替方法: GitHub Actions で Azure にログイン

基本認証を使わず、サービスプリンシパルを使用する方法もあります。

### サービスプリンシパルの作成

1. **Azure CLI でサービスプリンシパルを作成**

```bash
az ad sp create-for-rbac --name "myApp" --role contributor \
    --scopes /subscriptions/{subscription-id}/resourceGroups/{resource-group} \
    --sdk-auth
```

2. **出力されたJSONをコピー**

出力例：
```json
{
  "clientId": "xxx",
  "clientSecret": "xxx",
  "subscriptionId": "xxx",
  "tenantId": "xxx",
  ...
}
```

3. **GitHub Secrets に追加**

- **Name**: `AZURE_CREDENTIALS`
- **Secret**: コピーしたJSON全体

4. **ワークフローファイルを更新**

`.github/workflows/azure-deploy.yml` を以下のように変更：

```yaml
- name: Login to Azure
  uses: azure/login@v1
  with:
    creds: ${{ secrets.AZURE_CREDENTIALS }}

- name: Deploy to Azure Web App
  uses: azure/webapps-deploy@v2
  with:
    app-name: 'tmsystem'
    package: .
```

## トラブルシューティング

### エラー: "基本認証は無効になっています"

**原因**: Azure App Service の基本認証が無効化されている

**解決策**:
1. Azure Portal → App Services → tmsystem → 構成 → 全般設定
2. 「SCM基本認証」を「オン」に変更
3. 保存

### エラー: "発行プロファイルが無効です"

**原因**: 古い発行プロファイルを使用している

**解決策**:
1. 新しい発行プロファイルを再度ダウンロード
2. GitHub Secrets を更新

### エラー: "サブスクリプションが見つかりません"

**原因**: Azure サブスクリプションが無効または権限がない

**解決策**:
1. Azure Portal で有効なサブスクリプションがあるか確認
2. App Service へのアクセス権限があるか確認

## 確認

設定後、以下を確認してください：

1. **GitHub Actions が実行される**
   ```
   https://github.com/suzuki651/my-website4/actions
   ```

2. **デプロイが成功する**
   - 緑色のチェックマークが表示されればOK

3. **アプリケーションにアクセス**
   ```
   https://tmsystem.azurewebsites.net
   ```

---

**最終更新**: 2025-01-07
