# Azure App Service 環境変数設定スクリプト

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Azure App Service 環境変数 自動設定" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 設定値
$appName = "tmsystem"
$settings = @{
    "SECRET_KEY" = "c9ddd3522cbcc3cffd4d1b1f254d7f079373ce4f93eecec6642690d8493b41c8"
    "FLASK_ENV" = "production"
    "SMTP_SERVER" = "smtp.gmail.com"
    "SMTP_PORT" = "587"
    "EMAIL_USERNAME" = "suzuki651iris1@gmail.com"
    "EMAIL_PASSWORD" = "fznzjqvafwrpnmkv"
    "ADMIN_EMAIL" = "suzuki651iris1@gmail.com"
}

Write-Host "App Service名: $appName" -ForegroundColor Yellow
Write-Host ""
Write-Host "設定する環境変数:" -ForegroundColor Yellow
foreach ($key in $settings.Keys) {
    $value = $settings[$key]
    if ($key -eq "SECRET_KEY" -or $key -eq "EMAIL_PASSWORD") {
        $maskedValue = $value.Substring(0, 8) + "..." + $value.Substring($value.Length - 8)
        Write-Host "  $key = $maskedValue" -ForegroundColor Green
    } else {
        Write-Host "  $key = $value" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "設定方法を選択してください:" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. Azure CLI で自動設定（推奨）" -ForegroundColor Green
Write-Host "2. Azure Portal を開いて手動設定" -ForegroundColor Yellow
Write-Host "3. 設定値をクリップボードにコピー" -ForegroundColor Yellow
Write-Host ""

$choice = Read-Host "選択してください (1/2/3)"

switch ($choice) {
    "1" {
        Write-Host ""
        Write-Host "Azure CLI で設定します..." -ForegroundColor Green
        Write-Host ""

        # Azure CLIがインストールされているか確認
        try {
            $azVersion = az --version 2>&1
            Write-Host "Azure CLI が見つかりました" -ForegroundColor Green

            Write-Host ""
            Write-Host "Azureにログインします..." -ForegroundColor Yellow
            az login

            Write-Host ""
            Write-Host "環境変数を設定しています..." -ForegroundColor Yellow

            # App Service設定を構築
            $settingsJson = @()
            foreach ($key in $settings.Keys) {
                $settingsJson += "$key=$($settings[$key])"
            }

            # リソースグループを検索
            Write-Host "App Serviceを検索中..." -ForegroundColor Yellow
            $webApp = az webapp list --query "[?name=='$appName']" | ConvertFrom-Json

            if ($webApp.Count -eq 0) {
                Write-Host "エラー: App Service '$appName' が見つかりません" -ForegroundColor Red
                Write-Host "Azure Portalで手動設定してください" -ForegroundColor Yellow
                Start-Process "https://portal.azure.com"
            } else {
                $resourceGroup = $webApp[0].resourceGroup
                Write-Host "リソースグループ: $resourceGroup" -ForegroundColor Green

                # 環境変数を設定
                az webapp config appsettings set --name $appName --resource-group $resourceGroup --settings $settingsJson

                Write-Host ""
                Write-Host "✓ 環境変数の設定が完了しました！" -ForegroundColor Green
                Write-Host ""
                Write-Host "確認URL: https://portal.azure.com/#@/resource/subscriptions/.../providers/Microsoft.Web/sites/$appName/configuration" -ForegroundColor Cyan
            }

        } catch {
            Write-Host "エラー: Azure CLI がインストールされていません" -ForegroundColor Red
            Write-Host ""
            Write-Host "以下のURLからインストールしてください:" -ForegroundColor Yellow
            Write-Host "https://learn.microsoft.com/ja-jp/cli/azure/install-azure-cli-windows" -ForegroundColor Cyan
            Write-Host ""
            Write-Host "または、オプション2で手動設定してください" -ForegroundColor Yellow
        }
    }

    "2" {
        Write-Host ""
        Write-Host "Azure Portal を開きます..." -ForegroundColor Green
        Write-Host ""

        # Azure Portalの構成ページを開く
        $portalUrl = "https://portal.azure.com/#view/Microsoft_Azure_WwwExtension/WebsiteConfigurationBlade/resourceId/%2Fsubscriptions%2F%2FresourceGroups%2F%2Fproviders%2FMicrosoft.Web%2Fsites%2F$appName"
        Start-Process $portalUrl

        Write-Host "設定手順:" -ForegroundColor Yellow
        Write-Host "1. Azure Portalにログイン" -ForegroundColor White
        Write-Host "2. App Services → $appName を選択" -ForegroundColor White
        Write-Host "3. 左メニュー「環境変数」または「構成」をクリック" -ForegroundColor White
        Write-Host "4. 「アプリケーション設定」タブを選択" -ForegroundColor White
        Write-Host "5. 「+ 新しいアプリケーション設定」をクリック" -ForegroundColor White
        Write-Host ""
        Write-Host "以下の7つの設定を追加:" -ForegroundColor Yellow
        Write-Host ""

        foreach ($key in $settings.Keys) {
            $value = $settings[$key]
            Write-Host "名前: $key" -ForegroundColor Cyan
            Write-Host "値: $value" -ForegroundColor Green
            Write-Host ""
        }

        Write-Host "6. 最後に「保存」をクリック" -ForegroundColor White
        Write-Host "7. アプリが自動的に再起動されます" -ForegroundColor White
        Write-Host ""

        # SECRETS_VALUES.txt も開く
        $secretsFile = Join-Path $PSScriptRoot "SECRETS_VALUES.txt"
        if (Test-Path $secretsFile) {
            notepad $secretsFile
        }
    }

    "3" {
        Write-Host ""
        Write-Host "設定値をクリップボードにコピーしました" -ForegroundColor Green
        Write-Host ""

        $clipboardText = @"
Azure App Service 環境変数設定

App Service名: $appName

SECRET_KEY=$($settings['SECRET_KEY'])
FLASK_ENV=$($settings['FLASK_ENV'])
SMTP_SERVER=$($settings['SMTP_SERVER'])
SMTP_PORT=$($settings['SMTP_PORT'])
EMAIL_USERNAME=$($settings['EMAIL_USERNAME'])
EMAIL_PASSWORD=$($settings['EMAIL_PASSWORD'])
ADMIN_EMAIL=$($settings['ADMIN_EMAIL'])
"@

        Set-Clipboard -Value $clipboardText
        Write-Host "クリップボードの内容:" -ForegroundColor Yellow
        Write-Host $clipboardText
        Write-Host ""
        Write-Host "Azure Portal で手動設定してください" -ForegroundColor Yellow
        Start-Process "https://portal.azure.com"
    }

    default {
        Write-Host "無効な選択です" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "次のステップ:" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. Azure App Service の環境変数設定 ← 今ここ" -ForegroundColor Yellow
Write-Host "2. GitHub Secrets の設定" -ForegroundColor White
Write-Host "3. GitHub Actions でデプロイ" -ForegroundColor White
Write-Host ""
Write-Host "GitHub Secrets設定は以下のファイルを参照:" -ForegroundColor Yellow
Write-Host "  - SETUP_GITHUB_SECRETS.md" -ForegroundColor Cyan
Write-Host "  - SECRETS_VALUES.txt" -ForegroundColor Cyan
Write-Host ""

Read-Host "Enterキーを押して終了"
