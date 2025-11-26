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
def _overview_tab(enrollments):
    st.subheader("Overview")

    total_enrollments = len(enrollments)
    storage_mode = "SQLite" if database.USE_SQLITE else "JSON Fallback"

    c1, c2 = st.columns(2)
    c1.metric("Total Enrollments", total_enrollments)
    c2.metric("Storage Mode", storage_mode)

    if not database.USE_SQLITE:
        st.warning("Running in JSON fallback storage mode. Some features may be limited.")
    
    st.markdown("---")
    st.info("Use the Enrollments tab to view and manage all enrollments.")


def _enrollments_tab(enrollments):
    import pandas as pd

    st.subheader("Enrollments")

    # Diagnostics: Dashboard connectivity test
    with st.expander("Diagnostics: Dashboard Connectivity", expanded=False):
        st.caption("Verify Replit dashboard login and API availability.")
        if st.button("🔌 Test Dashboard Login", key="test_dashboard_login", type="secondary"):
            try:
                from byov_app import post_to_dashboard
                # Minimal record with required keys to trigger login only
                test_record = {
                    "tech_id": "TEST-CONNECTION",
                    "full_name": "Connectivity Test",
                    "state": "CA",
                    "district": "00",
                    "make": "Test",
                    "model": "Test",
                    "year": "2025",
                    "vin": "TESTVIN0000000000",
                    "submission_date": datetime.now().isoformat()
                }
                result = post_to_dashboard(test_record)
                if result.get("status") in ("created", "exists"):
                    st.success("✅ Dashboard reachable and authenticated successfully.")
                elif result.get("error"):
                    st.error(f"❌ Login or API error: {result.get('error')}\n{result.get('body','')}")
                elif result.get("skipped"):
                    st.warning(f"⚠️ Skipped: {result.get('skipped')}")
                else:
                    st.info(f"ℹ️ Result: {result}")
            except Exception as e:
                st.error(f"Unexpected error during connectivity test: {e}")

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
    st.session_state.setdefault("selected_enrollment_ids", set())
    st.session_state.setdefault("delete_confirm", {})

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
    # Build DataFrame for Display - 10 Columns
    # -----------------------------
    display_rows = []
    for row in page_rows:
        # Transform industries to comma-separated string
        industries_raw = row.get('industries', [])
        if isinstance(industries_raw, list):
            industries_str = ", ".join(industries_raw) if industries_raw else "None"
        else:
            industries_str = str(industries_raw)
        
        # Format vehicle info (Year, Make & Model)
        vehicle_info = f"{row.get('year', '')} {row.get('make', '')} {row.get('model', '')}".strip()
        
        # Format enrollment date from ISO to MM/DD/YYYY
        submission_date = row.get('submission_date', '')
        date_enrolled = 'N/A'
        if submission_date:
            try:
                dt = datetime.fromisoformat(submission_date)
                date_enrolled = dt.strftime("%m/%d/%Y")
            except Exception:
                date_enrolled = submission_date
        
        # Format registration expiration date
        reg_exp = row.get('registration_exp', '')
        if reg_exp:
            try:
                dt = datetime.fromisoformat(reg_exp)
                reg_exp = dt.strftime("%m/%d/%Y")
            except Exception:
                pass
        else:
            reg_exp = 'N/A'
        
        # Format insurance expiration date
        ins_exp = row.get('insurance_exp', '')
        if ins_exp:
            try:
                dt = datetime.fromisoformat(ins_exp)
                ins_exp = dt.strftime("%m/%d/%Y")
            except Exception:
                pass
        else:
            ins_exp = 'N/A'
        
        # Approved status
        approved_status = "Yes" if row.get('approved', 0) == 1 else "No"
        
        display_rows.append({
            'Name': row.get('full_name', 'N/A'),
            'Tech ID': row.get('tech_id', 'N/A'),
            'District': row.get('district', 'N/A'),
            'VIN': row.get('vin', 'N/A'),
            'Vehicle': vehicle_info,
            'Industries': industries_str,
            'Date Enrolled': date_enrolled,
            'Reg Exp': reg_exp,
            'Ins Exp': ins_exp,
            'Approved': approved_status
        })
    
    # Display table with dataframe
    if display_rows:
        df = pd.DataFrame(display_rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        st.subheader("Actions")
        
        # -----------------------------
        # Action Buttons for Each Row
        # -----------------------------
        for row in page_rows:
            enrollment_id = row.get('id')
            row_name = f"{row.get('full_name', 'N/A')} (Tech ID: {row.get('tech_id', 'N/A')})"
            
            # Custom CSS for this enrollment card
            st.markdown(f"""
            <style>
            div[data-testid="stHorizontalBlock"] button {{
                border-radius: 8px;
                font-weight: 500;
                transition: all 0.3s ease;
            }}
            </style>
            """, unsafe_allow_html=True)
            
            with st.container():
                # Enhanced header with badge styling
                vehicle_info = f"{row.get('year', '')} {row.get('make', '')} {row.get('model', '')}".strip()
                st.markdown(f"""
                <div style="
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    padding: 15px 20px;
                    border-radius: 10px;
                    margin-bottom: 15px;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                ">
                    <h3 style="color: white; margin: 0; font-size: 18px;">
                        Enrollment #{enrollment_id} — {row_name}
                    </h3>
                    <p style="color: rgba(255,255,255,0.9); margin: 5px 0 0 0; font-size: 14px;">
                        🚗 {vehicle_info} | 📍 District {row.get('district', 'N/A')}
                    </p>
                </div>
                """, unsafe_allow_html=True)
                
                cols = st.columns([2.2, 3.2, 3.7, 2.7, 2.7, 2.2])
                
                # Select button
                with cols[0]:
                    is_selected = enrollment_id in st.session_state.selected_enrollment_ids
                    btn_label = "✅ Selected" if is_selected else "⭕ Select"
                    btn_type = "primary" if is_selected else "secondary"
                    if st.button(btn_label, key=f"select_{enrollment_id}", type=btn_type, use_container_width=True):
                        if is_selected:
                            st.session_state.selected_enrollment_ids.discard(enrollment_id)
                        else:
                            st.session_state.selected_enrollment_ids.add(enrollment_id)
                        st.rerun()
                
                # View Photos button
                with cols[1]:
                    if st.button("🖼️ View Photos", key=f"view_photos_{enrollment_id}", use_container_width=True, type="secondary"):
                        st.session_state.open_photos_for_id = enrollment_id
                        st.rerun()
                
                # View PDF button
                with cols[2]:
                    # Get signed PDF from documents
                    docs = database.get_documents_for_enrollment(enrollment_id)
                    pdf_docs = [d for d in docs if d['doc_type'] == 'signature']
                    if pdf_docs and os.path.exists(pdf_docs[0]['file_path']):
                        with open(pdf_docs[0]['file_path'], 'rb') as f:
                            pdf_bytes = f.read()
                        st.download_button(
                            label="⬇️ Download PDF",
                            data=pdf_bytes,
                            file_name=f"BYOV_{row.get('tech_id', 'enrollment')}_{enrollment_id}.pdf",
                            mime="application/pdf",
                            key=f"download_pdf_{enrollment_id}",
                            use_container_width=True,
                            type="secondary"
                        )
                    else:
                        st.button("📄 No PDF", key=f"no_pdf_{enrollment_id}", disabled=True, use_container_width=True)
                
                # Approve button - Sends to dashboard
                with cols[3]:
                    # Check if already approved
                    is_approved = row.get('approved', 0) == 1
                    
                    if is_approved:
                        # Show approved badge instead of button
                        st.markdown(
                            '<div style="background: #10b981; color: white; padding: 8px 12px; '
                            'border-radius: 10px; text-align: center; font-weight: 600; font-size: 12px;">'
                            '✅ Approved</div>',
                            unsafe_allow_html=True
                        )
                    else:
                        # Show approve button
                        if st.button("✅ Approve", key=f"approve_{enrollment_id}", type="primary", use_container_width=True):
                            # Import the dashboard posting function
                            from byov_app import post_to_dashboard
                            
                            # Convert enrollment to record format
                            record = dict(row)
                            
                            # Attempt to post to dashboard
                            sync_result = post_to_dashboard(record)
                            
                            if sync_result.get("status") == "created":
                                # Mark as approved in database
                                database.approve_enrollment(enrollment_id)
                                st.success(f"✅ Enrollment #{enrollment_id} approved and sent to dashboard!")
                                st.rerun()
                            elif sync_result.get("status") == "exists":
                                # Mark as approved even if already exists
                                database.approve_enrollment(enrollment_id)
                                st.info(f"ℹ️ Enrollment #{enrollment_id} already exists on dashboard - marked as approved")
                                st.rerun()
                            elif sync_result.get("skipped"):
                                st.warning(f"⚠️ Dashboard sync skipped: {sync_result.get('skipped')}")
                            else:
                                st.error(f"❌ Dashboard sync error: {sync_result.get('error', 'Unknown error')}")
                
                # Delete button
                with cols[4]:
                    is_confirming = st.session_state.delete_confirm.get(enrollment_id, False)
                    btn_label = "⚠️ Confirm Delete" if is_confirming else "🗑️ Delete"
                    
                    if st.button(btn_label, key=f"delete_{enrollment_id}", type="secondary", use_container_width=True):
                        if is_confirming:
                            # Second click - execute delete
                            try:
                                tech_id = row.get('tech_id', 'unknown')
                                
                                # Get documents
                                docs = database.get_documents_for_enrollment(enrollment_id)
                                
                                # Delete files
                                for doc in docs:
                                    file_path = doc.get('file_path')
                                    if file_path and os.path.exists(file_path):
                                        try:
                                            os.remove(file_path)
                                        except Exception:
                                            pass
                                
                                # Delete upload folder
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
                                
                                # Delete PDF
                                if os.path.exists('pdfs'):
                                    pdf_prefix = f"{tech_id}_"
                                    for pdf_file in os.listdir('pdfs'):
                                        if pdf_file.startswith(pdf_prefix) and pdf_file.endswith('.pdf'):
                                            pdf_path = os.path.join('pdfs', pdf_file)
                                            try:
                                                os.remove(pdf_path)
                                            except Exception:
                                                pass
                                
                                # Delete from database
                                database.delete_enrollment(enrollment_id)
                                
                                # Clear confirmation state
                                st.session_state.delete_confirm.pop(enrollment_id, None)
                                st.success(f"✅ Deleted enrollment {enrollment_id}")
                                st.rerun()
                                
                            except Exception as e:
                                st.error(f"Error deleting enrollment {enrollment_id}: {e}")
                        else:
                            # First click - set confirmation
                            st.session_state.delete_confirm[enrollment_id] = True
                            st.rerun()
                
                st.markdown("<br>", unsafe_allow_html=True)
    
    # -----------------------------
    # Photo Modal (Displayed at Bottom)
    # -----------------------------
    if st.session_state.open_photos_for_id:
        enrollment_id = st.session_state.open_photos_for_id

        docs = database.get_documents_for_enrollment(enrollment_id)

        vehicle = [d["file_path"] for d in docs if d["doc_type"] == "vehicle"]
        registration = [d["file_path"] for d in docs if d["doc_type"] == "registration"]
        insurance = [d["file_path"] for d in docs if d["doc_type"] == "insurance"]
        signature_pdf = [d["file_path"] for d in docs if d["doc_type"] == "signature"]

        st.markdown("---")
        st.markdown("### 📸 Photo & Document Viewer")
        
        # Close button at top
        col1, col2 = st.columns([6, 1])
        with col2:
            if st.button("✖ Close", key=f"close_modal_top_{enrollment_id}", type="primary"):
                st.session_state.open_photos_for_id = None
                st.rerun()

        tabs = st.tabs(["📄 Signed PDF", "🚗 Vehicle", "📋 Registration", "🛡️ Insurance"])
        
        # PDF Tab
        with tabs[0]:
            if signature_pdf and os.path.exists(signature_pdf[0]):
                with open(signature_pdf[0], 'rb') as f:
                    pdf_bytes = f.read()
                
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.info(f"📄 {os.path.basename(signature_pdf[0])}")
                with col2:
                    st.download_button(
                        label="⬇️ Download PDF",
                        data=pdf_bytes,
                        file_name=os.path.basename(signature_pdf[0]),
                        mime="application/pdf",
                        key=f"download_pdf_modal_{enrollment_id}",
                        use_container_width=True
                    )
                
                # Display PDF using iframe
                import base64
                base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
                pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="800" type="application/pdf"></iframe>'
                st.markdown(pdf_display, unsafe_allow_html=True)
            else:
                st.warning("No signed PDF found for this enrollment.")
        
        groups = [vehicle, registration, insurance]
        labels = ["Vehicle", "Registration", "Insurance"]

        for tab, paths, label in zip(tabs[1:], groups, labels):
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

        # Close button at bottom
        st.markdown("---")
        col1, col2, col3 = st.columns([4, 2, 4])
        with col2:
            if st.button("✖ Close Photo Viewer", key=f"close_modal_bottom_{enrollment_id}", type="primary", use_container_width=True):
                st.session_state.open_photos_for_id = None
                st.rerun()

# ------------------------------------------------------------
# Entry Point
# ------------------------------------------------------------
def page_admin_control_center():
    st.title("BYOV Admin Control Center")
    st.caption("Manage enrollments and view analytics")
    
    # Add custom CSS for enhanced button styling
    st.markdown("""
    <style>
    /* Enhanced button styling */
    div[data-testid="stButton"] button {
        font-size: 12px;
        font-weight: 600;
        border-radius: 10px;
        padding: 8px 12px;
        border: none;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        transition: all 0.3s ease;
        white-space: nowrap;
        overflow: visible;
        text-overflow: clip;
    }
    
    div[data-testid="stButton"] button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.15);
    }
    
    div[data-testid="stButton"] button:active {
        transform: translateY(0px);
    }
    
    /* Download button styling */
    div[data-testid="stDownloadButton"] button {
        font-size: 12px;
        font-weight: 600;
        border-radius: 10px;
        padding: 8px 12px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        transition: all 0.3s ease;
        white-space: nowrap;
        overflow: visible;
        text-overflow: clip;
    }
    
    div[data-testid="stDownloadButton"] button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.15);
    }
    
    /* Card container styling */
    div[data-testid="stHorizontalBlock"] {
        gap: 10px;
    }
    
    /* Table styling */
    div[data-testid="stDataFrame"] {
        border-radius: 10px;
        overflow: hidden;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }
    </style>
    """, unsafe_allow_html=True)

    # Load data once for all tabs
    enrollments = _get_all_enrollments()

    tabs = st.tabs(["Overview", "Enrollments"])

    with tabs[0]:
        _overview_tab(enrollments)
    with tabs[1]:
        _enrollments_tab(enrollments)

    st.markdown("---")
    st.caption("Select Approve when all information has been successfully validated for enrollment to push to dashboard.")


if __name__ == '__main__':
    page_admin_control_center()
