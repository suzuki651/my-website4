#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Azure App Service用スタートアップファイル（修正版）
"""

import os
import sys
import logging
from typing import List, Dict, Optional
import time

# Azure App Service環境の検出
IS_AZURE = bool(os.environ.get('AZURE_ENV') or os.environ.get('WEBSITE_SITE_NAME'))

# ログ設定の改善
def setup_logging() -> logging.Logger:
    """Azure環境に最適化されたログ設定"""
    logger = logging.getLogger(__name__)
    
    if IS_AZURE:
        # Azureでは診断ログと重複を避けるため、WARNING以上に設定
        log_level = logging.WARNING
        # Azure App Serviceのログストリームに出力
        handler = logging.StreamHandler(sys.stdout)
    else:
        # ローカル開発環境ではINFO以上
        log_level = logging.INFO
        handler = logging.StreamHandler(sys.stdout)
    
    logger.setLevel(log_level)
    
    # フォーマッターの設定
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    return logger

logger = setup_logging()

def check_azure_environment() -> Dict[str, Optional[str]]:
    """Azure環境の詳細チェック"""
    env_info = {
        'WEBSITE_SITE_NAME': os.environ.get('WEBSITE_SITE_NAME'),
        'WEBSITE_RESOURCE_GROUP': os.environ.get('WEBSITE_RESOURCE_GROUP'),
        'WEBSITE_SKU': os.environ.get('WEBSITE_SKU'),
        'PORT': os.environ.get('PORT'),
        'PYTHONPATH': os.environ.get('PYTHONPATH'),
        'AZURE_ENV': os.environ.get('AZURE_ENV')
    }
    
    if IS_AZURE:
        logger.warning(f"Azure App Service環境を検出: {env_info.get('WEBSITE_SITE_NAME', 'Unknown')}")
        for key, value in env_info.items():
            if value:
                logger.info(f"環境変数 {key}: {value}")
    
    return env_info

def setup_azure_environment() -> int:
    """Azure環境用の設定（エラーハンドリング強化版）"""
    max_retries = 3
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            # Azure環境情報の取得と表示
            check_azure_environment()
            
            # ポート設定
            port_str: Optional[str] = os.environ.get('PORT')
            port: int = int(port_str) if port_str else 8000
            
            if IS_AZURE:
                logger.warning(f"Azure App Service用ポート設定: {port}")
            else:
                logger.info(f"ローカル開発環境用ポート設定: {port}")
            
            # 必須環境変数の確認
            required_env_vars: List[str] = ['SECRET_KEY'] if not IS_AZURE else []
            missing_vars: List[str] = []
            
            for var in required_env_vars:
                env_value: Optional[str] = os.environ.get(var)
                if not env_value:
                    missing_vars.append(var)
            
            if missing_vars:
                logger.warning(f"未設定の環境変数: {missing_vars}")
                if IS_AZURE:
                    logger.error("Azure App Serviceの構成で環境変数を設定してください")
            
            # データベース初期化（リトライ機能付き）
            try:
                logger.info("データベース初期化開始...")
                
                # アプリケーションのインポート（遅延インポート）
                from app import init_db
                
                init_db()
                logger.info("データベース初期化完了")
                
            except Exception as db_error:
                logger.error(f"データベース初期化エラー（試行 {attempt + 1}/{max_retries}): {db_error}")
                if attempt < max_retries - 1:
                    logger.info(f"{retry_delay}秒後にリトライします...")
                    time.sleep(retry_delay)
                    continue
                else:
                    logger.error("データベース初期化に失敗しました。手動での確認が必要です。")
                    # Azure環境では続行を試みる（データベースが後で利用可能になる可能性）
                    if not IS_AZURE:
                        raise
            
            return port
            
        except ImportError as import_error:
            logger.error(f"アプリケーションモジュールのインポートエラー: {import_error}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            else:
                logger.error("アプリケーションの起動に失敗しました")
                raise
        except Exception as e:
            logger.error(f"Azure環境設定エラー（試行 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            else:
                raise

    # ここに到達することはないはずだが、安全のため
    return 8000

def main() -> None:
    """メイン実行関数（エラーハンドリング強化版）"""
    try:
        logger.warning("=" * 50)
        if IS_AZURE:
            logger.warning("勤怠管理システム (Azure App Service版) 起動中...")
        else:
            logger.info("勤怠管理システム (開発環境版) 起動中...")
        logger.warning("=" * 50)
        
        # Azure環境設定
        port: int = setup_azure_environment()
        
        # アプリケーションのインポート
        try:
            from app import app
        except ImportError as e:
            logger.error(f"Flaskアプリケーションのインポートに失敗: {e}")
            sys.exit(1)
        
        # アプリケーション設定確認
        logger.info("アプリケーション設定:")
        logger.info(f"- DEBUG: {app.debug}")
        
        # SECRET_KEY設定確認（型チェック警告を抑制）
        has_secret_key: bool = bool(app.config.get('SECRET_KEY'))
        logger.info(f"- SECRET_KEY設定: {'✓' if has_secret_key else '✗'}")
        logger.info(f"- ポート: {port}")
        
        # 環境変数確認（機密情報は表示しない）
        logger.info("環境変数設定状況:")
        env_status: Dict[str, bool] = {
            'SMTP_SERVER': bool(os.environ.get('SMTP_SERVER')),
            'EMAIL_USERNAME': bool(os.environ.get('EMAIL_USERNAME')),
            'EMAIL_PASSWORD': bool(os.environ.get('EMAIL_PASSWORD')),
            'ADMIN_EMAIL': bool(os.environ.get('ADMIN_EMAIL'))
        }
        
        for key, status in env_status.items():
            logger.info(f"- {key}: {'✓' if status else '✗'}")
        
        logger.warning("=" * 50)
        logger.warning("システム起動完了！")
        logger.warning("=" * 50)
        
        # Flask アプリケーション起動
        if IS_AZURE:
            # Azure App ServiceではWSGIサーバーが使用される
            logger.warning("Azure App Service環境でアプリケーションを起動します")
            app.run(
                host='0.0.0.0',
                port=port,
                debug=False,  # 本番環境では必ずFalse
                threaded=True,  # Azure App Serviceでの並行処理対応
                use_reloader=False  # Azureでは不要
            )
        else:
            # ローカル開発環境
            logger.info("ローカル開発環境でアプリケーションを起動します")
            app.run(
                host='0.0.0.0',
                port=port,
                debug=True,
                threaded=True
            )
        
    except KeyboardInterrupt:
        logger.info("ユーザーによる中断を検出しました")
        sys.exit(0)
    except ImportError as e:
        logger.error(f"必要なモジュールのインポートエラー: {e}")
        logger.error("必要な依存関係がインストールされているか確認してください")
        sys.exit(1)
    except Exception as e:
        logger.error(f"アプリケーション起動エラー: {e}")
        logger.error("詳細なエラー情報:", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()