import os
import json
from datetime import datetime

# Try to import sqlite3 — some restricted deploy envs may not have it.
try:
    import sqlite3
    USE_SQLITE = True
except Exception:
    sqlite3 = None
    USE_SQLITE = False

# ============================================================
# CONFIGURATION
# ============================================================
DATA_DIR = "data"
DB_PATH = os.path.join(DATA_DIR, "byov.db")


# ============================================================
# DATABASE INITIALIZATION
# ============================================================
def init_db():
    """Creates the database directory and tables if they don't exist."""
    try:
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR, exist_ok=True)

        if USE_SQLITE and sqlite3 is not None:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            # Create enrollments table (includes approval tracking columns)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS enrollments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_name TEXT NOT NULL,
                    tech_id TEXT NOT NULL,
                    district TEXT,
                    state TEXT,
                    referred_by TEXT,
                    industries TEXT,
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
                    approved_by TEXT
                )
            """)

            # Create documents table
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

            # Create notification rules table
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

            # Create notifications_sent table
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

            # Commit initial schema changes
            conn.commit()

            # Idempotent migration: ensure 'industry' column exists and backfill from 'industries'
            try:
                cursor.execute("PRAGMA table_info(enrollments)")
                existing_cols = [r[1] for r in cursor.fetchall()]
                if 'industry' not in existing_cols:
                    try:
                        cursor.execute("ALTER TABLE enrollments ADD COLUMN industry TEXT")
                        conn.commit()
                    except Exception:
                        pass

                # Backfill: if industry is empty but industries has data, copy it over
                try:
                    cursor.execute("SELECT id, industries, industry FROM enrollments")
                    rows = cursor.fetchall()
                    for r in rows:
                        eid = r[0]
                        industries_val = r[1]
                        industry_val = r[2]
                        if (not industry_val or industry_val == '') and industries_val:
                            try:
                                # ensure industries_val is valid JSON or plain text
                                import json as _json
                                try:
                                    parsed = _json.loads(industries_val)
                                except Exception:
                                    # if it's not JSON, assume comma-separated
                                    parsed = [x.strip() for x in str(industries_val).split(',') if x.strip()]
                                new_val = _json.dumps(parsed)
                                cursor.execute("UPDATE enrollments SET industry = ? WHERE id = ?", (new_val, eid))
                            except Exception:
                                pass
                    conn.commit()
                except Exception:
                    pass
            except Exception:
                pass

            # Idempotent migration: ensure approval tracking columns exist for older DBs
            try:
                cursor.execute("PRAGMA table_info(enrollments)")
                existing_cols = [r[1] for r in cursor.fetchall()]
                if 'approved' not in existing_cols:
                    try:
                        cursor.execute("ALTER TABLE enrollments ADD COLUMN approved INTEGER DEFAULT 0")
                    except Exception:
                        pass
                if 'approved_at' not in existing_cols:
                    try:
                        cursor.execute("ALTER TABLE enrollments ADD COLUMN approved_at TEXT")
                    except Exception:
                        pass
                if 'approved_by' not in existing_cols:
                    try:
                        cursor.execute("ALTER TABLE enrollments ADD COLUMN approved_by TEXT")
                    except Exception:
                        pass
                # Add dashboard sync columns if missing
                if 'dashboard_tech_id' not in existing_cols:
                    try:
                        cursor.execute("ALTER TABLE enrollments ADD COLUMN dashboard_tech_id TEXT")
                    except Exception:
                        pass
                if 'last_upload_report' not in existing_cols:
                    try:
                        cursor.execute("ALTER TABLE enrollments ADD COLUMN last_upload_report TEXT")
                    except Exception:
                        pass
                conn.commit()
            except Exception:
                # Non-fatal: continue even if migration check fails
                pass

            conn.close()
        else:
            # Fallback: ensure a JSON-backed store exists so importing the module
            # doesn't raise on environments without sqlite3.
            FALLBACK_FILE = os.path.join(DATA_DIR, "fallback_store.json")
            if not os.path.exists(FALLBACK_FILE):
                store = {
                    "enrollments": [],
                    "documents": [],
                    "notification_rules": [],
                    "notifications_sent": [],
                    "counters": {"enrollment_id": 0, "document_id": 0, "rule_id": 0, "sent_id": 0}
                }
                with open(FALLBACK_FILE, 'w', encoding='utf-8') as f:
                    json.dump(store, f, indent=2)
    except Exception as e:
        print(f"Error initializing database: {e}")
        # Try to create fallback store
        try:
            FALLBACK_FILE = os.path.join(DATA_DIR, "fallback_store.json")
            if not os.path.exists(FALLBACK_FILE):
                store = {
                    "enrollments": [],
                    "documents": [],
                    "notification_rules": [],
                    "notifications_sent": [],
                    "counters": {"enrollment_id": 0, "document_id": 0, "rule_id": 0, "sent_id": 0}
                }
                with open(FALLBACK_FILE, 'w', encoding='utf-8') as f:
                    json.dump(store, f, indent=2)
        except:
            pass


# Initialize DB as soon as the module is imported
init_db()


# Fallback store helpers (used when sqlite3 is not available)
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


# ============================================================
# ENROLLMENT FUNCTIONS
# ============================================================
def insert_enrollment(record):
    """Insert a new enrollment row and return its assigned ID."""
    if USE_SQLITE and sqlite3 is not None:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Prefer new 'industry' key, but fall back to legacy 'industries'
        industries_list = record.get("industry", record.get("industries", []))
        industries_json = json.dumps(industries_list)
        # Also store legacy 'industries' column for backwards compatibility
        industries_legacy_json = industries_json
        industry_json = industries_json

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
            industries_legacy_json,
            industry_json,
            record.get("year"),
            record.get("make"),
            record.get("model"),
            record.get("vin"),
            record.get("insurance_exp"),
            record.get("registration_exp"),
            record.get("template_used"),
            record.get("comment"),
            record.get("submission_date", datetime.now().isoformat()),
            0,  # approved - default to pending
            None,  # approved_at
            None  # approved_by
        ))

        enrollment_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return enrollment_id
    else:
        # JSON fallback store
        store = _load_store()
        cid = store.get('counters', {})
        cid['enrollment_id'] = cid.get('enrollment_id', 0) + 1
        eid = cid['enrollment_id']
        rec = dict(record)
        rec['id'] = eid
        # ensure industries/industry are lists
        rec['industries'] = record.get('industries', record.get('industry', []))
        rec['industry'] = record.get('industry', record.get('industries', []))
        store.setdefault('enrollments', []).insert(0, rec)
        store['counters'] = cid
        _save_store(store)
        return eid


def get_all_enrollments():
    """Return all enrollments as list[dict]."""
    if USE_SQLITE and sqlite3 is not None:
        try:
            # Ensure database is initialized
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
                # Prefer new 'industry' column if present, but populate both keys for compatibility
                if r.get("industry"):
                    try:
                        r["industry"] = json.loads(r["industry"])
                    except:
                        # if it's not JSON, convert comma-separated text to list
                        try:
                            r["industry"] = [x.strip() for x in str(r.get("industry", "")).split(',') if x.strip()]
                        except:
                            r["industry"] = []
                    # keep legacy key populated too
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
            # Fallback to JSON store if database fails
            store = _load_store()
            return store.get('enrollments', [])
    else:
        store = _load_store()
        return store.get('enrollments', [])


def get_enrollment_by_id(enrollment_id):
    """Return a single enrollment + all documents."""
    if USE_SQLITE and sqlite3 is not None:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM enrollments WHERE id = ?", (enrollment_id,))
        row = cursor.fetchone()

        if not row:
            conn.close()
            return None

        columns = [col[0] for col in cursor.description]
        record = dict(zip(columns, row))

        # Decode industries JSON
        if record.get("industries"):
            try:
                record["industries"] = json.loads(record["industries"])
            except:
                record["industries"] = []
        # If new 'industry' column exists, prefer that and populate both keys
        if record.get("industry"):
            try:
                record["industry"] = json.loads(record["industry"])
            except:
                try:
                    record["industry"] = [x.strip() for x in str(record.get("industry", "")).split(',') if x.strip()]
                except:
                    record["industry"] = []
            record["industries"] = list(record["industry"]) if isinstance(record["industry"], list) else []

        # Load related documents
        cursor.execute("SELECT id, doc_type, file_path FROM documents WHERE enrollment_id = ?", (enrollment_id,))
        docs = cursor.fetchall()

        conn.close()

        record["documents"] = [
            {"id": d[0], "doc_type": d[1], "file_path": d[2]} for d in docs
        ]
        return record
    else:
        store = _load_store()
        enrolls = store.get('enrollments', [])
        for rec in enrolls:
            if int(rec.get('id')) == int(enrollment_id):
                # attach documents
                docs = [d for d in store.get('documents', []) if int(d.get('enrollment_id')) == int(enrollment_id)]
                rec_copy = dict(rec)
                rec_copy['documents'] = docs
                return rec_copy
        return None


def update_enrollment(enrollment_id, updates: dict):
    """Update specific fields on an enrollment."""
    if USE_SQLITE and sqlite3 is not None:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        fields = []
        values = []

        for key, value in updates.items():
            if key == "industries" or key == "industry":
                # store as JSON text
                value_json = json.dumps(value)
                # update both columns when 'industry' provided for compatibility
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
    else:
        store = _load_store()
        for i, rec in enumerate(store.get('enrollments', [])):
            if int(rec.get('id')) == int(enrollment_id):
                for k, v in updates.items():
                    if k == 'industries':
                        rec['industries'] = v
                        rec['industry'] = v
                    elif k == 'industry':
                        rec['industry'] = v
                        rec['industries'] = v
                    else:
                        rec[k] = v
                store['enrollments'][i] = rec
                _save_store(store)
                return


def set_dashboard_sync_info(enrollment_id, dashboard_tech_id: str = None, report: dict = None):
    """Persist dashboard sync metadata on an enrollment (idempotent).

    - `dashboard_tech_id` is the external dashboard's technician id.
    - `report` is a dict (e.g., {photo_count: int, failed_uploads: [...]}) and will be stored as JSON text.
    """
    if USE_SQLITE and sqlite3 is not None:
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
            # best-effort only
            pass
    else:
        store = _load_store()
        for i, rec in enumerate(store.get('enrollments', [])):
            if int(rec.get('id')) == int(enrollment_id):
                if dashboard_tech_id is not None:
                    rec['dashboard_tech_id'] = str(dashboard_tech_id)
                if report is not None:
                    rec['last_upload_report'] = report
                store['enrollments'][i] = rec
                _save_store(store)
                return


def delete_enrollment(enrollment_id):
    """Delete enrollment + all documents."""
    if USE_SQLITE and sqlite3 is not None:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # CASCADE handles documents automatically
        cursor.execute("DELETE FROM enrollments WHERE id = ?", (enrollment_id,))
        conn.commit()
        conn.close()
    else:
        store = _load_store()
        store['enrollments'] = [r for r in store.get('enrollments', []) if int(r.get('id')) != int(enrollment_id)]
        # remove documents
        store['documents'] = [d for d in store.get('documents', []) if int(d.get('enrollment_id')) != int(enrollment_id)]
        _save_store(store)


# ============================================================
# DOCUMENT FUNCTIONS
# ============================================================
def add_document(enrollment_id, doc_type, file_path):
    if USE_SQLITE and sqlite3 is not None:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO documents (enrollment_id, doc_type, file_path)
            VALUES (?, ?, ?)
        """, (enrollment_id, doc_type, file_path))

        conn.commit()
        conn.close()
    else:
        store = _load_store()
        cid = store.get('counters', {})
        cid['document_id'] = cid.get('document_id', 0) + 1
        did = cid['document_id']
        doc = {'id': did, 'enrollment_id': int(enrollment_id), 'doc_type': doc_type, 'file_path': file_path}
        store.setdefault('documents', []).append(doc)
        store['counters'] = cid
        _save_store(store)


def get_documents_for_enrollment(enrollment_id):
    if USE_SQLITE and sqlite3 is not None:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT id, doc_type, file_path FROM documents WHERE enrollment_id = ?", (enrollment_id,))
        docs = cursor.fetchall()

        conn.close()

        return [{"id": d[0], "doc_type": d[1], "file_path": d[2]} for d in docs]
    else:
        store = _load_store()
        return [d for d in store.get('documents', []) if int(d.get('enrollment_id')) == int(enrollment_id)]


def delete_documents_for_enrollment(enrollment_id):
    if USE_SQLITE and sqlite3 is not None:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM documents WHERE enrollment_id = ?", (enrollment_id,))
        conn.commit()
        conn.close()
    else:
        store = _load_store()
        store['documents'] = [d for d in store.get('documents', []) if int(d.get('enrollment_id')) != int(enrollment_id)]
        _save_store(store)


# ============================================================
# NOTIFICATION RULES
# ============================================================
def add_notification_rule(rule):
    if USE_SQLITE and sqlite3 is not None:
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
    else:
        store = _load_store()
        cid = store.get('counters', {})
        cid['rule_id'] = cid.get('rule_id', 0) + 1
        rid = cid['rule_id']
        r = {
            'id': rid,
            'rule_name': rule.get('rule_name'),
            'trigger': rule.get('trigger'),
            'days_before': rule.get('days_before'),
            'recipients': rule.get('recipients', []),
            'enabled': 1 if rule.get('enabled', True) else 0
        }
        store.setdefault('notification_rules', []).append(r)
        store['counters'] = cid
        _save_store(store)


def get_notification_rules():
    if USE_SQLITE and sqlite3 is not None:
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
    else:
        store = _load_store()
        return store.get('notification_rules', [])


def update_notification_rule(rule_id, updates: dict):
    if USE_SQLITE and sqlite3 is not None:
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
    else:
        store = _load_store()
        for i, r in enumerate(store.get('notification_rules', [])):
            if int(r.get('id')) == int(rule_id):
                for k, v in updates.items():
                    if k == 'recipients' and isinstance(v, (list, tuple)):
                        r[k] = list(v)
                    else:
                        r[k] = v
                store['notification_rules'][i] = r
                _save_store(store)
                return


def delete_notification_rule(rule_id):
    if USE_SQLITE and sqlite3 is not None:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM notification_rules WHERE id = ?", (rule_id,))
        conn.commit()
        conn.close()
    else:
        store = _load_store()
        store['notification_rules'] = [r for r in store.get('notification_rules', []) if int(r.get('id')) != int(rule_id)]
        _save_store(store)


# ============================================================
# SENT NOTIFICATIONS
# ============================================================
def log_notification_sent(enrollment_id, rule_id):
    if USE_SQLITE and sqlite3 is not None:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO notifications_sent (enrollment_id, rule_id)
            VALUES (?, ?)
        """, (enrollment_id, rule_id))

        conn.commit()
        conn.close()
    else:
        store = _load_store()
        cid = store.get('counters', {})
        cid['sent_id'] = cid.get('sent_id', 0) + 1
        sid = cid['sent_id']
        rec = {'id': sid, 'enrollment_id': int(enrollment_id), 'rule_id': int(rule_id), 'sent_at': datetime.now().isoformat()}
        store.setdefault('notifications_sent', []).append(rec)
        store['counters'] = cid
        _save_store(store)


def get_sent_notifications(enrollment_id):
    if USE_SQLITE and sqlite3 is not None:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM notifications_sent WHERE enrollment_id = ?", (enrollment_id,))
        rows = cursor.fetchall()

        columns = [col[0] for col in cursor.description]
        conn.close()

        return [dict(zip(columns, row)) for row in rows]
    else:
        store = _load_store()
        return [r for r in store.get('notifications_sent', []) if int(r.get('enrollment_id')) == int(enrollment_id)]


# ============================================================
# APPROVAL TRACKING
# ============================================================
def approve_enrollment(enrollment_id, approved_by="Admin"):
    """Mark an enrollment as approved with timestamp and admin name."""
    if USE_SQLITE and sqlite3 is not None:
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
    else:
        # JSON fallback
        store = _load_store()
        for rec in store.get('enrollments', []):
            if int(rec.get('id')) == int(enrollment_id):
                rec['approved'] = 1
                rec['approved_at'] = datetime.now().isoformat()
                rec['approved_by'] = approved_by
                break
        _save_store(store)
        return True


# ============================================================
# COMPATIBILITY LAYER (for older JSON-based calls)
# ============================================================
def load_enrollments():
    """Legacy compatibility: returns all enrollments."""
    return get_all_enrollments()


def save_enrollments(records):
    """
    Legacy function kept so the app doesn't break.
    You SHOULD NOT use this anymore.
    """
    pass  # No-op or could be used to import old JSON data
