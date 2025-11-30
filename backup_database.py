#!/usr/bin/env python3
"""
Database backup utility for BYOV enrollment system.
Supports both PostgreSQL (when DATABASE_URL is set) and SQLite.
"""

import os
import shutil
import json
from datetime import datetime

DATABASE_URL = os.environ.get("DATABASE_URL")
USE_POSTGRES = bool(DATABASE_URL)


def backup_database():
    """Create a timestamped backup of the database."""
    
    backup_dir = "data/backups"
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if USE_POSTGRES:
        try:
            import database
            
            enrollments = database.get_all_enrollments()
            
            for e in enrollments:
                e['documents'] = database.get_documents_for_enrollment(e['id'])
            
            rules = database.get_notification_rules()
            
            backup_data = {
                "timestamp": datetime.now().isoformat(),
                "database_type": "postgresql",
                "enrollments": enrollments,
                "notification_rules": rules
            }
            
            backup_path = os.path.join(backup_dir, f"byov_backup_{timestamp}.json")
            
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, indent=2, default=str)
            
            size_kb = os.path.getsize(backup_path) / 1024
            
            print(f"Backup created successfully!")
            print(f"   File: {backup_path}")
            print(f"   Size: {size_kb:.2f} KB")
            print(f"   Enrollments: {len(enrollments)}")
            print(f"   Notification Rules: {len(rules)}")
            print(f"   Type: PostgreSQL (JSON export)")
            
            return True
            
        except Exception as e:
            print(f"Backup failed: {e}")
            return False
    else:
        import sqlite3
        
        db_path = "data/byov.db"
        
        if not os.path.exists(db_path):
            print(f"Database not found at {db_path}")
            return False
        
        backup_path = os.path.join(backup_dir, f"byov_backup_{timestamp}.db")
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM enrollments")
            count = cursor.fetchone()[0]
            conn.close()
            
            shutil.copy2(db_path, backup_path)
            
            size_kb = os.path.getsize(backup_path) / 1024
            
            print(f"Backup created successfully!")
            print(f"   File: {backup_path}")
            print(f"   Size: {size_kb:.2f} KB")
            print(f"   Enrollments: {count}")
            print(f"   Type: SQLite")
            
            return True
            
        except Exception as e:
            print(f"Backup failed: {e}")
            return False


def list_backups():
    """List all available backups."""
    
    backup_dir = "data/backups"
    
    if not os.path.exists(backup_dir):
        print("No backups directory found.")
        return
    
    backups = [f for f in os.listdir(backup_dir) if f.endswith(('.db', '.json'))]
    
    if not backups:
        print("No backups found.")
        return
    
    print(f"\nAvailable backups ({len(backups)}):")
    print("-" * 60)
    
    backups.sort(reverse=True)
    
    for backup in backups:
        path = os.path.join(backup_dir, backup)
        size_kb = os.path.getsize(path) / 1024
        mod_time = datetime.fromtimestamp(os.path.getmtime(path))
        backup_type = "JSON (PostgreSQL)" if backup.endswith('.json') else "SQLite"
        
        print(f"{backup}")
        print(f"  Date: {mod_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Size: {size_kb:.2f} KB")
        print(f"  Type: {backup_type}")
        print()


def restore_database(backup_filename):
    """Restore database from a backup file."""
    
    backup_path = os.path.join("data/backups", backup_filename)
    
    if not os.path.exists(backup_path):
        print(f"Backup file not found: {backup_path}")
        return False
    
    if backup_filename.endswith('.json'):
        try:
            with open(backup_path, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)
            
            print(f"JSON backup restore requires manual import.")
            print(f"Backup contains:")
            print(f"   Enrollments: {len(backup_data.get('enrollments', []))}")
            print(f"   Notification Rules: {len(backup_data.get('notification_rules', []))}")
            print(f"   Created: {backup_data.get('timestamp', 'Unknown')}")
            return False
            
        except Exception as e:
            print(f"Failed to read backup: {e}")
            return False
    else:
        import sqlite3
        
        db_path = "data/byov.db"
        
        try:
            if os.path.exists(db_path):
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safety_backup = f"data/backups/before_restore_{timestamp}.db"
                shutil.copy2(db_path, safety_backup)
                print(f"Safety backup created: {safety_backup}")
            
            shutil.copy2(backup_path, db_path)
            
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM enrollments")
            count = cursor.fetchone()[0]
            conn.close()
            
            print(f"Database restored successfully!")
            print(f"   Enrollments: {count}")
            
            return True
            
        except Exception as e:
            print(f"Restore failed: {e}")
            return False


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "backup":
            backup_database()
        elif command == "list":
            list_backups()
        elif command == "restore" and len(sys.argv) > 2:
            restore_database(sys.argv[2])
        else:
            print("Usage:")
            print("  python backup_database.py backup          - Create a backup")
            print("  python backup_database.py list            - List all backups")
            print("  python backup_database.py restore <file>  - Restore from backup")
    else:
        backup_database()
        print()
        list_backups()
