"""
Clear all data from the BYOV database and uploaded files
"""
import sqlite3
import os
import json
import shutil

DATA_DIR = "data"
UPLOADS_DIR = "uploads"
PDFS_DIR = "pdfs"
DB_PATH = os.path.join(DATA_DIR, "byov.db")
FALLBACK_FILE = os.path.join(DATA_DIR, "fallback_store.json")

def clear_sqlite_database():
    """Clear all data from SQLite database"""
    if not os.path.exists(DB_PATH):
        print(f"Database file not found: {DB_PATH}")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Delete in correct order (respecting foreign keys)
    tables = ['notifications_sent', 'documents', 'notification_rules', 'enrollments']
    
    for table in tables:
        cur.execute(f'DELETE FROM {table}')
        count = cur.rowcount
        print(f"Deleted {count} records from {table}")
    
    conn.commit()
    
    # Verify all tables are empty
    print("\nVerifying database is empty:")
    for table in tables:
        cur.execute(f'SELECT COUNT(*) FROM {table}')
        count = cur.fetchone()[0]
        print(f"  {table}: {count} records")
    
    conn.close()
    print("\n✓ SQLite database cleared successfully!")


def clear_fallback_json():
    """Clear all data from fallback JSON file"""
    if not os.path.exists(FALLBACK_FILE):
        print(f"Fallback file not found: {FALLBACK_FILE}")
        return
    
    store = {
        "enrollments": [],
        "documents": [],
        "notification_rules": [],
        "notifications_sent": [],
        "counters": {
            "enrollment_id": 0,
            "document_id": 0,
            "rule_id": 0,
            "sent_id": 0
        }
    }
    
    with open(FALLBACK_FILE, 'w', encoding='utf-8') as f:
        json.dump(store, f, indent=2)
    
    print("\n✓ Fallback JSON store cleared successfully!")


def clear_uploaded_files():
    """Remove all uploaded files and generated PDFs"""
    files_removed = 0
    dirs_removed = 0
    
    # Clear uploads directory
    if os.path.exists(UPLOADS_DIR):
        for item in os.listdir(UPLOADS_DIR):
            item_path = os.path.join(UPLOADS_DIR, item)
            try:
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                    dirs_removed += 1
                    print(f"  Removed directory: {item}")
                else:
                    os.remove(item_path)
                    files_removed += 1
                    print(f"  Removed file: {item}")
            except Exception as e:
                print(f"  ⚠️  Error removing {item}: {e}")
    else:
        print(f"Uploads directory not found: {UPLOADS_DIR}")
    
    # Clear PDFs directory
    if os.path.exists(PDFS_DIR):
        for item in os.listdir(PDFS_DIR):
            item_path = os.path.join(PDFS_DIR, item)
            try:
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                    dirs_removed += 1
                    print(f"  Removed directory: {item}")
                elif item not in ['template_1.pdf', 'template_2.pdf']:  # Keep templates
                    os.remove(item_path)
                    files_removed += 1
                    print(f"  Removed file: {item}")
            except Exception as e:
                print(f"  ⚠️  Error removing {item}: {e}")
    else:
        print(f"PDFs directory not found: {PDFS_DIR}")
    
    print(f"\n✓ Removed {dirs_removed} directories and {files_removed} files")



if __name__ == '__main__':
    print("=" * 60)
    print("BYOV Database & Files Cleanup Utility")
    print("=" * 60)
    print("\nThis will delete ALL data including:")
    print("  - All enrollment records")
    print("  - All uploaded documents (images, PDFs, etc.)")
    print("  - All generated enrollment PDFs")
    print("  - All notification rules")
    print("  - All notification logs")
    print("\n⚠️  WARNING: This action cannot be undone!")
    
    response = input("\nAre you sure you want to continue? (yes/no): ").strip().lower()
    
    if response == 'yes':
        print("\nClearing database and files...\n")
        clear_sqlite_database()
        clear_fallback_json()
        print("\nRemoving uploaded files and generated PDFs...\n")
        clear_uploaded_files()
        print("\n" + "=" * 60)
        print("All database records and files have been cleared!")
        print("=" * 60)
    else:
        print("\nOperation cancelled. No data was deleted.")
