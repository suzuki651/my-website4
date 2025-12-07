import os

class Config:
    """アプリケーション設定クラス"""
    SECRET_KEY = os.environ.get('SECRET_KEY')

    # 注意: SQLAlchemyは使用していません
    # 以下の設定は参考用に残しますが、実際には使用されていません
    # SQLALCHEMY_DATABASE_URI = 'sqlite:///timecard.db'
    # SQLALCHEMY_TRACK_MODIFICATIONS = False