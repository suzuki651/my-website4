import sqlite3
import os

def migrate_database():
    """既存のデータベースにbreak_type列を追加"""
    db_path = 'timecard.db'
    
    if not os.path.exists(db_path):
        print("データベースファイルが見つかりません。")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 既存の列を確認
        cursor.execute("PRAGMA table_info(timecard)")
        columns = [column[1] for column in cursor.fetchall()]
        print(f"現在の列: {columns}")
        
        # break_type列が存在しない場合は追加
        if 'break_type' not in columns:
            print("break_type列を追加中...")
            cursor.execute("ALTER TABLE timecard ADD COLUMN break_type TEXT")
            print("break_type列を追加しました")
        else:
            print("break_type列は既に存在します")
        
        # 変更を確認
        cursor.execute("PRAGMA table_info(timecard)")
        updated_columns = [column[1] for column in cursor.fetchall()]
        print(f"更新後の列: {updated_columns}")
        
        conn.commit()
        conn.close()
        print("データベースマイグレーション完了")
        return True
        
    except Exception as e:
        print(f"マイグレーションエラー: {e}")
        return False

if __name__ == "__main__":
    migrate_database()