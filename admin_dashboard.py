import os
import streamlit as st
from datetime import datetime
import database
from notifications import send_email_notification
import shutil
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode

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
    import pandas as pd

    st.subheader("Enrollments")

    # -----------------------------
    # No enrollments
    # -----------------------------
    if not enrollments:
        st.info("No enrollments yet.")
        return

    # -----------------------------
    # Session state
    # -----------------------------
    st.session_state.setdefault("ecc_search", "")
    st.session_state.setdefault("ecc_page", 0)
    st.session_state.setdefault("ecc_page_size", 10)
    st.session_state.setdefault("open_photos_for_id", None)

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
        hay = " ".join([str(r.get(k, "")).lower() for k in ("full_name", "tech_id", "vin")])
        if q.lower() in hay:
            filtered.append(r)

    # -----------------------------
    # Pagination
    # -----------------------------
    total = len(filtered)
    page_size = st.session_state.ecc_page_size
    page = st.session_state.ecc_page
    max_page = max(0, (total - 1) // page_size)

    col_prev, col_next, col_info = st.columns([1, 1, 4])
    with col_prev:
        if st.button("◀ Prev", disabled=page <= 0):
            st.session_state.ecc_page = max(0, page - 1)
            st.rerun()

    with col_next:
        if st.button("Next ▶", disabled=page >= max_page):
            st.session_state.ecc_page = min(max_page, page + 1)
            st.rerun()

    with col_info:
        st.write(f"Page {page+1} of {max_page+1} — {total} records")

    start = page * page_size
    end = start + page_size
    page_rows = filtered[start:end]

    # -----------------------------
    # DataFrame + formatting
    # -----------------------------
    df = pd.DataFrame(page_rows)

    # Add photos column for button renderer
    df["photos"] = ""

    if "submission_date" in df.columns:
        df["submission_date"] = df["submission_date"].apply(
            lambda d: datetime.fromisoformat(d).strftime("%m/%d/%Y") if d else ""
        )

    # -----------------------------
    # AG-Grid Button Renderer
    # -----------------------------
    photo_btn_js = JsCode(
        """
        function(params) {
            return `
              <button 
                style="
                  background-color:#1e88e5;
                  color:white;
                  padding:4px 10px;
                  border:none;
                  border-radius:4px;
                  cursor:pointer;
                  font-weight:600;
                ">
                📸 View
              </button>
            `;
        }
        """
    )

    # -----------------------------
    # Build Grid Options
    # -----------------------------
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(resizable=True, filter=True, sortable=True)
    gb.configure_selection("multiple", use_checkbox=True, header_checkbox=True)
    gb.configure_column("id", hide=True)
    
    # Hide unwanted columns
    for col in ["comment", "template_used"]:
        if col in df.columns:
            gb.configure_column(col, hide=True)

    # Add Photos action column
    gb.configure_column(
        "photos",
        headerName="Photos",
        cellRenderer=photo_btn_js,
        width=120,
        pinned="right",
    )

    gb.configure_pagination(False, page_size)

    grid_resp = AgGrid(
        df,
        gridOptions=gb.build(),
        allow_unsafe_jscode=True,
        update_mode="SELECTION_CHANGED",
        fit_columns_on_grid_load=True,
        theme="alpine",
    )

    # -----------------------------
    # Row click → Open modal
    # -----------------------------
    selected = grid_resp.get("selected_rows", [])
    
    # Check for single row selection to view photos
    if selected and len(selected) == 1:
        sel = selected[0]
        # Only open modal if it's not already open for this enrollment
        if st.session_state.open_photos_for_id != sel["id"]:
            st.session_state.open_photos_for_id = sel["id"]
            st.rerun()
    
    # -----------------------------
    # Delete Selected Enrollments
    # -----------------------------
    if selected and len(selected) > 0:
        st.markdown("---")
        st.warning(f"⚠️ {len(selected)} enrollment(s) selected")
        
        col1, col2 = st.columns([1, 5])
        with col1:
            if st.button("🗑️ Delete Selected", type="primary", key="delete_selected_btn"):
                deleted_count = 0
                files_deleted = 0
                
                for sel_row in selected:
                    enrollment_id = sel_row.get('id')
                    tech_id = sel_row.get('tech_id', 'unknown')
                    
                    try:
                        # Get documents to find file paths
                        docs = database.get_documents_for_enrollment(enrollment_id)
                        
                        # Delete individual uploaded files tracked in database
                        for doc in docs:
                            file_path = doc.get('file_path')
                            if file_path and os.path.exists(file_path):
                                try:
                                    os.remove(file_path)
                                    files_deleted += 1
                                except Exception:
                                    pass
                        
                        # Delete upload folder for this enrollment (pattern: uploads/techid_uuid/)
                        if os.path.exists('uploads'):
                            upload_folder_prefix = f"{tech_id}_"
                            for folder in os.listdir('uploads'):
                                if folder.startswith(upload_folder_prefix):
                                    folder_path = os.path.join('uploads', folder)
                                    if os.path.isdir(folder_path):
                                        try:
                                            shutil.rmtree(folder_path, ignore_errors=True)
                                        except Exception:
                                            pass
                        
                        # Delete generated PDF (pattern: pdfs/techid_uuid.pdf)
                        if os.path.exists('pdfs'):
                            pdf_prefix = f"{tech_id}_"
                            for pdf_file in os.listdir('pdfs'):
                                if pdf_file.startswith(pdf_prefix) and pdf_file.endswith('.pdf'):
                                    pdf_path = os.path.join('pdfs', pdf_file)
                                    try:
                                        os.remove(pdf_path)
                                        files_deleted += 1
                                    except Exception:
                                        pass
                        
                        # Delete from database (CASCADE deletes related documents)
                        database.delete_enrollment(enrollment_id)
                        deleted_count += 1
                        
                    except Exception as e:
                        st.error(f"Error deleting enrollment {enrollment_id}: {e}")
                
                if deleted_count > 0:
                    st.success(f"✅ Successfully deleted {deleted_count} enrollment(s)")
                    st.rerun()
        
        with col2:
            st.caption("⚠️ This will permanently delete the selected enrollments and all associated files")

    # -----------------------------
    # Photo Modal
    # -----------------------------
    if st.session_state.open_photos_for_id:
        enrollment_id = st.session_state.open_photos_for_id

        docs = database.get_documents_for_enrollment(enrollment_id)

        vehicle = [d["file_path"] for d in docs if d["doc_type"] == "vehicle"]
        registration = [d["file_path"] for d in docs if d["doc_type"] == "registration"]
        insurance = [d["file_path"] for d in docs if d["doc_type"] == "insurance"]

        # Modal overlay
        st.markdown(
            """
            <style>
            .modal-overlay {
                position: fixed;
                top: 0; left: 0;
                width: 100vw;
                height: 100vh;
                background: rgba(0,0,0,0.75);
                z-index: 9998;
            }
            .modal-container {
                position: fixed;
                top: 50%; 
                left: 50%;
                transform: translate(-50%, -50%);
                background: white;
                padding: 30px;
                border-radius: 12px;
                width: 85vw;
                max-height: 85vh;
                overflow-y: auto;
                z-index: 9999;
            }
            </style>
            <div class="modal-overlay"></div>
            """,
            unsafe_allow_html=True,
        )

        with st.container():
            st.markdown("<div class='modal-container'>", unsafe_allow_html=True)

            tabs = st.tabs(["🚗 Vehicle", "📄 Registration", "🛡️ Insurance"])
            groups = [vehicle, registration, insurance]
            labels = ["Vehicle", "Registration", "Insurance"]

            for tab, paths, label in zip(tabs, groups, labels):
                with tab:
                    if paths:
                        for i in range(0, len(paths), 3):
                            cols = st.columns(3)
                            for j, col in enumerate(cols):
                                idx = i + j
                                if idx < len(paths):
                                    p = paths[idx]
                                    if os.path.exists(p):
                                        with col:
                                            st.image(p, use_container_width=True)
                                            st.caption(os.path.basename(p))
                                    else:
                                        with col:
                                            st.error(f"Missing: {p}")
                    else:
                        st.info(f"No {label.lower()} photos found.")

            # Close button
            st.markdown("<br>", unsafe_allow_html=True)
            c1, c2, c3 = st.columns([2,1,2])
            with c2:
                if st.button("Close", type="primary"):
                    st.session_state.open_photos_for_id = None
                    st.rerun()

            st.markdown("</div>", unsafe_allow_html=True)

    # -----------------------------
    # Footer: Enrollment Selector
    # -----------------------------
    st.markdown("---")
    options = [
        f"#{e.get('id')} — {e.get('full_name')} ({e.get('tech_id')})"
        for e in enrollments
    ]
    sel_label = st.selectbox("Select enrollment for rule actions", options) if options else None

    if sel_label:
        try:
            st.session_state.selected_enrollment_id = int(
                sel_label.split("—")[0].strip("# ").strip()
            )
        except:
            st.session_state.selected_enrollment_id = None

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

    tabs = st.tabs(["Overview", "Enrollments"])

    with tabs[0]:
        _overview_tab(enrollments, rules, sent)
    with tabs[1]:
        _enrollments_tab(enrollments)

    st.markdown("---")
    st.caption("Select an enrollment in the Enrollments tab before running a rule.")


if __name__ == '__main__':
    page_admin_control_center()
