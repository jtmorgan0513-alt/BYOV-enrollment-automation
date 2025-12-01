"""
PostgreSQL database module for BYOV Enrollment Engine.
Replaces SQLite with PostgreSQL for persistent storage across deployments.
"""
import os
import json
import time
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
from functools import wraps

import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get("DATABASE_URL")

MAX_RETRIES = 3
RETRY_DELAY = 0.5


def _create_connection():
    """Create a new database connection with retry logic."""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable not set")
    
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            return conn
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
    
    raise last_error if last_error else RuntimeError("Failed to connect to database")


@contextmanager
def get_connection():
    """Context manager for database connections."""
    conn = _create_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


@contextmanager
def get_cursor(dict_cursor: bool = True):
    """Context manager for database cursors."""
    with get_connection() as conn:
        cursor_factory = RealDictCursor if dict_cursor else None
        cursor = conn.cursor(cursor_factory=cursor_factory)
        try:
            yield cursor
        finally:
            cursor.close()


def with_retry(func):
    """Decorator to retry database operations on connection errors."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                raise
        if last_error:
            raise last_error
    return wrapper


def init_db():
    """Initialize database tables if they don't exist."""
    with get_cursor(dict_cursor=False) as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS enrollments (
                id SERIAL PRIMARY KEY,
                full_name TEXT NOT NULL,
                tech_id TEXT NOT NULL,
                district TEXT,
                state TEXT,
                referred_by TEXT,
                industries JSONB DEFAULT '[]',
                industry JSONB DEFAULT '[]',
                year TEXT,
                make TEXT,
                model TEXT,
                vin TEXT,
                insurance_exp TEXT,
                registration_exp TEXT,
                template_used TEXT,
                comment TEXT,
                submission_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                approved INTEGER DEFAULT 0,
                approved_at TIMESTAMP WITH TIME ZONE,
                approved_by TEXT,
                dashboard_tech_id TEXT,
                last_upload_report JSONB
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id SERIAL PRIMARY KEY,
                enrollment_id INTEGER NOT NULL REFERENCES enrollments(id) ON DELETE CASCADE,
                doc_type TEXT NOT NULL,
                file_path TEXT NOT NULL
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notification_rules (
                id SERIAL PRIMARY KEY,
                rule_name TEXT NOT NULL,
                trigger TEXT NOT NULL,
                days_before INTEGER,
                recipients TEXT NOT NULL,
                enabled INTEGER DEFAULT 1
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notifications_sent (
                id SERIAL PRIMARY KEY,
                enrollment_id INTEGER NOT NULL REFERENCES enrollments(id) ON DELETE CASCADE,
                rule_id INTEGER NOT NULL REFERENCES notification_rules(id) ON DELETE CASCADE,
                sent_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                id SERIAL PRIMARY KEY,
                setting_key TEXT UNIQUE NOT NULL,
                setting_value JSONB NOT NULL,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_enrollments_tech_id ON enrollments(tech_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_documents_enrollment_id ON documents(enrollment_id)")


def insert_enrollment(record: Dict[str, Any]) -> int:
    """Insert a new enrollment and return its ID."""
    industries_list = record.get("industry", record.get("industries", []))
    if isinstance(industries_list, str):
        try:
            industries_list = json.loads(industries_list)
        except:
            industries_list = [x.strip() for x in industries_list.split(",") if x.strip()]
    
    industries_json = json.dumps(industries_list)
    
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO enrollments (
                full_name, tech_id, district, state, referred_by,
                industries, industry, year, make, model, vin,
                insurance_exp, registration_exp, template_used, comment,
                submission_date, approved, approved_at, approved_by
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            ) RETURNING id
        """, (
            record.get("full_name"),
            record.get("tech_id"),
            record.get("district"),
            record.get("state"),
            record.get("referred_by"),
            industries_json,
            industries_json,
            record.get("year"),
            record.get("make"),
            record.get("model"),
            record.get("vin"),
            record.get("insurance_exp"),
            record.get("registration_exp"),
            record.get("template_used"),
            record.get("comment"),
            record.get("submission_date", datetime.now().isoformat()),
            0,
            None,
            None
        ))
        result = cursor.fetchone()
        return result["id"] if isinstance(result, dict) else result[0]


@with_retry
def get_all_enrollments() -> List[Dict[str, Any]]:
    """Return all enrollments ordered by submission date."""
    with get_cursor() as cursor:
        cursor.execute("SELECT * FROM enrollments ORDER BY submission_date DESC")
        rows = cursor.fetchall()
        
        results = []
        for row in rows:
            r = dict(row)
            if r.get("industries"):
                if isinstance(r["industries"], str):
                    try:
                        r["industries"] = json.loads(r["industries"])
                    except:
                        r["industries"] = []
            else:
                r["industries"] = []
            
            if r.get("industry"):
                if isinstance(r["industry"], str):
                    try:
                        r["industry"] = json.loads(r["industry"])
                    except:
                        r["industry"] = []
            else:
                r["industry"] = r["industries"]
            
            if r.get("submission_date"):
                r["submission_date"] = str(r["submission_date"])
            if r.get("approved_at"):
                r["approved_at"] = str(r["approved_at"])
            
            results.append(r)
        
        return results


@with_retry
def get_enrollment_by_id(enrollment_id: int) -> Optional[Dict[str, Any]]:
    """Return a single enrollment with its documents."""
    with get_cursor() as cursor:
        cursor.execute("SELECT * FROM enrollments WHERE id = %s", (enrollment_id,))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        record = dict(row)
        
        if record.get("industries"):
            if isinstance(record["industries"], str):
                try:
                    record["industries"] = json.loads(record["industries"])
                except:
                    record["industries"] = []
        else:
            record["industries"] = []
        
        if record.get("industry"):
            if isinstance(record["industry"], str):
                try:
                    record["industry"] = json.loads(record["industry"])
                except:
                    record["industry"] = []
        else:
            record["industry"] = record["industries"]
        
        if record.get("submission_date"):
            record["submission_date"] = str(record["submission_date"])
        if record.get("approved_at"):
            record["approved_at"] = str(record["approved_at"])
        
        cursor.execute(
            "SELECT id, doc_type, file_path FROM documents WHERE enrollment_id = %s",
            (enrollment_id,)
        )
        docs = cursor.fetchall()
        record["documents"] = [dict(d) for d in docs]
        
        return record


def update_enrollment(enrollment_id: int, updates: Dict[str, Any]):
    """Update specific fields on an enrollment."""
    if not updates:
        return
    
    fields = []
    values = []
    
    for key, value in updates.items():
        if key in ("industries", "industry"):
            value = json.dumps(value) if isinstance(value, (list, dict)) else value
            if key == "industry":
                fields.append("industry = %s")
                values.append(value)
                fields.append("industries = %s")
                values.append(value)
                continue
        fields.append(f"{key} = %s")
        values.append(value)
    
    values.append(enrollment_id)
    
    with get_cursor() as cursor:
        cursor.execute(
            f"UPDATE enrollments SET {', '.join(fields)} WHERE id = %s",
            values
        )


def set_dashboard_sync_info(enrollment_id: int, dashboard_tech_id: str = None, report: dict = None):
    """Persist dashboard sync metadata on an enrollment."""
    fields = []
    values = []
    
    if dashboard_tech_id is not None:
        fields.append("dashboard_tech_id = %s")
        values.append(str(dashboard_tech_id))
    
    if report is not None:
        fields.append("last_upload_report = %s")
        values.append(json.dumps(report))
    
    if not fields:
        return
    
    values.append(enrollment_id)
    
    with get_cursor() as cursor:
        cursor.execute(
            f"UPDATE enrollments SET {', '.join(fields)} WHERE id = %s",
            values
        )


def delete_enrollment(enrollment_id: int):
    """Delete an enrollment and its documents (CASCADE)."""
    with get_cursor() as cursor:
        cursor.execute("DELETE FROM enrollments WHERE id = %s", (enrollment_id,))


def add_document(enrollment_id: int, doc_type: str, file_path: str):
    """Add a document record for an enrollment."""
    with get_cursor() as cursor:
        cursor.execute(
            "INSERT INTO documents (enrollment_id, doc_type, file_path) VALUES (%s, %s, %s)",
            (enrollment_id, doc_type, file_path)
        )


def get_documents_for_enrollment(enrollment_id: int) -> List[Dict[str, Any]]:
    """Get all documents for an enrollment."""
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT id, doc_type, file_path FROM documents WHERE enrollment_id = %s",
            (enrollment_id,)
        )
        return [dict(row) for row in cursor.fetchall()]


def delete_documents_for_enrollment(enrollment_id: int):
    """Delete all documents for an enrollment."""
    with get_cursor() as cursor:
        cursor.execute("DELETE FROM documents WHERE enrollment_id = %s", (enrollment_id,))


def add_notification_rule(rule: Dict[str, Any]):
    """Add a notification rule."""
    recipients = rule.get("recipients", [])
    if isinstance(recipients, list):
        recipients = ",".join(recipients)
    
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO notification_rules (rule_name, trigger, days_before, recipients, enabled)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            rule["rule_name"],
            rule["trigger"],
            rule.get("days_before"),
            recipients,
            1 if rule.get("enabled", True) else 0
        ))


def get_notification_rules() -> List[Dict[str, Any]]:
    """Get all notification rules."""
    with get_cursor() as cursor:
        cursor.execute("SELECT * FROM notification_rules ORDER BY id DESC")
        rules = []
        for row in cursor.fetchall():
            r = dict(row)
            r["recipients"] = r["recipients"].split(",") if r["recipients"] else []
            rules.append(r)
        return rules


def update_notification_rule(rule_id: int, updates: Dict[str, Any]):
    """Update a notification rule."""
    fields = []
    values = []
    
    for k, v in updates.items():
        if k == "recipients" and isinstance(v, list):
            v = ",".join(v)
        fields.append(f"{k} = %s")
        values.append(v)
    
    values.append(rule_id)
    
    with get_cursor() as cursor:
        cursor.execute(
            f"UPDATE notification_rules SET {', '.join(fields)} WHERE id = %s",
            values
        )


def delete_notification_rule(rule_id: int):
    """Delete a notification rule."""
    with get_cursor() as cursor:
        cursor.execute("DELETE FROM notification_rules WHERE id = %s", (rule_id,))


def log_notification_sent(enrollment_id: int, rule_id: int):
    """Log that a notification was sent."""
    with get_cursor() as cursor:
        cursor.execute(
            "INSERT INTO notifications_sent (enrollment_id, rule_id) VALUES (%s, %s)",
            (enrollment_id, rule_id)
        )


def get_sent_notifications(enrollment_id: int) -> List[Dict[str, Any]]:
    """Get sent notifications for an enrollment."""
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT * FROM notifications_sent WHERE enrollment_id = %s",
            (enrollment_id,)
        )
        results = []
        for row in cursor.fetchall():
            r = dict(row)
            if r.get("sent_at"):
                r["sent_at"] = str(r["sent_at"])
            results.append(r)
        return results


def approve_enrollment(enrollment_id: int, approved_by: str = "Admin") -> bool:
    """Mark an enrollment as approved."""
    with get_cursor() as cursor:
        cursor.execute("""
            UPDATE enrollments
            SET approved = 1,
                approved_at = %s,
                approved_by = %s
            WHERE id = %s
        """, (datetime.now(), approved_by, enrollment_id))
    return True


def load_enrollments() -> List[Dict[str, Any]]:
    """Legacy compatibility: returns all enrollments."""
    return get_all_enrollments()


def save_enrollments(records):
    """Legacy function - no-op for compatibility."""
    pass


def get_approval_notification_settings() -> Optional[Dict[str, Any]]:
    """Get the approval notification settings."""
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT setting_value FROM app_settings WHERE setting_key = %s",
            ("approval_notification",)
        )
        row = cursor.fetchone()
        if row:
            value = row.get('setting_value') if isinstance(row, dict) else row[0]
            if isinstance(value, str):
                return json.loads(value)
            return value
        return None


def save_approval_notification_settings(settings: Dict[str, Any]) -> bool:
    """Save the approval notification settings."""
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO app_settings (setting_key, setting_value, updated_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (setting_key) 
            DO UPDATE SET setting_value = EXCLUDED.setting_value, updated_at = EXCLUDED.updated_at
        """, (
            "approval_notification",
            json.dumps(settings),
            datetime.now()
        ))
    return True


CHECKLIST_TASKS = [
    {'key': 'approved_synced', 'name': 'Approved Enrollment & Synced to Dashboard', 'default_recipient': ''},
    {'key': 'mileage_segno', 'name': 'Mileage form created in Segno', 'default_recipient': ''},
    {'key': 'fleet_truck', 'name': 'Fleet Notified for Truck Number', 'default_recipient': ''},
    {'key': 'inventory_assortment', 'name': 'Inventory Notified for Assortment', 'default_recipient': ''},
    {'key': 'supplies_magnets', 'name': 'Supplies Notified for Magnets', 'default_recipient': ''},
    {'key': 'policy_hshr', 'name': 'Signed Policy Form Sent to HSHRpaperwork', 'default_recipient': ''},
    {'key': 'survey_completed', 'name': 'Survey Completed', 'default_recipient': ''},
]


def init_checklist_table():
    """Initialize the enrollment_checklist table."""
    with get_cursor(dict_cursor=False) as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS enrollment_checklist (
                id SERIAL PRIMARY KEY,
                enrollment_id INTEGER NOT NULL REFERENCES enrollments(id) ON DELETE CASCADE,
                task_key TEXT NOT NULL,
                task_name TEXT NOT NULL,
                completed BOOLEAN DEFAULT FALSE,
                completed_at TIMESTAMPTZ,
                completed_by TEXT,
                email_recipient TEXT,
                email_sent BOOLEAN DEFAULT FALSE,
                email_sent_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(enrollment_id, task_key)
            )
        """)


def create_checklist_for_enrollment(enrollment_id: int) -> bool:
    """Create checklist tasks for a new enrollment."""
    with get_cursor() as cursor:
        for task in CHECKLIST_TASKS:
            cursor.execute("""
                INSERT INTO enrollment_checklist (enrollment_id, task_key, task_name, email_recipient)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (enrollment_id, task_key) DO NOTHING
            """, (enrollment_id, task['key'], task['name'], task['default_recipient']))
    return True


def get_checklist_for_enrollment(enrollment_id: int) -> List[Dict[str, Any]]:
    """Get all checklist tasks for an enrollment."""
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT id, enrollment_id, task_key, task_name, completed, completed_at, 
                   completed_by, email_recipient, email_sent, email_sent_at, created_at
            FROM enrollment_checklist
            WHERE enrollment_id = %s
            ORDER BY id
        """, (enrollment_id,))
        rows = cursor.fetchall()
        results = []
        for row in rows:
            r = dict(row)
            if r.get("completed_at"):
                r["completed_at"] = str(r["completed_at"])
            if r.get("email_sent_at"):
                r["email_sent_at"] = str(r["email_sent_at"])
            if r.get("created_at"):
                r["created_at"] = str(r["created_at"])
            results.append(r)
        return results


def update_checklist_task(task_id: int, completed: bool, completed_by: str = "Admin") -> bool:
    """Update a checklist task's completion status."""
    with get_cursor() as cursor:
        if completed:
            cursor.execute("""
                UPDATE enrollment_checklist
                SET completed = %s, completed_at = %s, completed_by = %s
                WHERE id = %s
            """, (completed, datetime.now(), completed_by, task_id))
        else:
            cursor.execute("""
                UPDATE enrollment_checklist
                SET completed = %s, completed_at = NULL, completed_by = NULL
                WHERE id = %s
            """, (completed, task_id))
    return True


def update_checklist_task_email(task_id: int, email_recipient: str) -> bool:
    """Update the email recipient for a checklist task."""
    with get_cursor() as cursor:
        cursor.execute("""
            UPDATE enrollment_checklist
            SET email_recipient = %s
            WHERE id = %s
        """, (email_recipient, task_id))
    return True


def mark_checklist_email_sent(task_id: int) -> bool:
    """Mark that the notification email was sent for a task."""
    with get_cursor() as cursor:
        cursor.execute("""
            UPDATE enrollment_checklist
            SET email_sent = TRUE, email_sent_at = %s
            WHERE id = %s
        """, (datetime.now(), task_id))
    return True


def get_checklist_task_recipients() -> Dict[str, str]:
    """Get default email recipients for each task type from app_settings."""
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT setting_value FROM app_settings WHERE setting_key = %s",
            ("checklist_recipients",)
        )
        row = cursor.fetchone()
        if row:
            value = row.get('setting_value') if isinstance(row, dict) else row[0]
            if isinstance(value, str):
                return json.loads(value)
            return value
        return {}


def save_checklist_task_recipients(recipients: Dict[str, str]) -> bool:
    """Save default email recipients for checklist tasks."""
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO app_settings (setting_key, setting_value, updated_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (setting_key) 
            DO UPDATE SET setting_value = EXCLUDED.setting_value, updated_at = EXCLUDED.updated_at
        """, (
            "checklist_recipients",
            json.dumps(recipients),
            datetime.now()
        ))
    return True


USE_SQLITE = False
DB_PATH = None

try:
    init_db()
    init_checklist_table()
except Exception as e:
    print(f"Warning: Could not initialize PostgreSQL database: {e}")
