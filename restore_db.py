"""
Restore database from filesystem uploads.
Scans the uploads directory and recreates database records.
Supports both PostgreSQL and SQLite.
"""
import os
from datetime import datetime

DATABASE_URL = os.environ.get("DATABASE_URL")
USE_POSTGRES = bool(DATABASE_URL)

UPLOAD_ROOT = "uploads"


def restore():
    """Scan uploads directory and restore database records."""
    import database
    
    if not os.path.exists(UPLOAD_ROOT):
        print(f"Uploads directory not found: {UPLOAD_ROOT}")
        return
    
    database.init_db()
    restored_count = 0
    docs_added = 0
    
    for folder in os.listdir(UPLOAD_ROOT):
        folder_path = os.path.join(UPLOAD_ROOT, folder)
        
        if not os.path.isdir(folder_path):
            continue
        
        if "_" not in folder:
            continue
        
        tech_id = folder.split("_")[0]
        full_name = tech_id
        
        existing = None
        for e in database.get_all_enrollments():
            if e.get('tech_id') == tech_id:
                existing = e
                break
        
        if existing:
            enrollment_id = existing.get('id')
            print(f"Found existing enrollment for {tech_id}: ID {enrollment_id}")
        else:
            record = {
                "tech_id": tech_id,
                "full_name": full_name,
                "district": "",
                "state": "",
                "submission_date": datetime.now().isoformat()
            }
            enrollment_id = database.insert_enrollment(record)
            restored_count += 1
            print(f"Created enrollment for {tech_id}: ID {enrollment_id}")
        
        existing_docs = database.get_documents_for_enrollment(enrollment_id)
        existing_paths = {d.get('file_path') for d in existing_docs}
        
        for doc_type in ["vehicle", "registration", "insurance"]:
            subdir = os.path.join(folder_path, doc_type)
            if not os.path.exists(subdir):
                continue
            
            for fname in os.listdir(subdir):
                fpath = os.path.join(subdir, fname)
                
                if fpath not in existing_paths:
                    database.add_document(enrollment_id, doc_type, fpath)
                    docs_added += 1
                    print(f"  Added {doc_type}: {fname}")
    
    print(f"\nRestoration complete.")
    print(f"  Enrollments created: {restored_count}")
    print(f"  Documents added: {docs_added}")


if __name__ == "__main__":
    print("=" * 60)
    print("Database Restore from Filesystem")
    print("=" * 60)
    print(f"Database mode: {'PostgreSQL' if USE_POSTGRES else 'SQLite'}")
    print()
    restore()
