"""
Database module for BYOV Enrollment Engine.
Uses PostgreSQL when DATABASE_URL is available, otherwise falls back to SQLite/JSON.
"""
import os
import json
from datetime import datetime

DATABASE_URL = os.environ.get("DATABASE_URL")

USE_POSTGRES = bool(DATABASE_URL)
USE_POSTGRESQL = USE_POSTGRES

if USE_POSTGRES:
    from database_pg import (
        init_db,
        insert_enrollment,
        get_all_enrollments,
        get_enrollment_by_id,
        update_enrollment,
        set_dashboard_sync_info,
        delete_enrollment,
        add_document,
        get_documents_for_enrollment,
        delete_documents_for_enrollment,
        add_notification_rule as _add_notification_rule,
        get_notification_rules,
        update_notification_rule,
        delete_notification_rule,
        log_notification_sent,
        get_sent_notifications,
        approve_enrollment,
        load_enrollments,
        save_enrollments,
    )
    
    get_all_notification_rules = get_notification_rules
    
    def add_notification_rule(rule_name, trigger, days_before, recipients, enabled=True):
        """Wrapper to add notification rule with individual parameters."""
        return _add_notification_rule({
            "rule_name": rule_name,
            "trigger": trigger,
            "days_before": days_before,
            "recipients": recipients,
            "enabled": 1 if enabled else 0
        })
    
    USE_SQLITE = False
    DB_PATH = None
    
    print("Database: Using PostgreSQL (persistent storage)")
else:
    import sqlite3 as _sqlite3
    sqlite3 = _sqlite3
    
    DATA_DIR = "data"
    DB_PATH = os.path.join(DATA_DIR, "byov.db")
    USE_SQLITE = True
    
    print("Database: Using SQLite (local storage - not persistent across deployments)")

    FALLBACK_FILE = os.path.join(DATA_DIR, "fallback_store.json")

    def _load_store():
        try:
            with open(FALLBACK_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {"enrollments": [], "documents": [], "notification_rules": [], "notifications_sent": [], "counters": {"enrollment_id": 0, "document_id": 0, "rule_id": 0, "sent_id": 0}}

    def _save_store(store):
        with open(FALLBACK_FILE, 'w', encoding='utf-8') as f:
            json.dump(store, f, indent=2)

    def init_db():
        """Creates the database directory and tables if they don't exist."""
        try:
            if not os.path.exists(DATA_DIR):
                os.makedirs(DATA_DIR, exist_ok=True)

            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS enrollments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_name TEXT NOT NULL,
                    tech_id TEXT NOT NULL,
                    district TEXT,
                    state TEXT,
                    referred_by TEXT,
                    industries TEXT,
                    industry TEXT,
                    year TEXT,
                    make TEXT,
                    model TEXT,
                    vin TEXT,
                    insurance_exp TEXT,
                    registration_exp TEXT,
                    template_used TEXT,
                    comment TEXT,
                    submission_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    approved INTEGER DEFAULT 0,
                    approved_at TEXT,
                    approved_by TEXT,
                    dashboard_tech_id TEXT,
                    last_upload_report TEXT
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    enrollment_id INTEGER NOT NULL,
                    doc_type TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    FOREIGN KEY(enrollment_id) REFERENCES enrollments(id)
                        ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notification_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rule_name TEXT NOT NULL,
                    trigger TEXT NOT NULL,
                    days_before INTEGER,
                    recipients TEXT NOT NULL,
                    enabled INTEGER DEFAULT 1
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notifications_sent (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    enrollment_id INTEGER NOT NULL,
                    rule_id INTEGER NOT NULL,
                    sent_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(enrollment_id) REFERENCES enrollments(id),
                    FOREIGN KEY(rule_id) REFERENCES notification_rules(id)
                )
            """)

            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error initializing database: {e}")

    def insert_enrollment(record):
        """Insert a new enrollment row and return its assigned ID."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        industries_list = record.get("industry", record.get("industries", []))
        industries_json = json.dumps(industries_list)

        cursor.execute("""
            INSERT INTO enrollments (
                full_name, tech_id, district, state, referred_by,
                industries, industry, year, make, model, vin,
                insurance_exp, registration_exp,
                template_used, comment, submission_date,
                approved, approved_at, approved_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

        enrollment_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return enrollment_id

    def get_all_enrollments():
        """Return all enrollments as list[dict]."""
        try:
            init_db()
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM enrollments ORDER BY submission_date DESC")
            rows = cursor.fetchall()

            columns = [col[0] for col in cursor.description]
            conn.close()

            results = []
            for row in rows:
                r = dict(zip(columns, row))
                if r.get("industry"):
                    try:
                        r["industry"] = json.loads(r["industry"])
                    except:
                        r["industry"] = []
                    r["industries"] = list(r["industry"]) if isinstance(r["industry"], list) else []
                elif r.get("industries"):
                    try:
                        r["industries"] = json.loads(r["industries"])
                    except:
                        r["industries"] = []
                    r["industry"] = list(r["industries"]) if isinstance(r["industries"], list) else []
                results.append(r)

            return results
        except Exception as e:
            print(f"Database error in get_all_enrollments: {e}")
            return []

    def get_enrollment_by_id(enrollment_id):
        """Return a single enrollment + all documents."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM enrollments WHERE id = ?", (enrollment_id,))
        row = cursor.fetchone()

        if not row:
            conn.close()
            return None

        columns = [col[0] for col in cursor.description]
        record = dict(zip(columns, row))

        if record.get("industries"):
            try:
                record["industries"] = json.loads(record["industries"])
            except:
                record["industries"] = []
        if record.get("industry"):
            try:
                record["industry"] = json.loads(record["industry"])
            except:
                record["industry"] = []
            record["industries"] = list(record["industry"]) if isinstance(record["industry"], list) else []

        cursor.execute("SELECT id, doc_type, file_path FROM documents WHERE enrollment_id = ?", (enrollment_id,))
        docs = cursor.fetchall()

        conn.close()

        record["documents"] = [
            {"id": d[0], "doc_type": d[1], "file_path": d[2]} for d in docs
        ]
        return record

    def update_enrollment(enrollment_id, updates: dict):
        """Update specific fields on an enrollment."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        fields = []
        values = []

        for key, value in updates.items():
            if key == "industries" or key == "industry":
                value_json = json.dumps(value)
                if key == 'industry':
                    fields.append("industry = ?")
                    values.append(value_json)
                    fields.append("industries = ?")
                    values.append(value_json)
                    continue
                else:
                    value = value_json
            fields.append(f"{key} = ?")
            values.append(value)

        values.append(enrollment_id)

        cursor.execute(f"UPDATE enrollments SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()
        conn.close()

    def set_dashboard_sync_info(enrollment_id, dashboard_tech_id: str = None, report: dict = None):
        """Persist dashboard sync metadata on an enrollment."""
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            fields = []
            values = []
            if dashboard_tech_id is not None:
                fields.append("dashboard_tech_id = ?")
                values.append(str(dashboard_tech_id))
            if report is not None:
                try:
                    report_json = json.dumps(report)
                except Exception:
                    report_json = json.dumps({"error": "failed to serialize report"})
                fields.append("last_upload_report = ?")
                values.append(report_json)
            if not fields:
                return
            values.append(enrollment_id)
            cursor.execute(f"UPDATE enrollments SET {', '.join(fields)} WHERE id = ?", values)
            conn.commit()
            conn.close()
        except Exception:
            pass

    def delete_enrollment(enrollment_id):
        """Delete enrollment + all documents."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM enrollments WHERE id = ?", (enrollment_id,))
        conn.commit()
        conn.close()

    def add_document(enrollment_id, doc_type, file_path):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO documents (enrollment_id, doc_type, file_path)
            VALUES (?, ?, ?)
        """, (enrollment_id, doc_type, file_path))
        conn.commit()
        conn.close()

    def get_documents_for_enrollment(enrollment_id):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id, doc_type, file_path FROM documents WHERE enrollment_id = ?", (enrollment_id,))
        docs = cursor.fetchall()
        conn.close()
        return [{"id": d[0], "doc_type": d[1], "file_path": d[2]} for d in docs]

    def delete_documents_for_enrollment(enrollment_id):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM documents WHERE enrollment_id = ?", (enrollment_id,))
        conn.commit()
        conn.close()

    def add_notification_rule(rule):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO notification_rules (rule_name, trigger, days_before, recipients, enabled)
            VALUES (?, ?, ?, ?, ?)
        """, (
            rule["rule_name"],
            rule["trigger"],
            rule.get("days_before"),
            ",".join(rule["recipients"]),
            1 if rule.get("enabled", True) else 0
        ))
        conn.commit()
        conn.close()

    def get_notification_rules():
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM notification_rules ORDER BY id DESC")
        rows = cursor.fetchall()
        columns = [col[0] for col in cursor.description]
        conn.close()
        rules = []
        for row in rows:
            r = dict(zip(columns, row))
            r["recipients"] = r["recipients"].split(",") if r["recipients"] else []
            rules.append(r)
        return rules

    def update_notification_rule(rule_id, updates: dict):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        fields = []
        values = []
        for k, v in updates.items():
            if k == 'recipients' and isinstance(v, (list, tuple)):
                v = ','.join(v)
            fields.append(f"{k} = ?")
            values.append(v)
        values.append(rule_id)
        cursor.execute(f"UPDATE notification_rules SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()
        conn.close()

    def delete_notification_rule(rule_id):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM notification_rules WHERE id = ?", (rule_id,))
        conn.commit()
        conn.close()

    def log_notification_sent(enrollment_id, rule_id):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO notifications_sent (enrollment_id, rule_id)
            VALUES (?, ?)
        """, (enrollment_id, rule_id))
        conn.commit()
        conn.close()

    def get_sent_notifications(enrollment_id):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM notifications_sent WHERE enrollment_id = ?", (enrollment_id,))
        rows = cursor.fetchall()
        columns = [col[0] for col in cursor.description]
        conn.close()
        return [dict(zip(columns, row)) for row in rows]

    def approve_enrollment(enrollment_id, approved_by="Admin"):
        """Mark an enrollment as approved with timestamp and admin name."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE enrollments 
            SET approved = 1,
                approved_at = ?,
                approved_by = ?
            WHERE id = ?
        """, (datetime.now().isoformat(), approved_by, enrollment_id))
        conn.commit()
        conn.close()
        return True

    def load_enrollments():
        """Legacy compatibility: returns all enrollments."""
        return get_all_enrollments()

    def save_enrollments(records):
        """Legacy function - no-op for compatibility."""
        pass

    init_db()
