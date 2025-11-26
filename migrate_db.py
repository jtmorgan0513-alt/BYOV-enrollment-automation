"""
Database Migration Script
Adds approval tracking columns to enrollments table
"""
import os
import sys
import json
from datetime import datetime

# Import database configuration
import database

def migrate_add_approved_columns():
    """
    Add approval tracking columns to enrollments table:
    - approved: INTEGER DEFAULT 0 (0=pending, 1=approved)
    - approved_at: TEXT (ISO timestamp of approval)
    - approved_by: TEXT (Admin name who approved)
    
    This function is idempotent - safe to run multiple times.
    """
    print("Starting database migration...")
    print(f"Database path: {database.DB_PATH}")
    print(f"Using SQLite: {database.USE_SQLITE}")
    
    if database.USE_SQLITE and database.sqlite3:
        try:
            conn = database.sqlite3.connect(database.DB_PATH)
            cursor = conn.cursor()
            
            # Check if columns already exist
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
            
            if not columns_to_add:
                print("✓ All approval columns already exist - no migration needed")
                conn.close()
                return True
            
            # Add missing columns
            for col_name, col_type in columns_to_add:
                print(f"Adding column: {col_name} {col_type}")
                cursor.execute(f"""
                    ALTER TABLE enrollments 
                    ADD COLUMN {col_name} {col_type}
                """)
            
            conn.commit()
            
            # Verify changes
            cursor.execute("PRAGMA table_info(enrollments)")
            new_columns = [row[1] for row in cursor.fetchall()]
            print(f"Updated columns: {new_columns}")
            
            conn.close()
            
            print("✓ Successfully added approval tracking columns to enrollments table")
            return True
            
        except Exception as e:
            print(f"✗ Migration failed: {e}")
            return False
    else:
        # JSON fallback: modify store structure
        print("Migrating JSON fallback store...")
        try:
            fallback_file = os.path.join(database.DATA_DIR, "fallback_store.json")
            
            if not os.path.exists(fallback_file):
                print("✓ No fallback store exists - nothing to migrate")
                return True
            
            with open(fallback_file, 'r') as f:
                store = json.load(f)
            
            # Add approval fields to existing enrollments
            modified_count = 0
            for enrollment in store.get('enrollments', []):
                if 'approved' not in enrollment:
                    enrollment['approved'] = 0
                    enrollment['approved_at'] = None
                    enrollment['approved_by'] = None
                    modified_count += 1
            
            # Save updated store
            with open(fallback_file, 'w') as f:
                json.dump(store, f, indent=2)
            
            print(f"✓ Updated {modified_count} enrollments in JSON fallback store")
            return True
            
        except Exception as e:
            print(f"✗ JSON migration failed: {e}")
            return False


if __name__ == '__main__':
    print("=" * 60)
    print("Database Migration: Add Approval Tracking")
    print("=" * 60)
    
    # Ensure database is initialized
    database.init_db()
    
    # Run migration
    success = migrate_add_approved_columns()
    
    print("=" * 60)
    if success:
        print("Migration completed successfully!")
        sys.exit(0)
    else:
        print("Migration failed - please review errors above")
        sys.exit(1)
