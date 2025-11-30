import os
import streamlit as st
from datetime import datetime
import database
from notifications import send_email_notification, send_pdf_to_hr, get_email_config_status
import shutil
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode
import file_storage

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import ssl
ssl._create_default_https_context = ssl._create_unverified_context

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
    """Returns list of dicts: {id, enrollment_id, rule_id, sent_at}"""
    sent = []
    enrolls = _get_all_enrollments()
    for e in enrolls:
        eid = e.get('id')
        for s in database.get_sent_notifications(eid):
            sent.append(s)
    sent.sort(key=lambda x: x.get('sent_at',''), reverse=True)
    return sent


# ------------------------------------------------------------
# UI Components
# ------------------------------------------------------------
def _overview_tab(enrollments):
    st.subheader("Overview")

    total_enrollments = len(enrollments)
    
    if database.USE_POSTGRES if hasattr(database, 'USE_POSTGRES') else False:
        db_mode = "PostgreSQL (Persistent)"
    elif database.USE_SQLITE:
        db_mode = "SQLite (Local)"
    else:
        db_mode = "JSON Fallback"
    
    file_mode = file_storage.get_storage_mode()
    email_status = get_email_config_status()

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Enrollments", total_enrollments)
    c2.metric("Database", db_mode)
    c3.metric("Email", email_status['primary_method'])
    
    c4, c5, c6 = st.columns(3)
    c4.metric("File Storage", file_mode.split(" ")[0])
    if email_status['sendgrid_configured']:
        c5.metric("SendGrid From", email_status['sendgrid_from'][:20] + "..." if len(email_status['sendgrid_from']) > 20 else email_status['sendgrid_from'])
    
    if "persistent" in db_mode.lower() and "persistent" in file_mode.lower():
        st.success("Data will persist across app restarts and deployments.")
    else:
        st.warning("Some data may not persist across deployments. Configure Object Storage for full persistence.")
    
    st.markdown("---")
    st.info("Use the Enrollments tab to view and manage all enrollments.")


def _notification_settings_tab():
    """Notification rules management tab"""
    st.subheader("Email Notification Settings")
    
    email_status = get_email_config_status()
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Current Configuration")
        if email_status['sendgrid_configured']:
            st.success(f"SendGrid: Configured ({email_status['sendgrid_from']})")
        else:
            st.warning("SendGrid: Not configured (add SENDGRID_API_KEY secret)")
        
        if email_status['gmail_configured']:
            st.success(f"Gmail SMTP: Configured ({email_status['gmail_sender']})")
        else:
            st.info("Gmail SMTP: Not configured (optional fallback)")
        
        st.info(f"Primary Method: {email_status['primary_method']}")
    
    with col2:
        st.markdown("#### Setup Instructions")
        st.markdown("""
        **To enable SendGrid:**
        1. Get your API key from SendGrid
        2. Add `SENDGRID_API_KEY` to Secrets
        3. `SENDGRID_FROM_EMAIL` is already set
        
        **To enable Gmail SMTP:**
        1. Create a Gmail App Password
        2. Add to Streamlit secrets.toml
        """)
    
    st.markdown("---")
    
    st.markdown("#### Notification Rules")
    st.info("Configure which departments receive email notifications for different events.")
    
    rules = database.get_all_notification_rules()
    
    with st.expander("Add New Notification Rule", expanded=len(rules) == 0):
        with st.form("add_notification_rule"):
            rule_name = st.text_input("Rule Name", placeholder="e.g., HR Notification")
            
            trigger = st.selectbox("Trigger Event", [
                "new_enrollment",
                "enrollment_approved", 
                "insurance_expiring_30days",
                "insurance_expiring_7days",
                "registration_expiring_30days",
                "registration_expiring_7days"
            ], format_func=lambda x: {
                "new_enrollment": "New Enrollment Submitted",
                "enrollment_approved": "Enrollment Approved",
                "insurance_expiring_30days": "Insurance Expiring (30 days)",
                "insurance_expiring_7days": "Insurance Expiring (7 days)",
                "registration_expiring_30days": "Registration Expiring (30 days)",
                "registration_expiring_7days": "Registration Expiring (7 days)"
            }.get(x, x))
            
            days_before = None
            if "expiring" in trigger:
                days_before = int(trigger.split("_")[-1].replace("days", ""))
            
            recipients = st.text_input("Recipients (comma-separated emails)", 
                                       placeholder="hr@shs.com, fleet@shs.com")
            
            if st.form_submit_button("Add Rule", type="primary"):
                if rule_name and recipients:
                    try:
                        database.add_notification_rule(rule_name, trigger, days_before, recipients)
                        st.success(f"Rule '{rule_name}' added successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error adding rule: {e}")
                else:
                    st.warning("Please fill in all required fields.")
    
    if rules:
        st.markdown("#### Active Rules")
        for rule in rules:
            with st.container():
                col1, col2, col3, col4 = st.columns([3, 2, 3, 1])
                with col1:
                    st.write(f"**{rule['rule_name']}**")
                with col2:
                    trigger_display = {
                        "new_enrollment": "New Enrollment",
                        "enrollment_approved": "Approved",
                        "insurance_expiring_30days": "Insurance -30d",
                        "insurance_expiring_7days": "Insurance -7d",
                        "registration_expiring_30days": "Reg. -30d",
                        "registration_expiring_7days": "Reg. -7d"
                    }.get(rule['trigger'], rule['trigger'])
                    st.write(trigger_display)
                with col3:
                    st.write(rule['recipients'][:40] + "..." if len(rule['recipients']) > 40 else rule['recipients'])
                with col4:
                    if st.button("🗑️", key=f"delete_rule_{rule['id']}", help="Delete rule"):
                        try:
                            database.delete_notification_rule(rule['id'])
                            st.success("Rule deleted!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")
                st.markdown("---")
    else:
        st.info("No notification rules configured yet. Add rules above to automatically notify departments.")


def _enrollments_tab(enrollments):
    """Enrollments management tab"""
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
        # Transform industry to comma-separated string (accept either 'industry' or 'industries')
        industries_raw = row.get('industry') if row.get('industry') is not None else row.get('industries', [])
        if isinstance(industries_raw, list):
            industries_str = ", ".join(industries_raw) if industries_raw else "None"
        else:
            industries_str = str(industries_raw) if industries_raw else "None"
        
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
            'Referred By': row.get('referred_by') or row.get('referredBy') or 'N/A',
            'VIN': row.get('vin', 'N/A'),
            'Vehicle': vehicle_info,
            'Industry': industries_str,
            'Date Enrolled': date_enrolled,
            'Registration Exp. Date': reg_exp,
            'Insurance Exp. Date': ins_exp,
            'Approved': approved_status
        })
    
    # Display table with dataframe
    if display_rows:
        df = pd.DataFrame(display_rows)
        st.dataframe(df, width='stretch', hide_index=True)
        
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
                
                cols = st.columns([2.2, 3.2, 2.7, 2.2])
                
                # Select button
                with cols[0]:
                    is_selected = enrollment_id in st.session_state.selected_enrollment_ids
                    btn_label = "✅ Selected" if is_selected else "⭕ Select"
                    btn_type = "primary" if is_selected else "secondary"
                    if st.button(btn_label, key=f"select_{enrollment_id}", type=btn_type, width='stretch'):
                        if is_selected:
                            st.session_state.selected_enrollment_ids.discard(enrollment_id)
                        else:
                            st.session_state.selected_enrollment_ids.add(enrollment_id)
                        st.rerun()
                
                # View Photos button
                with cols[1]:
                    if st.button("🖼️ View Photos", key=f"view_photos_{enrollment_id}", width='stretch', type="secondary"):
                        st.session_state.open_photos_for_id = enrollment_id
                        st.rerun()
                
                # Approve button - Sends to dashboard
                with cols[2]:
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
                        # Show approve button (creates technician record only)
                        if st.button("✅ Approve", key=f"approve_{enrollment_id}", type="primary", width='stretch'):
                            from byov_app import post_to_dashboard_single_request

                            record = dict(row)

                            # Use the single-request external API to create technician + photos
                            single_result = post_to_dashboard_single_request(record, enrollment_id=enrollment_id)

                            # Handle errors
                            if single_result.get('error'):
                                st.error(f"❌ Technician creation error: {single_result.get('error')}")
                            else:
                                status_code = single_result.get('status_code', 0)
                                resp = single_result.get('response')
                                # Consider 201 or 200 as success; 207 as partial success
                                if status_code in (201,) or (200 <= status_code < 300 and status_code != 207):
                                    # Success — database.set_dashboard_sync_info already attempted in helper
                                    try:
                                        database.approve_enrollment(enrollment_id)
                                    except Exception:
                                        pass
                                    st.success(f"✅ Enrollment #{enrollment_id} approved and technician created on dashboard.")
                                    st.rerun()
                                elif status_code == 207:
                                    # Partial success — show details and still mark approved
                                    try:
                                        database.approve_enrollment(enrollment_id)
                                    except Exception:
                                        pass
                                    st.warning(f"⚠️ Enrollment #{enrollment_id} created, but some photos failed to attach.")
                                    if single_result.get('failed_photos'):
                                        with st.expander("Failed Photo Details"):
                                            st.json(single_result.get('failed_photos'))
                                    st.rerun()
                                else:
                                    # Non-successful HTTP response
                                    st.error(f"❌ Dashboard responded with status {status_code}: {resp}")
                
                # Delete button
                with cols[3]:
                    is_confirming = st.session_state.delete_confirm.get(enrollment_id, False)
                    btn_label = "⚠️ Confirm Delete" if is_confirming else "🗑️ Delete"
                    
                    if st.button(btn_label, key=f"delete_{enrollment_id}", type="secondary", width='stretch'):
                        if is_confirming:
                            try:
                                tech_id = row.get('tech_id', 'unknown')
                                docs = database.get_documents_for_enrollment(enrollment_id)
                                
                                for doc in docs:
                                    file_path = doc.get('file_path')
                                    if file_path:
                                        file_storage.delete_file(file_path)
                                
                                if not file_storage.USE_OBJECT_STORAGE:
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
                                    
                                    if os.path.exists('pdfs'):
                                        pdf_prefix = f"{tech_id}_"
                                        for pdf_file in os.listdir('pdfs'):
                                            if pdf_file.startswith(pdf_prefix) and pdf_file.endswith('.pdf'):
                                                pdf_path = os.path.join('pdfs', pdf_file)
                                                try:
                                                    os.remove(pdf_path)
                                                except Exception:
                                                    pass
                                
                                database.delete_enrollment(enrollment_id)
                                st.session_state.delete_confirm.pop(enrollment_id, None)
                                st.success(f"✅ Deleted enrollment {enrollment_id}")
                                st.rerun()
                                
                            except Exception as e:
                                st.error(f"Error deleting enrollment {enrollment_id}: {e}")
                        else:
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
        
        with tabs[0]:
            if signature_pdf and file_storage.file_exists(signature_pdf[0]):
                try:
                    pdf_bytes = file_storage.read_file(signature_pdf[0])
                    
                    enrollment_record = database.get_enrollment_by_id(enrollment_id)
                    
                    col1, col2, col3 = st.columns([3, 1, 1])
                    with col1:
                        st.info(f"📄 {os.path.basename(signature_pdf[0])}")
                    with col2:
                        st.download_button(
                            label="⬇️ Download",
                            data=pdf_bytes,
                            file_name=os.path.basename(signature_pdf[0]),
                            mime="application/pdf",
                            key=f"download_pdf_modal_{enrollment_id}",
                            use_container_width=True
                        )
                    with col3:
                        if st.button("📧 Send to HR", key=f"send_hr_btn_{enrollment_id}", use_container_width=True):
                            st.session_state[f"show_hr_form_{enrollment_id}"] = True
                    
                    if st.session_state.get(f"show_hr_form_{enrollment_id}", False):
                        with st.form(f"send_hr_form_{enrollment_id}"):
                            st.markdown("#### Send Signed PDF to HR")
                            hr_email = st.text_input("HR Email Address", placeholder="hr@shs.com")
                            custom_subject = st.text_input("Subject (optional)", 
                                placeholder=f"BYOV Signed Agreement - {enrollment_record.get('full_name', 'Unknown')}")
                            
                            col_send, col_cancel = st.columns(2)
                            with col_send:
                                if st.form_submit_button("📤 Send Email", type="primary", use_container_width=True):
                                    if hr_email:
                                        record_with_pdf = enrollment_record.copy()
                                        record_with_pdf['signature_pdf_path'] = signature_pdf[0]
                                        
                                        if send_pdf_to_hr(record_with_pdf, hr_email, custom_subject if custom_subject else None):
                                            st.success(f"PDF sent to {hr_email}!")
                                            st.session_state[f"show_hr_form_{enrollment_id}"] = False
                                        else:
                                            st.error("Failed to send email. Check email configuration.")
                                    else:
                                        st.warning("Please enter an HR email address.")
                            with col_cancel:
                                if st.form_submit_button("Cancel", use_container_width=True):
                                    st.session_state[f"show_hr_form_{enrollment_id}"] = False
                                    st.rerun()
                    
                    st.markdown("---")
                    
                    import base64
                    base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
                    st.markdown(
                        f'<div class="pdf-container"><iframe src="data:application/pdf;base64,{base64_pdf}" '
                        f'width="100%" height="700" style="border:none;"></iframe></div>',
                        unsafe_allow_html=True
                    )
                    
                except Exception as e:
                    st.error(f"Error loading PDF: {e}")
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
                                if file_storage.file_exists(p):
                                    with col:
                                        try:
                                            img_bytes = file_storage.read_file(p)
                                            st.image(img_bytes, width=250)
                                            st.caption(os.path.basename(p))
                                        except Exception as e:
                                            st.error(f"Error loading: {e}")
                                else:
                                    with col:
                                        st.error(f"Missing: {p}")
                else:
                    st.info(f"No {label.lower()} photos found.")

        # Close button at bottom
        st.markdown("---")
        col1, col2, col3 = st.columns([4, 2, 4])
        with col2:
            if st.button("✖ Close Photo Viewer", key=f"close_modal_bottom_{enrollment_id}", type="primary", width='stretch'):
                st.session_state.open_photos_for_id = None
                st.rerun()

# ------------------------------------------------------------
# Entry Point
# ------------------------------------------------------------
def page_admin_control_center():
    st.title("BYOV Admin Control Center")
    st.caption("Manage enrollments and view analytics")
    
    st.markdown("""
    <style>
    /* Tab styling to fit text properly */
    button[data-baseweb="tab"] {
        padding: 8px 16px !important;
        font-size: 13px !important;
        white-space: normal !important;
    }
    
    /* Enhanced button styling */
    div[data-testid="stButton"] button {
        font-size: 12px;
        font-weight: 600;
        border-radius: 10px;
        padding: 8px 12px;
        border: none;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        transition: all 0.3s ease;
        white-space: normal;
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
    
    /* PDF Viewer styling */
    .pdf-container {
        border: 1px solid #ddd;
        border-radius: 8px;
        overflow: hidden;
    }
    </style>
    """, unsafe_allow_html=True)

    enrollments = _get_all_enrollments()

    tab1, tab2, tab3 = st.tabs(["📋 Enrollments", "📧 Email Settings", "📊 Overview"])
    
    with tab1:
        _enrollments_tab(enrollments)
        st.markdown("---")
        st.caption("Select Approve when all information has been successfully validated for enrollment to push to dashboard.")
    
    with tab2:
        _notification_settings_tab()
    
    with tab3:
        _overview_tab(enrollments)


if __name__ == '__main__':
    page_admin_control_center()
