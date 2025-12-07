# 勤怠管理システム


QRコード対応のWebベース勤怠管理システム


## 主な機能

### 打刻機能
- **QRコード打刻**: カメラでQRコードをスキャンして打刻
- **手動打刻**: 従業員IDを入力して打刻
- **音声ガイダンス**: 各アクションに対応した音声案内
- **写真記録**: 打刻時の写真撮影・保存
- **整合性チェック**: 不正な打刻順序の検出とエラー表示

### 管理機能
- **従業員管理**: 従業員の追加・削除・編集
- **QRコード生成**: 従業員ごとのQRコード自動生成
- **勤怠記録表示**: 日別・月別の勤怠データ表示
- **データエクスポート**: CSV・Excel形式での出力
- **パスワード管理**: 管理者パスワードの変更・リセット

### 自動機能
- **自動休憩時間**: 出勤時に3回の休憩時間を自動登録
  - 08:15-08:30 (朝休憩)
  - 12:00-13:00 (昼休憩)  
  - 15:15-15:30 (夕休憩)
- **勤務時間計算**: 休憩時間を除いた実働時間の自動計算

## 技術仕様

- **フレームワーク**: Flask (Python)
- **データベース**: SQLite
- **フロントエンド**: HTML5, JavaScript, CSS
- **QRコード**: html5-qrcode ライブラリ
- **エクスポート**: pandas, openpyxl
- **認証**: Flask-Login
- **メール送信**: SMTP (Gmail対応)

## セットアップ

### 1. 依存関係のインストール
```bash
pip install -r requirements.txt
```

### 2. 環境変数の設定
`.env` ファイルを作成し、以下を設定：
```bash
SECRET_KEY=your_secure_random_key
EMAIL_USERNAME=your-gmail@gmail.com
EMAIL_PASSWORD=your-gmail-app-password
ADMIN_EMAIL=suzuki651iris1@gmail.com
```

### 3. アプリケーション起動
```bash
python app.py
```

### 4. アクセス
- 管理画面: http://localhost:5000/admin
- モバイル打刻: http://localhost:5000/mobile

## 初期設定

### デフォルトログイン情報
- ユーザー名: `admin`
- パスワード: `admin_password`

### テスト用従業員
- 従業員ID: `TEST001`
- 氏名: テスト太郎
- QRコード: http://localhost:5000/qr/TEST001

## 使用方法

### 従業員の打刻手順
1. モバイル画面にアクセス
2. 打刻アクション（出勤・退勤・退出・戻り）を選択
3. QRコードをスキャンまたは従業員IDを手動入力
4. 音声ガイダンスで完了確認

### 管理者の操作手順
1. 管理画面にログイン
2. 従業員管理で新規従業員を追加
3. QRコードを生成・印刷
4. 勤怠記録を日別・月別で確認
5. 必要に応じてデータをエクスポート

## ディレクトリ構造

```
timecard_system/
├── app.py                    # メインアプリケーション
├── requirements.txt          # 依存関係
├── .env                     # 環境変数設定
├── templates/               # HTMLテンプレート
│   ├── admin.html          # 管理画面
│   ├── mobile.html         # モバイル打刻画面
│   └── reset_password.html # パスワードリセット画面
└── static/                 # 静的ファイル
    ├── qrcodes/           # QRコード画像
    └── photos/            # 打刻写真
```

## API エンドポイント

### 打刻関連
- `POST /api/timecard` - QRコード打刻
- `POST /api/timecard/manual` - 手動打刻
- `POST /api/timecard/check-consistency` - 整合性チェック
- `GET /api/timecard/daily-summary` - 日別サマリー
- `GET /api/timecard/detail` - 詳細記録取得

### 従業員管理
- `GET /api/employees` - 従業員一覧取得
- `POST /api/employees` - 従業員追加
- `DELETE /api/employees/{id}` - 従業員削除

### エクスポート
- `GET /api/employees/export-csv` - 従業員CSV出力
- `GET /api/employees/export-excel` - 従業員Excel出力
- `GET /api/timecard/export-excel` - 勤怠Excel出力
- `GET /api/timecard/monthly-report-excel` - 月次レポート

## セキュリティ

- パスワードハッシュ化 (SHA256)
- セッション管理 (Flask-Login)
- 環境変数による機密情報管理
- CSRF保護対応

## トラブルシューティング

### 手動打刻エラー
- ネットワーク接続を確認
- 従業員IDが正しいか確認
- 打刻順序（出勤→退勤）を確認

### メール送信失敗
- Gmail アプリパスワードが正しいか確認
- 2段階認証が有効になっているか確認
- 環境変数が正しく設定されているか確認

### QRコード読み取り失敗
- カメラ権限が許可されているか確認
- QRコードが鮮明に印刷されているか確認
- 照明が十分か確認

## ライセンス

このプロジェクトはMITライセンスの下で公開されています。

## 貢献

バグ報告や機能要求は、GitHubのIssueでお知らせください。

## 更新履歴

### v1.0.0 (2024-01-15)
- 初回リリース
- QRコード打刻機能
- 手動打刻機能
- 管理画面

- データエクスポート機能