import os
import sqlite3
from datetime import datetime

DB_PATH = "data/byov.db"
UPLOAD_ROOT = "uploads"   # top level 'uploads/' folder

def connect():
    return sqlite3.connect(DB_PATH)

def restore():
    conn = connect()
    cur = conn.cursor()

    # Ensure tables exist
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS enrollments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tech_id TEXT,
        full_name TEXT,
        district TEXT,
        state TEXT,
        submission_date TEXT
    );

    CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        enrollment_id INTEGER,
        doc_type TEXT,
        file_path TEXT,
        FOREIGN KEY(enrollment_id) REFERENCES enrollments(id)
    );
    """)

    conn.commit()

    restored_count = 0

    # Loop through every enrollment folder under /uploads/
    for folder in os.listdir(UPLOAD_ROOT):
        folder_path = os.path.join(UPLOAD_ROOT, folder)

        if not os.path.isdir(folder_path):
            continue

        # folder format: <tech_id>_<uuid>
        if "_" not in folder:
            continue

        tech_id = folder.split("_")[0]
        full_name = tech_id  # safest since no names in file system

        # Insert enrollment if not exists
        cur.execute("SELECT id FROM enrollments WHERE tech_id = ?", (tech_id,))
        row = cur.fetchone()

        if row:
            enrollment_id = row[0]
        else:
            cur.execute("""
                INSERT INTO enrollments (tech_id, full_name, district, state, submission_date)
                VALUES (?, ?, ?, ?, ?)
            """, (tech_id, full_name, "", "", datetime.now().isoformat()))
            enrollment_id = cur.lastrowid
            restored_count += 1

        # Process subfolders: vehicle, registration, insurance
        for doc_type in ["vehicle", "registration", "insurance"]:
            subdir = os.path.join(folder_path, doc_type)
            if not os.path.exists(subdir):
                continue

            for fname in os.listdir(subdir):
                fpath = os.path.join(subdir, fname)

                cur.execute("""
                    INSERT INTO documents (enrollment_id, doc_type, file_path)
                    VALUES (?, ?, ?)
                """, (enrollment_id, doc_type, fpath))

    conn.commit()
    conn.close()

    print(f"\nRestoration complete. Restored {restored_count} enrollments.\n")

if __name__ == "__main__":
    restore()
