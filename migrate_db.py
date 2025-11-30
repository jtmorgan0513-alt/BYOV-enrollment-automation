"""
Database Migration Script
For PostgreSQL: Schema is always up-to-date via init_db()
For SQLite: Adds approval tracking columns to enrollments table
"""
import os
import sys
import json

DATABASE_URL = os.environ.get("DATABASE_URL")
USE_POSTGRES = bool(DATABASE_URL)


def migrate_postgres():
    """PostgreSQL migrations are handled via init_db()."""
    print("PostgreSQL detected.")
    print("Schema migrations are handled automatically by init_db().")
    
    try:
        import database
        database.init_db()
        print("Database schema is up-to-date.")
        return True
    except Exception as e:
        print(f"Error initializing database: {e}")
        return False


def migrate_sqlite():
    """Add approval tracking columns to SQLite enrollments table."""
    import database
    
    print(f"Database path: {database.DB_PATH}")
    print(f"Using SQLite: {database.USE_SQLITE}")
    
    if database.USE_SQLITE and database.sqlite3:
        try:
            conn = database.sqlite3.connect(database.DB_PATH)
            cursor = conn.cursor()
            
            cursor.execute("PRAGMA table_info(enrollments)")
            columns = [row[1] for row in cursor.fetchall()]
            print(f"Current columns: {columns}")
            
            columns_to_add = []
            if 'approved' not in columns:
                columns_to_add.append(('approved', 'INTEGER DEFAULT 0'))
            if 'approved_at' not in columns:
                columns_to_add.append(('approved_at', 'TEXT'))
            if 'approved_by' not in columns:
                columns_to_add.append(('approved_by', 'TEXT'))
            if 'dashboard_tech_id' not in columns:
                columns_to_add.append(('dashboard_tech_id', 'TEXT'))
            if 'last_upload_report' not in columns:
                columns_to_add.append(('last_upload_report', 'TEXT'))
            if 'industry' not in columns:
                columns_to_add.append(('industry', 'TEXT'))
            
            if not columns_to_add:
                print("All columns already exist - no migration needed")
                conn.close()
                return True
            
            for col_name, col_type in columns_to_add:
                print(f"Adding column: {col_name} {col_type}")
                cursor.execute(f"""
                    ALTER TABLE enrollments 
                    ADD COLUMN {col_name} {col_type}
                """)
            
            conn.commit()
            
            cursor.execute("PRAGMA table_info(enrollments)")
            new_columns = [row[1] for row in cursor.fetchall()]
            print(f"Updated columns: {new_columns}")
            
            conn.close()
            
            print("Successfully added missing columns to enrollments table")
            return True
            
        except Exception as e:
            print(f"Migration failed: {e}")
            return False
    else:
        print("Migrating JSON fallback store...")
        try:
            fallback_file = os.path.join(database.DATA_DIR, "fallback_store.json")
            
            if not os.path.exists(fallback_file):
                print("No fallback store exists - nothing to migrate")
                return True
            
            with open(fallback_file, 'r') as f:
                store = json.load(f)
            
            modified_count = 0
            for enrollment in store.get('enrollments', []):
                if 'approved' not in enrollment:
                    enrollment['approved'] = 0
                    enrollment['approved_at'] = None
                    enrollment['approved_by'] = None
                    modified_count += 1
            
            with open(fallback_file, 'w') as f:
                json.dump(store, f, indent=2)
            
            print(f"Updated {modified_count} enrollments in JSON fallback store")
            return True
            
        except Exception as e:
            print(f"JSON migration failed: {e}")
            return False


if __name__ == '__main__':
    print("=" * 60)
    print("Database Migration")
    print("=" * 60)
    print(f"Database mode: {'PostgreSQL' if USE_POSTGRES else 'SQLite'}")
    
    if USE_POSTGRES:
        success = migrate_postgres()
    else:
        import database
        database.init_db()
        success = migrate_sqlite()
    
    print("=" * 60)
    if success:
        print("Migration completed successfully!")
        sys.exit(0)
    else:
        print("Migration failed - please review errors above")
        sys.exit(1)
