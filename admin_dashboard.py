import os
import streamlit as st
from datetime import datetime
import database
from notifications import send_email_notification

try:
    import sqlite3
except Exception:
    sqlite3 = None

# ------------------------------------------------------------
# Helper: fetch all enrollments & sent notifications
# ------------------------------------------------------------
def _get_all_enrollments():
    return database.get_all_enrollments()


def _get_all_sent_notifications():
    # Returns list of dicts: {id, enrollment_id, rule_id, sent_at}
    # SQLite direct query for efficiency; fallback aggregates JSON store.
    if database.USE_SQLITE and sqlite3:
        try:
            conn = sqlite3.connect(database.DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT id,enrollment_id,rule_id,sent_at FROM notifications_sent ORDER BY sent_at DESC")
            rows = cur.fetchall()
            conn.close()
            return [
                {"id": r[0], "enrollment_id": r[1], "rule_id": r[2], "sent_at": r[3]} for r in rows
            ]
        except Exception:
            return []
    else:
        # Fallback: iterate each enrollment and collect
        sent = []
        enrolls = _get_all_enrollments()
        for e in enrolls:
            eid = e.get('id')
            for s in database.get_sent_notifications(eid):
                sent.append(s)
        # Sort newest first
        sent.sort(key=lambda x: x.get('sent_at',''), reverse=True)
        return sent


# ------------------------------------------------------------
# UI Components
# ------------------------------------------------------------
def _overview_tab(enrollments, rules, sent):
    st.subheader("Overview")

    total_enrollments = len(enrollments)
    active_rules = sum(1 for r in rules if r.get('enabled'))
    total_notifications = len(sent)
    storage_mode = "SQLite" if database.USE_SQLITE else "JSON Fallback"



    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Enrollments", total_enrollments)
    c2.metric("Active Rules", active_rules)
    c3.metric("Emails Logged", total_notifications)
    c4.metric("Storage Mode", storage_mode)

    if not database.USE_SQLITE:
        st.warning("Running in JSON fallback storage mode. Some features may be limited.")

    # Recent activity (last 5 notifications)
    if sent:
        st.markdown("### Recent Notifications")
        recent = sent[:5]
        rule_lookup = {r.get('id'): r.get('rule_name') for r in rules}
        for n in recent:
            rid = n.get('rule_id')
            rname = rule_lookup.get(rid, f"Rule {rid}")
            st.write(f"• {n.get('sent_at','')} — {rname} (Enrollment #{n.get('enrollment_id')})")
    else:
        st.info("No notifications have been sent yet.")


def _enrollments_tab(enrollments):
    from st_aggrid import AgGrid, GridOptionsBuilder
    import pandas as pd
    from datetime import datetime
    import shutil

    st.subheader("Enrollments")

    if not enrollments:
        st.info("No enrollments yet.")
        return

    # -----------------------------
    # State (search, pagination, etc.)
    # -----------------------------
    st.session_state.setdefault('ecc_search', '')
    st.session_state.setdefault('ecc_page', 0)
    st.session_state.setdefault('ecc_page_size', 10)
    st.session_state.setdefault('ecc_view_id', None)
    st.session_state.setdefault('ecc_edit_id', None)
    st.session_state.setdefault('ecc_delete_id', None)

    # -----------------------------
    # Search
    # -----------------------------
    q = st.text_input("Search (Name, Tech ID, VIN)", value=st.session_state.ecc_search)
    st.session_state.ecc_search = q

    filtered = []
    for r in enrollments:
        if not q:
            filtered.append(r)
            continue
        
        hay = ' '.join([str(r.get(k, '')).lower() for k in ('full_name', 'tech_id', 'vin')])
        if q.lower() in hay:
            filtered.append(r)

    # -----------------------------
    # Pagin1FTLR4FEXAPA20178ation
    # -----------------------------
    total = len(filtered)
    page_size = st.session_state.ecc_page_size
    page = st.session_state.ecc_page
    max_page = max(0, (total - 1) // page_size)

    cnav1, cnav2, cnav3 = st.columns([1, 1, 4])
    with cnav1:
        if st.button("◀ Prev", disabled=page <= 0):
            st.session_state.ecc_page = max(0, page - 1)
            st.rerun()
    with cnav2:
        if st.button("Next ▶", disabled=page >= max_page):
            st.session_state.ecc_page = min(max_page, page + 1)
            st.rerun()
    with cnav3:
        st.write(f"Page {page+1} of {max_page+1} — {total} records")

    start = page * page_size
    end = start + page_size
    page_rows = filtered[start:end]

    # -----------------------------
    # AG-Grid Table
    # -----------------------------
    df = pd.DataFrame(page_rows)

    # Keep the 'id' column for deletion tracking but move unwanted columns
    columns_to_hide = ["comment", "template_used"]
    for col in columns_to_hide:
        if col in df.columns:
            df.drop(columns=[col], inplace=True)

    # Format submission date
    if "submission_date" in df.columns:
        df["submission_date"] = df["submission_date"].apply(
            lambda d: datetime.fromisoformat(d).strftime("%m/%d/%Y") if d else ""
        )

    # Build grid with selection enabled
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(
        resizable=True,
        filter=True,
        sortable=True,
    )
    
    # Enable row selection with checkboxes
    gb.configure_selection(
        selection_mode='multiple',
        use_checkbox=True,
        header_checkbox=True,
        pre_selected_rows=[]
    )
    
    # Hide the 'id' column but keep it in data
    gb.configure_column("id", hide=True)

    # Match pagination in Streamlit with pagination inside AG-Grid
    gb.configure_pagination(
        paginationAutoPageSize=False,
        paginationPageSize=page_size,
    )

    grid = AgGrid(
        df,
        gridOptions=gb.build(),
        theme="alpine",
        fit_columns_on_grid_load=True,
        allow_unsafe_jscode=True,
        update_mode='SELECTION_CHANGED'
    )
    
    # -----------------------------
    # Delete Selected Enrollments
    # -----------------------------
    selected_rows = grid.get('selected_rows', [])
    
    if selected_rows is not None and len(selected_rows) > 0:
        st.warning(f"⚠️ {len(selected_rows)} enrollment(s) selected")
        
        col1, col2 = st.columns([1, 5])
        with col1:
            if st.button("🗑️ Delete Selected", type="primary"):
                deleted_count = 0
                files_deleted = 0
                
                for selected in selected_rows:
                    enrollment_id = selected.get('id')
                    tech_id = selected.get('tech_id', 'unknown')
                    
                    try:
                        # Get documents to find file paths
                        docs = database.get_documents_for_enrollment(enrollment_id)
                        
                        # Delete uploaded files
                        for doc in docs:
                            file_path = doc.get('file_path')
                            if file_path and os.path.exists(file_path):
                                try:
                                    os.remove(file_path)
                                    files_deleted += 1
                                except Exception:
                                    pass
                        
                        # Delete upload directory for this enrollment
                        upload_dirs = [
                            f"uploads/{tech_id}_{uuid}" 
                            for uuid in os.listdir('uploads') 
                            if os.path.isdir(f"uploads/{uuid}") and tech_id in uuid
                        ] if os.path.exists('uploads') else []
                        
                        for upload_dir in upload_dirs:
                            if os.path.exists(upload_dir):
                                try:
                                    shutil.rmtree(upload_dir)
                                except Exception:
                                    pass
                        
                        # Delete generated PDF if exists
                        pdf_patterns = [
                            f"pdfs/{tech_id}_{uuid}.pdf"
                            for uuid in os.listdir('pdfs')
                            if tech_id in uuid and uuid.endswith('.pdf')
                        ] if os.path.exists('pdfs') else []
                        
                        for pdf_path in pdf_patterns:
                            if os.path.exists(pdf_path):
                                try:
                                    os.remove(pdf_path)
                                    files_deleted += 1
                                except Exception:
                                    pass
                        
                        # Delete from database (this also deletes documents via CASCADE)
                        database.delete_enrollment(enrollment_id)
                        deleted_count += 1
                        
                    except Exception as e:
                        st.error(f"Error deleting enrollment {enrollment_id}: {e}")
                
                if deleted_count > 0:
                    st.success(f"✅ Deleted {deleted_count} enrollment(s) and {files_deleted} file(s)")
                    st.rerun()
        
        with col2:
            st.caption("This will permanently delete the selected enrollments and all associated files")

    # -----------------------------
    # Enrollment selector (unchanged)
    # -----------------------------
    st.markdown("---")
    options = [f"#{e.get('id')} — {e.get('full_name')} ({e.get('tech_id')})" for e in enrollments]
    selected_label = st.selectbox("Select enrollment for rule actions", options) if options else None

    if selected_label:
        try:
            selected_id = int(selected_label.split('—')[0].strip('# ').strip())
            st.session_state.selected_enrollment_id = selected_id
        except Exception:
            st.session_state.selected_enrollment_id = None





def _notifications_tab(enrollments, rules, sent):
    st.subheader("Notifications Log")
    if not sent:
        st.info("No notifications logged yet.")
        return
    rule_lookup = {r.get('id'): r.get('rule_name') for r in rules}
    enroll_lookup = {e.get('id'): e for e in enrollments}

    # Simple table
    for n in sent:
        rname = rule_lookup.get(n.get('rule_id'), f"Rule {n.get('rule_id')}")
        enroll = enroll_lookup.get(n.get('enrollment_id'))
        tech = enroll.get('tech_id') if enroll else 'N/A'
        fname = enroll.get('full_name') if enroll else 'Unknown'
        st.write(f"• {n.get('sent_at','')} — {rname} → {fname} ({tech})")

    if st.button("Refresh Log"):
        st.rerun()


# ------------------------------------------------------------
# Entry Point
# ------------------------------------------------------------
def page_admin_control_center():
    st.title("BYOV Admin Control Center")
    st.caption("Operational oversight: enrollments, rules, notifications")

    # Load data once for all tabs
    enrollments = _get_all_enrollments()
    rules = database.get_notification_rules()
    sent = _get_all_sent_notifications()

    tabs = st.tabs(["Overview", "Enrollments", "Notifications Log"])

    with tabs[0]:
        _overview_tab(enrollments, rules, sent)
    with tabs[1]:
        _enrollments_tab(enrollments)
    with tabs[2]:
        _notifications_tab(enrollments, rules, sent)

    st.markdown("---")
    st.caption("Select an enrollment in the Enrollments tab before running a rule.")


if __name__ == '__main__':
    page_admin_control_center()
