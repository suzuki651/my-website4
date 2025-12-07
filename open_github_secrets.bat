@echo off
echo ========================================
echo GitHub Secrets 設定ページを開きます
echo ========================================
echo.
echo ブラウザでGitHub Secretsページが開きます。
echo SECRETS_VALUES.txt を参照して設定してください。
echo.
pause

start https://github.com/suzuki651/my-website4/settings/secrets/actions

echo.
echo ========================================
echo Azure Portal も開きますか？ (Y/N)
echo ========================================
set /p OPEN_AZURE="発行プロファイル取得のため (Y/N): "

if /i "%OPEN_AZURE%"=="Y" (
    echo Azure Portal を開きます...
    start https://portal.azure.com/#@/resource/subscriptions/YOUR_SUBSCRIPTION_ID/resourceGroups/YOUR_RESOURCE_GROUP/providers/Microsoft.Web/sites/tmsystem/publishprofile
) else (
    echo Azure Portalは開きませんでした。
    echo 必要な場合は https://portal.azure.com にアクセスし、
    echo App Services → tmsystem → 発行プロファイルの取得 をクリックしてください。
)

echo.
echo ========================================
echo 設定ファイルを開きますか？ (Y/N)
echo ========================================
set /p OPEN_FILE="SECRETS_VALUES.txt を開く (Y/N): "

if /i "%OPEN_FILE%"=="Y" (
    notepad SECRETS_VALUES.txt
)

echo.
echo 設定完了後、GitHubで以下を確認してください:
echo https://github.com/suzuki651/my-website4/actions
echo.
pause
