import sqlite3
from datetime import datetime, timedelta
from typing import Any, Tuple, Optional, Dict, List
import logging
import sys
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user  # type: ignore
import qrcode  # type: ignore
import pandas as pd  # type: ignore
import io
import os
from PIL import Image
import base64
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pytz
from enum import Enum
from werkzeug.security import generate_password_hash, check_password_hash

from config import Config

# ロギング設定
logger = logging.getLogger(__name__)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# 定数定義
MAX_DAILY_PUNCH_IN = 1
MAX_DAILY_PUNCH_OUT = 1
MAX_DAILY_PERSONAL_OUT = 5
MAX_DAILY_PERSONAL_IN = 5
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB
MAX_PHOTO_SIZE = 10 * 1024 * 1024  # 10MB

# Azure App Service用の環境変数読み込み
app = Flask(__name__)
app.config.from_object(Config)

# SECRET_KEY検証
secret_key = os.environ.get('SECRET_KEY')
if not secret_key or secret_key == 'your_super_secret_key_change_in_production':
    logger.error("致命的エラー: SECRET_KEYが設定されていないか、デフォルト値のままです。")
    logger.error("本番環境では必ず安全なランダムな値を設定してください。")
    if os.environ.get('FLASK_ENV') == 'production':
        raise ValueError("本番環境ではSECRET_KEYの設定が必須です")
    else:
        logger.warning("開発環境のため、一時的なSECRET_KEYを生成します")
        secret_key = secrets.token_hex(32)

app.config['SECRET_KEY'] = secret_key

# パス設定（OSに応じて変更）
if os.name == 'posix':  # Linux/Unix (Azure)
    PERSISTENT_STORAGE_PATH = '/home'
else:  # Windows
    PERSISTENT_STORAGE_PATH = os.path.dirname(os.path.abspath(__file__))

app.config['QR_FOLDER'] = os.path.join(PERSISTENT_STORAGE_PATH, 'static', 'qrcodes')
app.config['PHOTO_FOLDER'] = os.path.join(PERSISTENT_STORAGE_PATH, 'static', 'photos')
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# 日本時間の設定
JST = pytz.timezone('Asia/Tokyo')

# メール設定（環境変数から取得）
SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))
EMAIL_USERNAME = os.environ.get('EMAIL_USERNAME', 'your-email@gmail.com')
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD', 'your-app-password')
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@example.com')

login_manager = LoginManager()
login_manager.init_app(app)  # type: ignore
login_manager.login_view = 'admin_login'  # type: ignore

# === 強化された整合性チェック機能 ===

class EmployeeState(Enum):
    """従業員の状態定義"""
    NOT_ARRIVED = "not_arrived"    # 未出勤
    WORKING = "working"            # 出勤中  
    PERSONAL_OUT = "personal_out"  # 退出中

class PunchValidator:
    """打刻の整合性チェッククラス（修正版）"""

    def __init__(self) -> None:
        self.max_daily_punch_count = {
            'in': MAX_DAILY_PUNCH_IN,
            'out': MAX_DAILY_PUNCH_OUT,
            'out_personal': MAX_DAILY_PERSONAL_OUT,
            'in_personal': MAX_DAILY_PERSONAL_IN
        }
    
    def get_employee_state(self, employee_id: str, target_date: str) -> EmployeeState:
        """従業員の現在状態を取得"""
        conn = get_db_connection()
        
        # 当日の打刻記録を時系列順で取得
        punches = conn.execute('''
            SELECT action, timestamp FROM timecard 
            WHERE employee_id = ? AND DATE(timestamp) = ?
            ORDER BY timestamp DESC
        ''', (employee_id, target_date)).fetchall()
        
        conn.close()
        
        if not punches:
            return EmployeeState.NOT_ARRIVED
        
        last_action = punches[0]['action']
        
        # 最後の打刻に基づいて状態を判定
        if last_action == 'in':
            return EmployeeState.WORKING
        elif last_action == 'out':
            return EmployeeState.NOT_ARRIVED
        elif last_action == 'out_personal':
            return EmployeeState.PERSONAL_OUT
        elif last_action == 'in_personal':
            return EmployeeState.WORKING
        elif last_action in ['break_out', 'break_in']:
            # 休憩記録は状態判定に影響しない
            for punch in punches:
                if punch['action'] in ['in', 'out', 'out_personal', 'in_personal']:
                    last_real_action = punch['action']
                    if last_real_action == 'in':
                        return EmployeeState.WORKING
                    elif last_real_action == 'out':
                        return EmployeeState.NOT_ARRIVED
                    elif last_real_action == 'out_personal':
                        return EmployeeState.PERSONAL_OUT
                    elif last_real_action == 'in_personal':
                        return EmployeeState.WORKING
                    break
            return EmployeeState.NOT_ARRIVED
        else:
            return EmployeeState.NOT_ARRIVED
    
    def validate_punch(self, employee_id: str, action: str, target_date: Optional[str] = None) -> Tuple[bool, str]:
        """総合的な打刻検証（修正版）"""
        if not target_date:
            target_date = datetime.now(JST).strftime('%Y-%m-%d')
        
        # 1. 従業員の現在状態を取得
        current_state = self.get_employee_state(employee_id, target_date)
        
        # 2. 状態に基づいて許可されるアクションチェック
        allowed_actions = self.get_allowed_actions(current_state)
        if action not in allowed_actions:
            return False, self.get_state_error_message(current_state, action)
        
        # 3. 同一アクション重複チェック（修正：出勤・退勤のみ）
        if action in ['in', 'out'] and self.is_duplicate_action(employee_id, action, target_date):
            action_names = {
                'in': '出勤', 'out': '退勤',
                'out_personal': '退出', 'in_personal': '戻り'
            }
            return False, f"{action_names[action]}は既に打刻済みです"
        
        # 4. 退勤前の戻り打刻必須チェック（新規追加）
        if action == 'out' and current_state == EmployeeState.PERSONAL_OUT:
            return False, "退出中です。先に戻り打刻を行ってから退勤してください"
        
        return True, "打刻可能です"
    
    def get_allowed_actions(self, state: EmployeeState) -> List[str]:
        """状態に基づいて許可されるアクション一覧"""
        if state == EmployeeState.NOT_ARRIVED:
            return ['in']
        elif state == EmployeeState.WORKING:
            return ['out', 'out_personal']
        elif state == EmployeeState.PERSONAL_OUT:
            return ['in_personal']  # 修正：退出中は戻りのみ許可
        else:
            return []
    
    def get_state_error_message(self, state: EmployeeState, action: str) -> str:
        """状態不整合エラーメッセージ"""
        action_names = {
            'in': '出勤', 'out': '退勤',
            'out_personal': '退出', 'in_personal': '戻り'
        }
        
        action_name = action_names.get(action, action)
        
        if state == EmployeeState.NOT_ARRIVED:
            if action in ['out', 'out_personal', 'in_personal']:
                return "まず出勤打刻を行ってください"
        elif state == EmployeeState.WORKING:
            if action == 'in':
                return "既に出勤済みです"
            elif action == 'in_personal':
                return "退出していません。先に退出打刻を行ってください"
        elif state == EmployeeState.PERSONAL_OUT:
            if action in ['in', 'out', 'out_personal']:
                if action == 'out':
                    return "退出中です。先に戻り打刻を行ってから退勤してください"
                elif action == 'in':
                    return "退出中です。戻り打刻を行ってください"
                else:
                    return "既に退出中です"
        
        return f"{action_name}は現在実行できません"
    
    def is_duplicate_action(self, employee_id: str, action: str, target_date: str) -> bool:
        """同一アクション重複チェック（修正版）"""
        conn = get_db_connection()
        
        existing_punch = conn.execute('''
            SELECT COUNT(*) as count FROM timecard 
            WHERE employee_id = ? AND DATE(timestamp) = ? AND action = ?
        ''', (employee_id, target_date, action)).fetchone()
        
        conn.close()
        
        count = existing_punch['count'] if existing_punch else 0
        return count > 0

# グローバルバリデーターインスタンス
punch_validator = PunchValidator()

# === データベース関数 ===

def get_db_connection() -> sqlite3.Connection:
    """
    データベース接続を取得（OS対応版・外部キー有効化）
    """
    # パス設定（OSに応じて変更）
    if os.name == 'posix':  # Linux/Unix (Azure)
        persistent_storage_path = '/home'
    else:  # Windows
        persistent_storage_path = os.path.dirname(os.path.abspath(__file__))

    db_path = os.path.join(persistent_storage_path, 'timecard.db')

    logger.info(f"データベース接続を試行します: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # 外部キー制約を有効化
    conn.execute("PRAGMA foreign_keys = ON")

    return conn

def send_reset_email(reset_url: str, admin_email: str) -> bool:
    """パスワードリセット用URLをメール送信"""
    try:
        if not all([EMAIL_USERNAME, EMAIL_PASSWORD, SMTP_SERVER]):
            logger.warning("メール設定が不完全です")
            return False

        if EMAIL_USERNAME == 'your-email@gmail.com' or EMAIL_PASSWORD == 'your-app-password':
            logger.warning("メール設定がデフォルト値のままです")
            return False
        
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USERNAME
        msg['To'] = admin_email
        msg['Subject'] = '勤怠管理システム - パスワードリセット'
        
        body = f"""
勤怠管理システムのパスワードリセット要求が送信されました。

以下のURLからパスワードをリセットしてください：
{reset_url}

このリンクは1時間で有効期限が切れます。

※このメールに心当たりがない場合は無視してください。

---
勤怠管理システム
        """
        
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()

        logger.info(f"パスワードリセットメールを送信しました: {admin_email}")
        return True
    except Exception as e:
        logger.error(f"メール送信エラー: {e}")
        return False

def init_db() -> None:
    """データベース初期化（修正版）"""
    conn = None
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # 従業員テーブル作成
        c.execute('''
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                factory TEXT,
                employment_type TEXT
            )
        ''')
        
        # 勤怠テーブル作成
        c.execute('''
            CREATE TABLE IF NOT EXISTS timecard (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                action TEXT NOT NULL,
                photo_path TEXT,
                location TEXT,
                break_type TEXT,
                FOREIGN KEY (employee_id) REFERENCES employees (employee_id)
            )
        ''')
        
        # ユーザーテーブル作成
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                email TEXT,
                reset_token TEXT,
                reset_token_expires TEXT
            )
        ''')
        
        # 顔データテーブル作成
        c.execute('''
            CREATE TABLE IF NOT EXISTS face_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id TEXT UNIQUE NOT NULL,
                face_descriptor TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (employee_id) REFERENCES employees (employee_id)
            )
        ''')
        
        # デフォルト管理者ユーザー作成（セキュアなパスワード）
        admin_user = c.execute("SELECT * FROM users WHERE username = 'admin'").fetchone()
        if not admin_user:
            # 初回起動時に強制的にパスワード変更が必要な一時パスワードを生成
            temp_password = secrets.token_urlsafe(16)
            hashed_password = generate_password_hash(temp_password, method='pbkdf2:sha256')
            c.execute("INSERT INTO users (username, password) VALUES (?, ?)", ('admin', hashed_password))
            logger.warning("=" * 60)
            logger.warning("デフォルト管理者ユーザーを作成しました")
            logger.warning(f"ユーザー名: admin")
            logger.warning(f"一時パスワード: {temp_password}")
            logger.warning("初回ログイン後、必ずパスワードを変更してください！")
            logger.warning("=" * 60)

        # テスト用従業員データ追加
        test_employee = c.execute("SELECT * FROM employees WHERE employee_id = 'TEST001'").fetchone()
        if not test_employee:
            c.execute("INSERT INTO employees (employee_id, name, factory, employment_type) VALUES (?, ?, ?, ?)",
                     ('TEST001', 'テスト太郎', '大野', '正社員'))
            logger.info("テスト用従業員を追加しました: TEST001")

        conn.commit()
        logger.info("データベース初期化完了")

    except Exception as e:
        logger.error(f"データベース初期化エラー: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

    # ディレクトリ作成（修正版）
    try:
        qr_folder = app.config['QR_FOLDER']
        photo_folder = app.config['PHOTO_FOLDER']

        # ディレクトリ作成とパーミッション設定
        os.makedirs(qr_folder, exist_ok=True)
        os.makedirs(photo_folder, exist_ok=True)

        # パーミッション設定（Linuxの場合）
        if os.name == 'posix':
            try:
                os.chmod(qr_folder, 0o755)
                os.chmod(photo_folder, 0o755)
            except Exception as perm_error:
                logger.warning(f"パーミッション設定エラー: {perm_error}")

        logger.info(f"必要なディレクトリを作成しました:")
        logger.info(f"  - QRフォルダ: {qr_folder}")
        logger.info(f"  - 写真フォルダ: {photo_folder}")

        # テスト用QRコード生成
        generate_qr_code('TEST001')
        logger.info("テスト用QRコードを生成しました")

    except Exception as e:
        logger.error(f"ディレクトリ作成エラー: {e}")

class User(UserMixin):
    def __init__(self, id: int) -> None:
        self.id = id
        
@login_manager.user_loader
def load_user(user_id: str) -> Optional[User]:
    conn = get_db_connection()
    user_data = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if user_data:
        return User(user_data['id'])
    return None

def generate_qr_code(employee_id: str) -> None:
    """QRコード生成"""
    img = qrcode.make(employee_id)
    qr_path = os.path.join(app.config['QR_FOLDER'], f'{employee_id}.png')
    img.save(qr_path)

def save_photo(photo_data: str, employee_id: str) -> Optional[str]:
    """写真保存機能（強化版）"""
    try:
        if not photo_data:
            return None
            
        # Base64データから画像データを抽出
        if ',' in photo_data:
            img_data = base64.b64decode(photo_data.split(',')[1])
        else:
            img_data = base64.b64decode(photo_data)
        
        # PIL Imageで画像を開く
        img = Image.open(io.BytesIO(img_data))
        
        # ファイル名生成
        now = datetime.now(JST)
        photo_filename = f"{employee_id}_{now.strftime('%Y%m%d_%H%M%S')}.jpg"
        
        # 保存ディレクトリ確認・作成
        photo_dir = app.config['PHOTO_FOLDER']
        os.makedirs(photo_dir, exist_ok=True)

        # フルパス
        full_photo_path = os.path.join(photo_dir, photo_filename)

        # 画像をJPEG形式で保存
        if img.mode in ('RGBA', 'LA', 'P'):
            # 透明度がある画像の場合は白背景で合成
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            mask = img.split()[-1] if img.mode == 'RGBA' else None
            background.paste(img, mask=mask)
            img = background

        img.save(full_photo_path, 'JPEG', quality=85)

        # 修正: データベース用の相対パスを統一
        relative_path = f"static/photos/{photo_filename}"

        logger.info(f"写真保存完了: {relative_path}")
        return relative_path

    except Exception as e:
        logger.error(f"写真保存エラー: {e}")
        return None

# === ルーティングとAPI ===

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        conn = get_db_connection()
        user_data = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()

        if user_data and check_password_hash(user_data['password'], password):
            user = User(user_data['id'])
            login_user(user)
            return redirect(url_for('admin'))
        return render_template('admin.html', login_error='ユーザー名またはパスワードが違います')
    return render_template('admin.html')

@app.route('/is_logged_in')
def is_logged_in():
    return jsonify({'is_logged_in': current_user.is_authenticated})

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('admin_login'))

@app.route('/admin')
@login_required
def admin():
    return render_template('admin.html')

@app.route('/mobile')
def mobile():
    return render_template('mobile.html')

# === パスワード関連の関数を全て削除して、以下に置き換える ===

@app.route('/admin/change-password', methods=['POST'])
@login_required
def change_password():
    """パスワード変更処理（セキュア版）"""
    data = request.json
    if not data:
        return jsonify({'success': False, 'message': '無効なリクエストです'})

    old_password = data.get('old_password')
    new_password = data.get('new_password')

    if not old_password or not new_password:
        return jsonify({'success': False, 'message': '現在のパスワードと新しいパスワードを入力してください'})

    # パスワード強度チェック
    if len(new_password) < 8:
        return jsonify({'success': False, 'message': 'パスワードは8文字以上で入力してください'})

    conn = get_db_connection()
    user_data = conn.execute("SELECT * FROM users WHERE id = ?", (current_user.id,)).fetchone()

    if not user_data or not check_password_hash(user_data['password'], old_password):
        conn.close()
        return jsonify({'success': False, 'message': '現在のパスワードが間違っています'})

    new_password_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
    conn.execute("UPDATE users SET password = ? WHERE id = ?", (new_password_hash, current_user.id))
    conn.commit()
    conn.close()

    logger.info(f"ユーザーID {current_user.id} のパスワードが変更されました")
    return jsonify({'success': True, 'message': 'パスワードを変更しました'})


@app.route('/admin/forgot-password', methods=['POST'])
def forgot_password():
    """パスワード忘れ処理（リセットURL生成・セキュア版）"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'success': False, 'message': '無効なリクエストです'}), 400

        username = data.get('username', '').strip() if data else ''

        if not username:
            return jsonify({'success': False, 'message': 'ユーザー名を入力してください'}), 400

        logger.info(f"パスワードリセット要求: {username}")
        
        conn = get_db_connection()
        user_data = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

        if not user_data:
            conn.close()
            logger.warning(f"ユーザーが見つからない: {username}")
            return jsonify({'success': False, 'message': 'ユーザーが見つかりません'}), 404

        # リセットトークン生成
        reset_token = secrets.token_urlsafe(32)
        expires_at = (datetime.now(JST) + timedelta(hours=1)).isoformat()

        conn.execute("UPDATE users SET reset_token = ?, reset_token_expires = ? WHERE id = ?",
                     (reset_token, expires_at, user_data['id']))
        conn.commit()
        conn.close()

        # リセットURLを生成
        base_url = request.host_url.rstrip('/')
        reset_url = f"{base_url}/admin/reset-password?token={reset_token}"

        logger.info(f"リセットURL生成: {reset_url}")

        # メール送信を試行
        email_sent = send_reset_email(reset_url, ADMIN_EMAIL)

        if email_sent:
            logger.info("リセットメール送信成功")
            return jsonify({
                'success': True,
                'message': 'パスワードリセット用のメールを送信しました'
            })
        else:
            # メール設定が未完了または送信失敗時は開発用URLを返す
            logger.warning("メール送信失敗、開発用URL返却")
            return jsonify({
                'success': True,
                'message': 'メール設定が未完了です。以下のURLでリセットしてください',
                'reset_url': reset_url
            })

    except Exception as e:
        logger.error(f"パスワード忘れ処理エラー: {e}")
        return jsonify({'success': False, 'message': f'サーバーエラー: {str(e)}'}), 500


@app.route('/admin/reset-password', methods=['GET', 'POST'])
def reset_password():
    """パスワードリセット処理（GET: フォーム表示, POST: パスワード更新）"""
    
    if request.method == 'GET':
        # GETリクエスト：リセットフォーム表示
        token = request.args.get('token')

        logger.info(f"パスワードリセットGETリクエスト受信。Token: {token}")

        if not token:
            logger.warning("トークンが見つかりません")
            return render_template('reset_password.html', error='無効なリセットリンクです。トークンが見つかりません。')

        # トークンの有効性確認
        conn = get_db_connection()
        user_data = conn.execute("SELECT * FROM users WHERE reset_token = ?", (token,)).fetchone()

        if not user_data:
            conn.close()
            logger.warning(f"トークンが無効: {token}")
            return render_template('reset_password.html', error='無効なトークンです。')

        try:
            # 有効期限チェック
            expires_at = datetime.fromisoformat(user_data['reset_token_expires'])
            current_time = datetime.now(JST)

            logger.info(f"トークン有効期限: {expires_at}, 現在時刻: {current_time}")

            if current_time > expires_at:
                conn.close()
                logger.warning("トークンが期限切れ")
                return render_template('reset_password.html', error='トークンが有効期限切れです。新しいリセットリンクを要求してください。')

        except Exception as e:
            conn.close()
            logger.error(f"トークン形式エラー: {e}")
            return render_template('reset_password.html', error='トークンの形式が不正です。')

        conn.close()
        logger.info("有効なトークンでリセットフォームを表示")
        return render_template('reset_password.html', token=token)
    
    else:  # POST
        # POSTリクエスト：パスワード更新処理
        try:
            data = request.get_json()

            if not data:
                logger.warning("JSONデータが見つかりません")
                return jsonify({'success': False, 'message': '無効なリクエストです'}), 400

            token = data.get('token')
            new_password = data.get('new_password')

            logger.info(f"パスワードリセットPOSTリクエスト受信。Token: {token}")

            if not token or not new_password:
                logger.warning("必要なデータが不足")
                return jsonify({'success': False, 'message': '必要な情報が不足しています'}), 400

            # パスワード強度チェック（強化版）
            if len(new_password) < 8:
                return jsonify({'success': False, 'message': 'パスワードは8文字以上で入力してください'}), 400

            if len(new_password) > 100:
                return jsonify({'success': False, 'message': 'パスワードは100文字以下で入力してください'}), 400

            conn = get_db_connection()
            user_data = conn.execute("SELECT * FROM users WHERE reset_token = ?", (token,)).fetchone()

            if not user_data:
                conn.close()
                logger.warning(f"無効なトークン: {token}")
                return jsonify({'success': False, 'message': 'トークンが無効です'}), 400

            try:
                expires_at = datetime.fromisoformat(user_data['reset_token_expires'])
                if datetime.now(JST) > expires_at:
                    conn.close()
                    logger.warning("トークンが期限切れ")
                    return jsonify({'success': False, 'message': 'トークンが有効期限切れです'}), 400
            except Exception as e:
                conn.close()
                logger.error(f"日時形式エラー: {e}")
                return jsonify({'success': False, 'message': 'トークンの形式が不正です'}), 400

            # パスワードをセキュアにハッシュ化して更新
            new_password_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
            conn.execute("UPDATE users SET password = ?, reset_token = NULL, reset_token_expires = NULL WHERE id = ?",
                         (new_password_hash, user_data['id']))
            conn.commit()
            conn.close()

            logger.info(f"パスワードリセット成功: ユーザーID {user_data['id']}")
            return jsonify({'success': True, 'message': 'パスワードをリセットしました'})

        except Exception as e:
            logger.error(f"パスワードリセット処理エラー: {e}")
            return jsonify({'success': False, 'message': f'サーバーエラーが発生しました: {str(e)}'}), 500


# エラーハンドラーの追加
@app.errorhandler(404)
def not_found_error(error: Any) -> Tuple[str, int]:
    """404エラーハンドラー"""
    logger.warning(f"404エラー: {request.url}")
    return render_template('reset_password.html',
                         error='ページが見つかりません。URLを確認してください。'), 404


@app.errorhandler(500)
def internal_error(error: Any) -> Tuple[str, int]:
    """500エラーハンドラー"""
    logger.error(f"500エラー: {error}")
    return render_template('reset_password.html',
                         error='サーバーエラーが発生しました。しばらく待ってから再度お試しください。'), 500

# === 従業員管理API ===

@app.route('/api/employees', methods=['GET'])
def get_employees():
    conn = get_db_connection()
    employees = conn.execute('SELECT * FROM employees').fetchall()
    conn.close()
    return jsonify([dict(row) for row in employees])

@app.route('/api/employees', methods=['POST'])
@login_required
def add_employee():
    data = request.json
    if not data:
        return jsonify({'success': False, 'message': '無効なリクエストデータです'})

    employee_id = data.get('employee_id')
    name = data.get('name')
    factory = data.get('factory')
    employment_type = data.get('employment_type')
    
    if not employee_id or not name:
        return jsonify({'success': False, 'message': '従業員IDと氏名は必須です'})

    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO employees (employee_id, name, factory, employment_type) VALUES (?, ?, ?, ?)",
                     (employee_id, name, factory, employment_type))
        conn.commit()
        generate_qr_code(str(employee_id))
        return jsonify({'success': True, 'message': '従業員を追加しました'})
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'message': 'この従業員IDは既に使用されています'})
    finally:
        conn.close()

@app.route('/api/employees/<int:id>', methods=['DELETE'])
@login_required
def delete_employee(id: int):
    conn = get_db_connection()
    employee = conn.execute('SELECT * FROM employees WHERE id = ?', (id,)).fetchone()
    if employee:
        conn.execute('DELETE FROM employees WHERE id = ?', (id,))
        conn.commit()
        qr_path = os.path.join(app.root_path, app.config['QR_FOLDER'], f'{employee["employee_id"]}.png')
        if os.path.exists(qr_path):
            os.remove(qr_path)
        conn.close()
        return jsonify({'success': True, 'message': '従業員を削除しました'})
    conn.close()
    return jsonify({'success': False, 'message': '従業員が見つかりません'})

@app.route('/api/employees/<int:id>/regenerate-qr', methods=['POST'])
@login_required
def regenerate_qr(id: int):
    conn = get_db_connection()
    employee = conn.execute('SELECT * FROM employees WHERE id = ?', (id,)).fetchone()
    conn.close()
    if employee:
        generate_qr_code(str(employee['employee_id']))
        return jsonify({'success': True, 'message': 'QRコードを再生成しました'})
    return jsonify({'success': False, 'message': '従業員が見つかりません'})

@app.route('/api/employees/generate-all-qr', methods=['POST'])
@login_required
def generate_all_qr():
    conn = get_db_connection()
    employees = conn.execute('SELECT employee_id FROM employees').fetchall()
    conn.close()
    for emp in employees:
        generate_qr_code(str(emp['employee_id']))
    return jsonify({'success': True, 'message': 'すべてのQRコードを生成しました'})

# === 顔認証関連API ===

@app.route('/api/face/register', methods=['POST'])
@login_required
def register_face_data():
    """顔データ登録API（写真保存対応・修正版）"""
    try:
        data = request.json
        employee_id = data.get('employee_id')
        face_descriptor = data.get('face_descriptor')
        photo_data = data.get('photo')  # 写真データを追加で受け取る
        
        if not employee_id or not face_descriptor:
            return jsonify({'success': False, 'message': '従業員IDと顔データは必須です'})
        
        # 従業員存在確認
        conn = get_db_connection()
        employee = conn.execute('SELECT * FROM employees WHERE employee_id = ?', (employee_id,)).fetchone()
        
        if not employee:
            conn.close()
            return jsonify({'success': False, 'message': '従業員が見つかりません'})
        
        # 写真保存（顔認証登録時）
        photo_path = None
        if photo_data:
            photo_path = save_photo(photo_data, employee_id)
            if photo_path:
                logger.info(f"顔認証登録時の写真を保存: {photo_path}")
        
        # 顔データを文字列として保存
        descriptor_str = ','.join(map(str, face_descriptor))
        now = datetime.now(JST).isoformat()
        
        # 既存データの更新または新規登録
        existing = conn.execute('SELECT id FROM face_data WHERE employee_id = ?', (employee_id,)).fetchone()
        
        if existing:
            conn.execute('''
                UPDATE face_data 
                SET face_descriptor = ?, updated_at = ?
                WHERE employee_id = ?
            ''', (descriptor_str, now, employee_id))
            message = f'{employee["name"]}さんの顔データを更新しました'
        else:
            conn.execute('''
                INSERT INTO face_data (employee_id, face_descriptor, created_at, updated_at)
                VALUES (?, ?, ?, ?)
            ''', (employee_id, descriptor_str, now, now))
            message = f'{employee["name"]}さんの顔データを登録しました'
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': message})
        
    except Exception as e:
        logger.error(f"顔データ登録エラー: {e}")
        return jsonify({'success': False, 'message': f'顔データ登録中にエラーが発生しました: {e}'})

@app.route('/api/face/verify', methods=['POST'])
def verify_face_data():
    """顔認証検証API"""
    try:
        data = request.json
        employee_id = data.get('employee_id')
        face_descriptor = data.get('face_descriptor', [])
        
        if not employee_id:
            return jsonify({'success': False, 'message': '従業員IDは必須です'})
        
        conn = get_db_connection()
        
        # 登録済み顔データを取得
        face_data = conn.execute('''
            SELECT face_descriptor FROM face_data WHERE employee_id = ?
        ''', (employee_id,)).fetchone()
        
        conn.close()
        
        if not face_data:
            return jsonify({
                'success': False, 
                'message': '顔データが未登録です',
                'needs_registration': True
            })
        
        # 空の face_descriptor の場合は登録データの存在確認のみ
        if not face_descriptor:
            stored_descriptor = [float(x) for x in face_data['face_descriptor'].split(',')]
            return jsonify({
                'success': True,
                'stored_descriptor': stored_descriptor
            })
        
        # 顔認証実行（実際の実装では face-api.js の距離計算を使用）
        stored_descriptor = [float(x) for x in face_data['face_descriptor'].split(',')]
        
        return jsonify({
            'success': True,
            'stored_descriptor': stored_descriptor,
            'similarity': 0.85  # プレースホルダー値
        })
        
    except Exception as e:
        logger.error(f"顔認証検証エラー: {e}")
        return jsonify({'success': False, 'message': f'顔認証検証中にエラーが発生しました: {e}'})

@app.route('/api/face/status')
@login_required
def get_face_data_status():
    """全従業員の顔データ登録状況取得API"""
    try:
        conn = get_db_connection()
        
        # 全従業員と顔データの登録状況を取得
        result = conn.execute('''
            SELECT e.employee_id, 
                   CASE WHEN f.employee_id IS NOT NULL THEN 1 ELSE 0 END as has_face_data
            FROM employees e
            LEFT JOIN face_data f ON e.employee_id = f.employee_id
        ''').fetchall()
        
        conn.close()
        
        # 辞書形式で返す
        status = {}
        for row in result:
            status[row['employee_id']] = bool(row['has_face_data'])
        
        return jsonify(status)
        
    except Exception as e:
        logger.error(f"顔データ状況取得エラー: {e}")
        return jsonify({})

# === 整合性チェックAPI ===

@app.route('/api/timecard/check-consistency', methods=['POST'])
def check_consistency():
    """強化された整合性チェックAPI"""
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'message': '無効なリクエストデータです', 'play_error_sound': True})

        employee_id = data.get('employee_id')
        action = data.get('action')
        custom_date = data.get('date')
        
        if not employee_id or not action:
            return jsonify({'success': False, 'message': '従業員IDとアクションは必須です', 'play_error_sound': True})

        conn = get_db_connection()
        employee = conn.execute('SELECT * FROM employees WHERE employee_id = ?', (employee_id,)).fetchone()
        
        if not employee:
            conn.close()
            return jsonify({'success': False, 'message': f'従業員ID {employee_id} が見つかりません', 'play_error_sound': True})
        
        # 整合性チェック実行
        is_valid, error_message = punch_validator.validate_punch(employee_id, action, custom_date)
        conn.close()
        
        if is_valid:
            return jsonify({
                'success': True,
                'message': f'{employee["name"]}さんの打刻が可能です',
                'employee_name': employee['name']
            })
        else:
            return jsonify({
                'success': False,
                'message': f'エラー: {error_message}',
                'play_error_sound': True
            })
            
    except Exception as e:
        logger.error(f"整合性チェックAPI エラー: {e}")
        return jsonify({
            'success': False,
            'message': f'システムエラー: {e}',
            'play_error_sound': True
        })

# === 打刻関連API ===

@app.route('/api/timecard/manual', methods=['POST'])
@login_required
def manual_punch():
    """手動打刻API（修正版：自動写真撮影・保存機能追加）"""
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'message': '無効なリクエストデータです'})

        employee_id = data.get('employee_id')
        action = data.get('action')
        custom_date = data.get('date')
        custom_time = data.get('time')
        photo_data = data.get('photo')  # 追加：写真データを受け取る
        
        if not employee_id or not action:
            return jsonify({'success': False, 'message': '従業員IDとアクションは必須です'})

        # 日付・時刻の処理を改善
        if custom_date and custom_time:
            try:
                # JST タイムゾーンで日時を作成
                naive_datetime = datetime.strptime(f"{custom_date} {custom_time}", '%Y-%m-%d %H:%M')
                timestamp = JST.localize(naive_datetime)
                target_date = custom_date  # 整合性チェック用の日付
                logger.info(f"手動指定時刻: {timestamp}, 対象日: {target_date}")
            except ValueError:
                return jsonify({'success': False, 'message': '日付または時刻の形式が正しくありません'})
        else:
            # 現在時刻を使用（JST）
            timestamp = datetime.now(JST)
            target_date = timestamp.strftime('%Y-%m-%d')
            logger.info(f"現在時刻使用: {timestamp}, 対象日: {target_date}")

        logger.info(f"手動打刻: employee_id={employee_id}, action={action}, time={timestamp}")

        conn = get_db_connection()
        employee = conn.execute('SELECT * FROM employees WHERE employee_id = ?', (employee_id,)).fetchone()
        if not employee:
            conn.close()
            return jsonify({
                'success': False, 
                'message': f'従業員ID {employee_id} が見つかりません',
                'voice': '従業員情報が見つかりません'
            })

        # 指定された日付で整合性チェックを実行
        is_valid, error_message = punch_validator.validate_punch(employee_id, action, target_date)
        if not is_valid:
            conn.close()
            return jsonify({
                'success': False, 
                'message': error_message,
                'voice': error_message
            })

        # 修正：写真保存処理の追加
        photo_path = None
        if photo_data:
            photo_path = save_photo(photo_data, employee_id)
            if photo_path:
                logger.info(f"手動打刻時写真保存成功: {photo_path}")
            else:
                logger.warning("手動打刻時写真保存に失敗")

        try:
            # データベースに保存する際のタイムスタンプ形式（修正版）
            timestamp_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
            
            conn.execute("""
                INSERT INTO timecard (employee_id, timestamp, action, photo_path, location)
                VALUES (?, ?, ?, ?, ?)
            """, (employee_id, timestamp_str, action, photo_path, '手動'))

            logger.info(f"打刻記録完了: {timestamp_str}, {action}")
            
            conn.commit()
            
        except Exception as e:
            conn.rollback()
            conn.close()
            logger.error(f"手動打刻データベースエラー: {e}")
            return jsonify({
                'success': False, 
                'message': f'データベースエラー: {e}'
            })
            
        conn.close()
        
        action_names = {
            'in': '出勤',
            'out': '退勤',
            'out_personal': '退出', 
            'in_personal': '戻り'
        }
        
        action_name = action_names.get(action, action)
        success_message = f'{employee["name"]}さんの{action_name}を登録しました'
        
        if custom_date and custom_time:
            success_message += f'（{custom_date} {custom_time}）'
        
        # 修正：写真保存結果をレスポンスに含める
        response_data = {
            'success': True, 
            'message': success_message,
            'employee_name': employee['name']
        }
        
        if photo_path:
            response_data['message'] += ' 📷'
            response_data['photo_saved'] = True
            response_data['photo_path'] = photo_path
        elif photo_data:
            response_data['message'] += ' (写真保存失敗)'
            response_data['photo_saved'] = False
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"手動打刻全般エラー: {e}")
        return jsonify({
            'success': False,
            'message': f'システムエラー: {e}'
        })

@app.route('/api/timecard', methods=['POST'])
def punch_timecard():
    """打刻処理 (モバイル用) - 強化された整合性チェックと顔認証時写真撮影対応（修正版）"""
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'message': '無効なリクエストデータです', 'voice': '無効なリクエストです'})

        employee_id = data.get('employee_id')
        action = data.get('action')
        photo_data = data.get('photo')
        face_verified = data.get('face_verified', False)
        face_similarity = data.get('face_similarity', 0)

        logger.info(f"打刻処理開始: employee_id={employee_id}, action={action}, face_verified={face_verified}")
        
        if not employee_id or not action:
            return jsonify({'success': False, 'message': '従業員IDとアクションは必須です', 'voice': '必要な情報が不足しています'})
        
        conn = get_db_connection()
        employee = conn.execute('SELECT * FROM employees WHERE employee_id = ?', (employee_id,)).fetchone()
        if not employee:
            conn.close()
            return jsonify({'success': False, 'message': '従業員情報が見つかりません', 'voice': '従業員情報がありません', 'play_error_sound': True})

        # 強化された打刻の整合性チェック
        is_valid, error_message = punch_validator.validate_punch(employee_id, action)
        if not is_valid:
            conn.close()
            return jsonify({
                'success': False, 
                'message': error_message, 
                'voice': error_message,
                'play_error_sound': True
            })

        # JST タイムゾーンで現在時刻を取得
        now = datetime.now(JST)
        
        # 写真保存処理（修正版）
        photo_path = None
        if photo_data:
            photo_path = save_photo(photo_data, employee_id)
            if photo_path:
                logger.info(f"打刻時写真保存成功: {photo_path}")
            else:
                logger.warning("打刻時写真保存に失敗")

        try:
            # データベースに保存
            timestamp_str = now.strftime('%Y-%m-%d %H:%M:%S')
            conn.execute("""
                INSERT INTO timecard (employee_id, timestamp, action, photo_path, location)
                VALUES (?, ?, ?, ?, ?)
            """, (employee_id, timestamp_str, action, photo_path, 'モバイル'))

            logger.info(f"打刻記録完了: {timestamp_str}, {action}")
            conn.commit()

        except Exception as e:
            conn.rollback()
            conn.close()
            logger.error(f"データベース操作エラー: {e}")
            return jsonify({'success': False, 'message': f'データベースエラー: {e}', 'voice': 'データベースエラーです', 'play_error_sound': True})
        
        conn.close()
        
        voice_messages = {
            'in': f'{employee["name"]}さん、おはようございます。出勤を記録しました',
            'out': f'{employee["name"]}さん、お疲れ様でした。退勤を記録しました',
            'out_personal': f'{employee["name"]}さん、外出を記録しました',
            'in_personal': f'{employee["name"]}さん、戻りを記録しました'
        }
        
        voice_message = voice_messages.get(action, '打刻が完了しました')
        
        response_data: Dict[str, Any] = {
            'success': True, 
            'message': '打刻が完了しました', 
            'voice': voice_message,
            'employee_name': employee['name']
        }
        
        # 修正: 写真保存結果の報告を改善
        if photo_path:
            response_data['photo_saved'] = True
            response_data['photo_path'] = photo_path
            logger.info(f"打刻時写真保存レスポンス: {photo_path}")
        else:
            response_data['photo_saved'] = False
            if photo_data:
                logger.warning("写真データはあったが保存に失敗")
            else:
                logger.debug("写真データなし")
        
        # 顔認証情報の追加
        if face_verified:
            response_data['face_verified'] = True
            response_data['face_similarity'] = face_similarity
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"打刻処理全般エラー: {e}")
        return jsonify({
            'success': False,
            'message': f'システムエラー: {e}',
            'voice': 'システムエラーが発生しました',
            'play_error_sound': True
        })

# === 勤怠記録管理API ===

@app.route('/api/timecard/update', methods=['POST'])
@login_required
def update_timecard():
    """勤怠記録更新API（修正版）"""
    data = request.json
    if not data:
        return jsonify({'success': False, 'message': '無効なリクエストデータです'})

    punch_id = data.get('id')
    new_timestamp = data.get('timestamp')
    new_action = data.get('action')
    new_break_type = data.get('break_type')

    if not all([punch_id, new_timestamp, new_action]):
        return jsonify({'success': False, 'message': 'ID、タイムスタンプ、アクションは必須です'})
    
    # タイムスタンプ形式の統一
    try:
        # フロントエンドから送られてくる形式: "YYYY-MM-DDTHH:MM"
        # データベース保存形式: "YYYY-MM-DD HH:MM:SS"
        if 'T' in new_timestamp:
            # ISO形式の場合は変換
            formatted_timestamp = new_timestamp.replace('T', ' ')
            if len(formatted_timestamp) == 16:  # "YYYY-MM-DD HH:MM" の場合
                formatted_timestamp += ':00'  # 秒を追加
        else:
            formatted_timestamp = new_timestamp

        logger.info(f"タイムスタンプ変換: {new_timestamp} -> {formatted_timestamp}")

    except Exception as e:
        logger.error(f"タイムスタンプ変換エラー: {e}")
        return jsonify({'success': False, 'message': 'タイムスタンプの形式が不正です'})
    
    conn = get_db_connection()
    try:
        # 更新実行
        conn.execute("""
            UPDATE timecard 
            SET timestamp = ?, action = ?, break_type = ? 
            WHERE id = ?
        """, (formatted_timestamp, new_action, new_break_type, punch_id))
        
        if conn.total_changes == 0:
            conn.close()
            return jsonify({'success': False, 'message': '該当する記録が見つかりませんでした'})
            
        conn.commit()
        conn.close()

        logger.info(f"打刻記録更新完了: ID={punch_id}, timestamp={formatted_timestamp}")
        return jsonify({'success': True, 'message': '打刻情報を更新しました'})

    except Exception as e:
        conn.rollback()
        conn.close()
        logger.error(f"打刻記録更新エラー: {e}")
        return jsonify({'success': False, 'message': f'更新エラー: {e}'})

@app.route('/api/timecard/delete/<int:id>', methods=['DELETE'])
@login_required
def delete_timecard(id: int):
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM timecard WHERE id = ?", (id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': '打刻情報を削除しました'})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': f'削除エラー: {e}'})

@app.route('/api/timecard/bulk-delete', methods=['POST'])
@login_required
def bulk_delete_timecard():
    data = request.json
    if not data:
        return jsonify({'success': False, 'message': '無効なリクエストデータです'})
    
    employee_id = data.get('employee_id')
    date = data.get('date')
    
    if not employee_id or not date:
        return jsonify({'success': False, 'message': '従業員IDと日付は必須です'})
    
    conn = get_db_connection()
    try:
        result = conn.execute("DELETE FROM timecard WHERE employee_id = ? AND DATE(timestamp) = ?", (employee_id, date))
        deleted_count = result.rowcount
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': f'{deleted_count}件の打刻記録を削除しました'})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': f'削除エラー: {e}'})

@app.route('/qr/<employee_id>')
def get_qr_code(employee_id: str):
    path = os.path.join(app.root_path, app.config['QR_FOLDER'], f'{employee_id}.png')
    if os.path.exists(path):
        return send_file(path, mimetype='image/png')
    return "QR code not found", 404

# 写真配信ルート（既存のserve_photo関数を置き換え）
@app.route('/static/photos/<filename>')
def serve_photo(filename: str):
    """写真ファイルの配信（セキュリティ強化版）"""
    try:
        # セキュリティ: ファイル名のサニタイズ
        filename = os.path.basename(filename)  # パストラバーサル攻撃防止
        
        # ファイル拡張子の確認
        allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif'}
        file_ext = os.path.splitext(filename)[1].lower()
        if file_ext not in allowed_extensions:
            return "Invalid file type", 400
        
        photo_path = os.path.join(app.root_path, app.config['PHOTO_FOLDER'], filename)
        
        if os.path.exists(photo_path):
            # ファイルサイズチェック (最大10MB)
            file_size = os.path.getsize(photo_path)
            if file_size > MAX_PHOTO_SIZE:
                return "File too large", 413

            return send_file(photo_path, mimetype='image/jpeg', as_attachment=False)
        else:
            logger.warning(f"写真ファイルが見つかりません: {photo_path}")
            return "Photo not found", 404
    except Exception as e:
        logger.error(f"写真配信エラー: {e}")
        return "Error serving photo", 500

# === エクスポート機能（勤務時間計算削除） ===

@app.route('/api/employees/export-csv')
@login_required
def export_employees_csv():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT employee_id, name, factory, employment_type FROM employees", conn)
    conn.close()
    
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
    csv_buffer.seek(0)
    
    return send_file(io.BytesIO(csv_buffer.getvalue().encode('utf-8-sig')),
                     mimetype='text/csv',
                     as_attachment=True,
                     download_name='employees.csv')

@app.route('/api/employees/export-excel')
@login_required
def export_employees_excel():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT employee_id, name, factory, employment_type FROM employees", conn)
    conn.close()
    
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Employees')
    excel_buffer.seek(0)
    
    return send_file(excel_buffer,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True,
                     download_name='employees.xlsx')

@app.route('/api/timecard/export-csv')
@login_required
def export_timecard_csv():
    date_str = request.args.get('date')
    conn = get_db_connection()
    
    df = pd.read_sql_query("SELECT T.timestamp, E.employee_id, E.name, T.action, T.location FROM timecard AS T JOIN employees AS E ON T.employee_id = E.employee_id WHERE T.timestamp LIKE ? ORDER BY T.timestamp", conn, params=(f'{date_str}%',))
    conn.close()
    
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
    csv_buffer.seek(0)
    
    return send_file(io.BytesIO(csv_buffer.getvalue().encode('utf-8-sig')),
                     mimetype='text/csv',
                     as_attachment=True,
                     download_name=f'timecard_{date_str}.csv')

@app.route('/api/timecard/monthly-report-excel')
@login_required
def export_monthly_report():
    year_str = request.args.get('year')
    month_str = request.args.get('month')
    if not year_str or not month_str:
        return jsonify({'error': 'Year and month are required'}), 400

    conn = get_db_connection()
    query = """
        SELECT T.timestamp, E.employee_id, E.name, T.action, T.break_type
        FROM timecard AS T
        JOIN employees AS E ON T.employee_id = E.employee_id
        WHERE SUBSTR(T.timestamp, 1, 4) = ? AND SUBSTR(T.timestamp, 6, 2) = ?
        ORDER BY E.employee_id, T.timestamp
    """
    df = pd.read_sql_query(query, conn, params=(year_str, month_str.zfill(2)))
    conn.close()

    if df.empty:
        return jsonify({'error': 'No data for this month'}), 404

    def clean_timestamp_format(ts_str):
        """ 'YYYY-MM-DD HH:MM:SS:ms' を 'YYYY-MM-DD HH:MM:SS.ms' に変換する """
        if isinstance(ts_str, str) and ts_str.count(':') > 2:
            # 文字列の最後のコロンだけをピリオドに置換する
            parts = ts_str.rpartition(':')
            return parts[0] + '.' + parts[2]
        return ts_str

    # タイムスタンプ文字列をクリーンな形式に変換
    df['timestamp'] = df['timestamp'].apply(clean_timestamp_format)

    # クリーンになった文字列をdatetimeオブジェクトに変換
    # この行は元のコードと同じですが、上記の処理の後に実行します
    df['timestamp'] = pd.to_datetime(df['timestamp'], format='mixed')
    df['date'] = df['timestamp'].dt.date
    df['time'] = df['timestamp'].dt.time

    summary_data = []
    
    for (employee_id, date), group in df.groupby(['employee_id', 'date']):
        employee_name = group.iloc[0]['name']
        
        punches = {}
        
        for _, row in group.iterrows():
            action = row['action']
            time_str = row['time'].strftime('%H:%M')
            
            if action == 'in':
                punches['出勤'] = time_str
            elif action == 'out':
                punches['退勤'] = time_str
            elif action == 'out_personal':
                punches['退出'] = time_str
            elif action == 'in_personal':  
                punches['戻り'] = time_str
        
        # 勤務時間計算機能を削除
        summary_data.append({
            '日付': date.strftime('%Y/%m/%d'),
            '曜日': ['月', '火', '水', '木', '金', '土', '日'][date.weekday()],
            '従業員ID': employee_id,
            '氏名': employee_name,
            '出勤': punches.get('出勤', ''),
            '退勤': punches.get('退勤', ''),
            '退出': punches.get('退出', ''),
            '戻り': punches.get('戻り', '')
        })

    summary_df = pd.DataFrame(summary_data)
    
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        summary_df.to_excel(writer, index=False, sheet_name=f'{year_str}年{month_str}月勤怠')
        
        worksheet = writer.sheets[f'{year_str}年{month_str}月勤怠']
        
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                if cell.value:
                    max_length = max(max_length, len(str(cell.value)))
            worksheet.column_dimensions[column_letter].width = min(max_length + 2, 50)
        
        for cell in worksheet[1]:
            from openpyxl.styles import Font, PatternFill
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color="CCCCCC", end_color="CCCCCC", fill_type="solid")
    
    excel_buffer.seek(0)

    return send_file(excel_buffer,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True,
                     download_name=f'勤怠記録_{year_str}年{month_str}月.xlsx')

@app.route('/api/timecard/export-excel')
@login_required
def export_timecard_excel():
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({'error': 'Date is required'}), 400
        
    conn = get_db_connection()
    
    query = '''
        SELECT 
            e.employee_id,
            e.name,
            MIN(CASE WHEN t.action = 'in' THEN t.timestamp END) as check_in,
            MAX(CASE WHEN t.action = 'out' THEN t.timestamp END) as check_out,
            MIN(CASE WHEN t.action = 'out_personal' THEN t.timestamp END) as exit_time,
            MAX(CASE WHEN t.action = 'in_personal' THEN t.timestamp END) as return_time
        FROM employees e
        LEFT JOIN timecard t ON e.employee_id = t.employee_id 
            AND DATE(t.timestamp) = ?
        GROUP BY e.employee_id, e.name
        ORDER BY e.employee_id
    '''
    
    df = pd.read_sql_query(query, conn, params=(date_str,))
    conn.close()
    
    formatted_data = []
    for _, row in df.iterrows():
        # 勤務時間計算機能を削除
        formatted_data.append({
            '従業員ID': row['employee_id'],
            '氏名': row['name'],
            '出勤時刻': row['check_in'][:16] if row['check_in'] else '',
            '退勤時刻': row['check_out'][:16] if row['check_out'] else '',
            '退出時刻': row['exit_time'][:16] if row['exit_time'] else '',
            '戻り時刻': row['return_time'][:16] if row['return_time'] else ''
        })
    
    result_df = pd.DataFrame(formatted_data)
    
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        result_df.to_excel(writer, index=False, sheet_name=f'{date_str}勤怠記録')
        
        worksheet = writer.sheets[f'{date_str}勤怠記録']
        
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                if cell.value:
                    max_length = max(max_length, len(str(cell.value)))
            worksheet.column_dimensions[column_letter].width = min(max_length + 2, 15)
    
    excel_buffer.seek(0)
    
    return send_file(excel_buffer,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True,
                     download_name=f'勤怠記録_{date_str}.xlsx')

@app.route('/api/timecard/daily-summary', methods=['GET'])
@login_required
def get_daily_summary():
    date_str = request.args.get('date')
    if not date_str:
        return jsonify([])
    
    conn = get_db_connection()
    
    # 日付ごとの勤怠サマリーを取得（勤務時間計算機能削除版）
    query = '''
        SELECT 
            e.employee_id,
            e.name,
            MIN(CASE WHEN t.action = 'in' THEN t.timestamp END) as check_in,
            MAX(CASE WHEN t.action = 'out' THEN t.timestamp END) as check_out,
            MIN(CASE WHEN t.action = 'out_personal' THEN t.timestamp END) as exit_time,
            MAX(CASE WHEN t.action = 'in_personal' THEN t.timestamp END) as return_time
        FROM employees e
        LEFT JOIN timecard t ON e.employee_id = t.employee_id 
            AND DATE(t.timestamp) = ?
        GROUP BY e.employee_id, e.name
        ORDER BY e.employee_id
    '''
    
    records = conn.execute(query, (date_str,)).fetchall()
    conn.close()
    
    result = []
    for record in records:
        # 勤務時間計算機能を削除
        result.append({
            'employee_id': record['employee_id'],
            'name': record['name'],
            'check_in': record['check_in'][:16] if record['check_in'] else '',
            'check_out': record['check_out'][:16] if record['check_out'] else '',
            'morning_break_start': '',
            'morning_break_end': '',
            'lunch_break_start': '',
            'lunch_break_end': '',
            'evening_break_start': '',
            'evening_break_end': '',
            'exit_time': record['exit_time'][:16] if record['exit_time'] else '',
            'return_time': record['return_time'][:16] if record['return_time'] else ''
        })
    
    return jsonify(result)

@app.route('/api/timecard/detail', methods=['GET'])
@login_required
def get_timecard_detail():
    """従業員の日別詳細記録取得（修正版：休憩種別の列を削除）"""
    employee_id = request.args.get('employee_id')
    date_str = request.args.get('date')
    
    if not employee_id or not date_str:
        return jsonify({'error': 'employee_id and date are required'}), 400
    
    conn = get_db_connection()
    
    # 従業員名を取得
    employee = conn.execute('SELECT name FROM employees WHERE employee_id = ?', (employee_id,)).fetchone()
    if not employee:
        conn.close()
        return jsonify({'error': 'Employee not found'}), 404
    
    # その日の打刻詳細を取得（修正：break_typeを削除）
    punches = conn.execute('''
        SELECT id, timestamp, action, photo_path, location
        FROM timecard 
        WHERE employee_id = ? AND DATE(timestamp) = ?
        ORDER BY timestamp ASC
    ''', (employee_id, date_str)).fetchall()
    
    conn.close()
    
    return jsonify({
        'employee_name': employee['name'],
        'employee_id': employee_id,
        'date': date_str,
        'punches': [dict(punch) for punch in punches]
    })

# === デバッグ用API（新規追加） ===

@app.route('/api/debug/timecard-data', methods=['GET'])
@login_required
def debug_timecard_data():
    """デバッグ用: 打刻データの詳細確認"""
    try:
        date_str = request.args.get('date', datetime.now(JST).strftime('%Y-%m-%d'))
        employee_id = request.args.get('employee_id', 'TEST001')
        
        conn = get_db_connection()
        
        # 全打刻データの確認
        all_punches = conn.execute('''
            SELECT * FROM timecard 
            ORDER BY timestamp DESC 
            LIMIT 50
        ''').fetchall()
        
        # 特定日の打刻データ
        daily_punches = conn.execute('''
            SELECT * FROM timecard 
            WHERE DATE(timestamp) = ?
            ORDER BY timestamp DESC
        ''', (date_str,)).fetchall()
        
        # 特定従業員の打刻データ
        employee_punches = conn.execute('''
            SELECT * FROM timecard 
            WHERE employee_id = ?
            ORDER BY timestamp DESC 
            LIMIT 20
        ''', (employee_id,)).fetchall()
        
        # データベーステーブル構造確認
        table_info = conn.execute("PRAGMA table_info(timecard)").fetchall()
        
        # 従業員データ確認
        employees = conn.execute("SELECT * FROM employees").fetchall()
        
        conn.close()
        
        return jsonify({
            'debug_info': {
                'target_date': date_str,
                'target_employee': employee_id,
                'current_jst_time': datetime.now(JST).isoformat(),
                'table_structure': [dict(row) for row in table_info]
            },
            'all_punches_count': len(all_punches),
            'all_punches': [dict(row) for row in all_punches],
            'daily_punches_count': len(daily_punches),
            'daily_punches': [dict(row) for row in daily_punches],
            'employee_punches_count': len(employee_punches),
            'employee_punches': [dict(row) for row in employee_punches],
            'employees': [dict(row) for row in employees]
        })
        
    except Exception as e:
        return jsonify({'error': str(e), 'type': type(e).__name__})

@app.route('/api/debug/daily-summary-debug', methods=['GET'])
@login_required
def debug_daily_summary():
    """デバッグ用: 日別サマリー取得処理の詳細確認"""
    try:
        date_str = request.args.get('date', datetime.now(JST).strftime('%Y-%m-%d'))
        
        conn = get_db_connection()
        
        # 元のクエリを分解して確認
        employees_query = "SELECT * FROM employees ORDER BY employee_id"
        employees = conn.execute(employees_query).fetchall()
        
        # 各従業員の打刻データを個別に確認
        detailed_results = []
        
        for emp in employees:
            employee_id = emp['employee_id']
            
            # その従業員の当日の全打刻
            punches = conn.execute('''
                SELECT * FROM timecard 
                WHERE employee_id = ? AND DATE(timestamp) = ?
                ORDER BY timestamp ASC
            ''', (employee_id, date_str)).fetchall()
            
            # 各アクション別の最初/最後の時刻
            check_in = conn.execute('''
                SELECT MIN(timestamp) as time FROM timecard 
                WHERE employee_id = ? AND DATE(timestamp) = ? AND action = 'in'
            ''', (employee_id, date_str)).fetchone()
            
            check_out = conn.execute('''
                SELECT MAX(timestamp) as time FROM timecard 
                WHERE employee_id = ? AND DATE(timestamp) = ? AND action = 'out'
            ''', (employee_id, date_str)).fetchone()
            
            exit_time = conn.execute('''
                SELECT MIN(timestamp) as time FROM timecard 
                WHERE employee_id = ? AND DATE(timestamp) = ? AND action = 'out_personal'
            ''', (employee_id, date_str)).fetchone()
            
            return_time = conn.execute('''
                SELECT MAX(timestamp) as time FROM timecard 
                WHERE employee_id = ? AND DATE(timestamp) = ? AND action = 'in_personal'
            ''', (employee_id, date_str)).fetchone()
            
            detailed_results.append({
                'employee_id': employee_id,
                'employee_name': emp['name'],
                'punches_count': len(punches),
                'punches': [dict(p) for p in punches],
                'check_in': check_in['time'] if check_in and check_in['time'] else None,
                'check_out': check_out['time'] if check_out and check_out['time'] else None,
                'exit_time': exit_time['time'] if exit_time and exit_time['time'] else None,
                'return_time': return_time['time'] if return_time and return_time['time'] else None
            })
        
        # 元のサマリークエリも実行
        original_query = '''
            SELECT 
                e.employee_id,
                e.name,
                MIN(CASE WHEN t.action = 'in' THEN t.timestamp END) as check_in,
                MAX(CASE WHEN t.action = 'out' THEN t.timestamp END) as check_out,
                MIN(CASE WHEN t.action = 'out_personal' THEN t.timestamp END) as exit_time,
                MAX(CASE WHEN t.action = 'in_personal' THEN t.timestamp END) as return_time
            FROM employees e
            LEFT JOIN timecard t ON e.employee_id = t.employee_id 
                AND DATE(t.timestamp) = ?
            GROUP BY e.employee_id, e.name
            ORDER BY e.employee_id
        '''
        
        original_result = conn.execute(original_query, (date_str,)).fetchall()
        
        conn.close()
        
        return jsonify({
            'debug_info': {
                'target_date': date_str,
                'current_jst_time': datetime.now(JST).isoformat(),
                'employees_count': len(employees)
            },
            'detailed_analysis': detailed_results,
            'original_query_result': [dict(row) for row in original_result]
        })
        
    except Exception as e:
        return jsonify({'error': str(e), 'type': type(e).__name__})

@app.route('/api/debug/test-punch', methods=['POST'])
@login_required
def debug_test_punch():
    """デバッグ用: テスト打刻の実行と確認"""
    try:
        data = request.json or {}
        employee_id = data.get('employee_id', 'TEST001')
        action = data.get('action', 'in')
        
        # 現在時刻でテスト打刻
        now = datetime.now(JST)
        timestamp_str = now.strftime('%Y-%m-%d %H:%M:%S')
        
        conn = get_db_connection()
        
        # 打刻前の状態確認
        before_state = punch_validator.get_employee_state(employee_id, now.strftime('%Y-%m-%d'))
        
        # 整合性チェック
        is_valid, error_message = punch_validator.validate_punch(employee_id, action)
        
        if is_valid:
            # テスト打刻実行
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO timecard (employee_id, timestamp, action, location) 
                VALUES (?, ?, ?, ?)
            """, (employee_id, timestamp_str, action, 'テスト'))
            
            conn.commit()
            
            # 打刻後の確認
            inserted_id = cursor.lastrowid
            inserted_record = conn.execute("SELECT * FROM timecard WHERE id = ?", (inserted_id,)).fetchone()
            
            # 打刻後の状態確認
            after_state = punch_validator.get_employee_state(employee_id, now.strftime('%Y-%m-%d'))
            
            result = {
                'success': True,
                'message': 'テスト打刻が成功しました',
                'before_state': before_state.value,
                'after_state': after_state.value,
                'inserted_record': dict(inserted_record) if inserted_record else None,
                'timestamp_used': timestamp_str
            }
        else:
            result = {
                'success': False,
                'message': f'整合性チェックで拒否: {error_message}',
                'before_state': before_state.value,
                'validation_error': error_message
            }
        
        conn.close()
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'type': type(e).__name__
        })

# デバッグ用API（既存のものと統合）
@app.route('/api/debug/photos', methods=['GET'])
@login_required
def debug_photos():
    """デバッグ用: 写真保存状況確認"""
    try:
        photo_folder = os.path.join(app.root_path, app.config['PHOTO_FOLDER'])
        
        if not os.path.exists(photo_folder):
            return jsonify({
                'error': 'Photo folder not found',
                'photo_folder': photo_folder
            })
        
        # 写真ファイル一覧
        photo_files = []
        for filename in os.listdir(photo_folder):
            if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                file_path = os.path.join(photo_folder, filename)
                file_stat = os.stat(file_path)
                photo_files.append({
                    'filename': filename,
                    'size': file_stat.st_size,
                    'created': datetime.fromtimestamp(file_stat.st_ctime).isoformat(),
                    'url': f'/static/photos/{filename}'
                })
        
        # データベース内の写真パス確認
        conn = get_db_connection()
        db_photos = conn.execute('''
            SELECT employee_id, timestamp, photo_path 
            FROM timecard 
            WHERE photo_path IS NOT NULL 
            ORDER BY timestamp DESC 
            LIMIT 20
        ''').fetchall()
        conn.close()
        
        return jsonify({
            'photo_folder': photo_folder,
            'photo_files_count': len(photo_files),
            'photo_files': photo_files,
            'db_photos': [dict(row) for row in db_photos]
        })
        
    except Exception as e:
        return jsonify({'error': str(e)})

# Azure App Service用の初期化とエントリーポイント
if __name__ == '__main__':
    # Azure App Service用のログ出力
    logger.info("=" * 50)
    logger.info("勤怠管理システム - Azure App Service版を起動しています...")
    logger.info("=" * 50)

    # データベース初期化
    init_db()

    logger.info("システム起動完了！")
    logger.info("=" * 50)

    # Azure App Service用の設定
    # ポートは環境変数から取得、デフォルトは8000
    port = int(os.environ.get('PORT', 8000))

    app.run(host='0.0.0.0', port=port, debug=False)