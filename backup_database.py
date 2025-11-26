#!/usr/bin/env python3
"""
Database backup utility for BYOV enrollment system.
Creates timestamped backups of the SQLite database.
"""

import os
import shutil
import sqlite3
from datetime import datetime


def backup_database():
    """Create a timestamped backup of the database."""
    
    db_path = "data/byov.db"
    backup_dir = "data/backups"
    
    # Create backup directory if it doesn't exist
    os.makedirs(backup_dir, exist_ok=True)
    
    if not os.path.exists(db_path):
        print(f"❌ Database not found at {db_path}")
        return False
    
    # Generate timestamp for backup filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"byov_backup_{timestamp}.db")
    
    try:
        # Get record count before backup
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM enrollments")
        count = cursor.fetchone()[0]
        conn.close()
        
        # Copy database file
        shutil.copy2(db_path, backup_path)
        
        # Get file size
        size_kb = os.path.getsize(backup_path) / 1024
        
        print(f"✅ Backup created successfully!")
        print(f"   File: {backup_path}")
        print(f"   Size: {size_kb:.2f} KB")
        print(f"   Enrollments: {count}")
        
        return True
        
    except Exception as e:
        print(f"❌ Backup failed: {e}")
        return False


def list_backups():
    """List all available backups."""
    
    backup_dir = "data/backups"
    
    if not os.path.exists(backup_dir):
        print("No backups directory found.")
        return
    
    backups = [f for f in os.listdir(backup_dir) if f.endswith('.db')]
    
    if not backups:
        print("No backups found.")
        return
    
    print(f"\n📦 Available backups ({len(backups)}):")
    print("-" * 60)
    
    backups.sort(reverse=True)
    
    for backup in backups:
        path = os.path.join(backup_dir, backup)
        size_kb = os.path.getsize(path) / 1024
        mod_time = datetime.fromtimestamp(os.path.getmtime(path))
        
        print(f"{backup}")
        print(f"  Date: {mod_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Size: {size_kb:.2f} KB")
        print()


def restore_database(backup_filename):
    """Restore database from a backup file."""
    
    db_path = "data/byov.db"
    backup_path = os.path.join("data/backups", backup_filename)
    
    if not os.path.exists(backup_path):
        print(f"❌ Backup file not found: {backup_path}")
        return False
    
    try:
        # Create backup of current database first
        if os.path.exists(db_path):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safety_backup = f"data/backups/before_restore_{timestamp}.db"
            shutil.copy2(db_path, safety_backup)
            print(f"💾 Safety backup created: {safety_backup}")
        
        # Restore from backup
        shutil.copy2(backup_path, db_path)
        
        # Verify restored database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM enrollments")
        count = cursor.fetchone()[0]
        conn.close()
        
        print(f"✅ Database restored successfully!")
        print(f"   Enrollments: {count}")
        
        return True
        
    except Exception as e:
        print(f"❌ Restore failed: {e}")
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
        # Default: create backup
        backup_database()
        print()
        list_backups()
