import os
import streamlit as st
from datetime import datetime
import database
from notifications import send_email_notification, send_pdf_to_hr, get_email_config_status
import shutil
import file_storage

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import ssl
ssl._create_default_https_context = ssl._create_unverified_context

try:
    import sqlite3
except Exception:
    sqlite3 = None

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


def _get_approval_notification_settings():
    """Get the approval notification settings from the database."""
    try:
        settings = database.get_approval_notification_settings()
        if settings:
            return settings
    except Exception:
        pass
    return {
        'enabled': False,
        'recipients': '',
        'subject_template': 'BYOV Enrollment Approved: {full_name} (Tech ID: {tech_id})',
        'include_pdf': True,
        'include_details': True
    }


def _save_approval_notification_settings(settings):
    """Save approval notification settings to database."""
    try:
        database.save_approval_notification_settings(settings)
        return True
    except Exception as e:
        st.error(f"Error saving settings: {e}")
        return False


def _notification_settings_tab():
    """Notification rules management tab"""
    st.subheader("Email Notification Settings")
    
    email_status = get_email_config_status()
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Current Email Configuration")
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
    
    st.markdown("### Approval Notification Settings")
    st.info("Configure the email notification that is sent when you click 'Approve' on an enrollment.")
    
    current_settings = _get_approval_notification_settings()
    
    with st.form("approval_notification_form"):
        col1, col2 = st.columns([1, 1])
        
        with col1:
            enabled = st.checkbox(
                "Enable approval notifications",
                value=current_settings.get('enabled', False),
                help="When enabled, an email will be sent each time you approve an enrollment"
            )
            
            recipients = st.text_input(
                "Recipients (comma-separated)",
                value=current_settings.get('recipients', ''),
                placeholder="hr@company.com, fleet@company.com"
            )
        
        with col2:
            include_pdf = st.checkbox(
                "Attach signed PDF",
                value=current_settings.get('include_pdf', True)
            )
            
            include_details = st.checkbox(
                "Include enrollment details in email body",
                value=current_settings.get('include_details', True)
            )
        
        subject_template = st.text_input(
            "Email Subject Template",
            value=current_settings.get('subject_template', 'BYOV Enrollment Approved: {full_name} (Tech ID: {tech_id})'),
            help="Use {full_name}, {tech_id}, {district}, {state} as placeholders"
        )
        
        st.caption("Available placeholders: {full_name}, {tech_id}, {district}, {state}, {year}, {make}, {model}")
        
        if st.form_submit_button("Save Notification Settings", type="primary"):
            new_settings = {
                'enabled': enabled,
                'recipients': recipients,
                'subject_template': subject_template,
                'include_pdf': include_pdf,
                'include_details': include_details
            }
            if _save_approval_notification_settings(new_settings):
                st.success("Approval notification settings saved!")
                st.rerun()
    
    st.markdown("---")
    
    st.markdown("### Expiration Notification Rules")
    st.info("Configure automatic notifications for insurance/registration expiration reminders.")
    
    rules = database.get_all_notification_rules()
    
    with st.expander("Add New Expiration Rule", expanded=len(rules) == 0):
        with st.form("add_notification_rule"):
            rule_name = st.text_input("Rule Name", placeholder="e.g., HR - Insurance Expiring Soon")
            
            trigger = st.selectbox("Trigger Event", [
                "insurance_expiring_30days",
                "insurance_expiring_7days",
                "registration_expiring_30days",
                "registration_expiring_7days"
            ], format_func=lambda x: {
                "insurance_expiring_30days": "Insurance Expiring (30 days notice)",
                "insurance_expiring_7days": "Insurance Expiring (7 days notice)",
                "registration_expiring_30days": "Registration Expiring (30 days notice)",
                "registration_expiring_7days": "Registration Expiring (7 days notice)"
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
        st.info("No expiration notification rules configured yet.")


def _send_approval_notification(record, enrollment_id):
    """Send approval notification based on saved settings."""
    settings = _get_approval_notification_settings()
    
    if not settings.get('enabled'):
        return None
    
    recipients = settings.get('recipients', '')
    if not recipients:
        return None
    
    subject_template = settings.get('subject_template', 'BYOV Enrollment Approved: {full_name}')
    subject = subject_template.format(
        full_name=record.get('full_name', 'Unknown'),
        tech_id=record.get('tech_id', 'N/A'),
        district=record.get('district', 'N/A'),
        state=record.get('state', 'N/A'),
        year=record.get('year', ''),
        make=record.get('make', ''),
        model=record.get('model', '')
    )
    
    attach_pdf_only = not settings.get('include_details', True)
    
    try:
        if settings.get('include_pdf', True):
            result = send_email_notification(
                record,
                recipients=recipients,
                subject=subject,
                attach_pdf_only=attach_pdf_only
            )
        else:
            result = send_email_notification(
                record,
                recipients=recipients,
                subject=subject,
                attach_pdf_only=False
            )
        return result
    except Exception as e:
        return {'error': str(e)}


def _enrollments_tab(enrollments):
    """Enrollments management tab with integrated selection"""
    import pandas as pd
    
    st.subheader("Enrollments")
    
    if not enrollments:
        st.info("No enrollments yet.")
        return

    st.session_state.setdefault("selected_enrollment_id", None)
    st.session_state.setdefault("ecc_search", "")
    st.session_state.setdefault("ecc_page", 0)
    st.session_state.setdefault("ecc_page_size", 10)
    st.session_state.setdefault("delete_confirm", {})

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

    st.markdown("#### Select a record to view details and take action")
    
    for row in page_rows:
        enrollment_id = row.get('id')
        is_selected = st.session_state.selected_enrollment_id == enrollment_id
        is_approved = row.get('approved', 0) == 1
        
        vehicle_info = f"{row.get('year', '')} {row.get('make', '')} {row.get('model', '')}".strip()
        status_badge = "✅ Approved" if is_approved else "⏳ Pending"
        
        submission_date = row.get('submission_date', '')
        date_enrolled = ''
        if submission_date:
            try:
                dt = datetime.fromisoformat(submission_date)
                date_enrolled = dt.strftime("%m/%d/%Y")
            except Exception:
                date_enrolled = submission_date
        
        if is_selected:
            card_style = "background: linear-gradient(135deg, #0d6efd 0%, #0b5ed7 100%); border: 2px solid #0d6efd;"
            text_color = "white"
            badge_bg = "rgba(255,255,255,0.2)"
        else:
            card_style = "background: #f8f9fa; border: 1px solid #dee2e6;"
            text_color = "#333"
            badge_bg = "#e9ecef"
        
        st.markdown(f"""
        <div style="
            {card_style}
            padding: 12px 16px;
            border-radius: 10px;
            margin-bottom: 8px;
            cursor: pointer;
            transition: all 0.2s ease;
        ">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <span style="color: {text_color}; font-weight: 600; font-size: 15px;">
                        {row.get('full_name', 'N/A')}
                    </span>
                    <span style="color: {'rgba(255,255,255,0.8)' if is_selected else '#666'}; font-size: 13px; margin-left: 10px;">
                        Tech ID: {row.get('tech_id', 'N/A')} | {vehicle_info}
                    </span>
                </div>
                <div style="display: flex; gap: 8px; align-items: center;">
                    <span style="background: {badge_bg}; color: {text_color}; padding: 4px 10px; border-radius: 12px; font-size: 11px;">
                        {date_enrolled}
                    </span>
                    <span style="background: {'#10b981' if is_approved else '#f59e0b'}; color: white; padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: 600;">
                        {status_badge}
                    </span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2 = st.columns([1, 5])
        with col1:
            btn_label = "● Selected" if is_selected else "○ Select"
            btn_type = "primary" if is_selected else "secondary"
            if st.button(btn_label, key=f"select_{enrollment_id}", type=btn_type):
                if is_selected:
                    st.session_state.selected_enrollment_id = None
                else:
                    st.session_state.selected_enrollment_id = enrollment_id
                st.rerun()
    
    if st.session_state.selected_enrollment_id:
        _render_action_panel(st.session_state.selected_enrollment_id, enrollments)


def _render_action_panel(enrollment_id, enrollments):
    """Render the action panel for a selected enrollment."""
    row = None
    for e in enrollments:
        if e.get('id') == enrollment_id:
            row = e
            break
    
    if not row:
        st.warning("Selected enrollment not found.")
        st.session_state.selected_enrollment_id = None
        return
    
    st.markdown("---")
    st.markdown("### Selected Enrollment Details")
    
    is_approved = row.get('approved', 0) == 1
    
    vehicle_info = f"{row.get('year', '')} {row.get('make', '')} {row.get('model', '')}".strip()
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, #0d6efd 0%, #0b5ed7 100%);
        padding: 20px;
        border-radius: 12px;
        margin-bottom: 20px;
        box-shadow: 0 4px 12px rgba(13, 110, 253, 0.3);
    ">
        <h2 style="color: white; margin: 0 0 8px 0; font-size: 22px;">
            {row.get('full_name', 'N/A')}
        </h2>
        <p style="color: rgba(255,255,255,0.9); margin: 0; font-size: 14px;">
            Tech ID: <strong>{row.get('tech_id', 'N/A')}</strong> | 
            District: <strong>{row.get('district', 'N/A')}</strong> | 
            State: <strong>{row.get('state', 'N/A')}</strong>
        </p>
        <p style="color: rgba(255,255,255,0.85); margin: 8px 0 0 0; font-size: 13px;">
            🚗 {vehicle_info} | VIN: {row.get('vin', 'N/A')}
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("**Technician Info**")
        st.write(f"Name: {row.get('full_name', 'N/A')}")
        st.write(f"Tech ID: {row.get('tech_id', 'N/A')}")
        st.write(f"District: {row.get('district', 'N/A')}")
        st.write(f"State: {row.get('state', 'N/A')}")
        referred_by = row.get('referred_by') or row.get('referredBy') or 'N/A'
        st.write(f"Referred By: {referred_by}")
    
    with col2:
        st.markdown("**Vehicle Info**")
        st.write(f"Year: {row.get('year', 'N/A')}")
        st.write(f"Make: {row.get('make', 'N/A')}")
        st.write(f"Model: {row.get('model', 'N/A')}")
        st.write(f"VIN: {row.get('vin', 'N/A')}")
        
        industries_raw = row.get('industry') if row.get('industry') is not None else row.get('industries', [])
        if isinstance(industries_raw, list):
            industries_str = ", ".join(industries_raw) if industries_raw else "None"
        else:
            industries_str = str(industries_raw) if industries_raw else "None"
        st.write(f"Industry: {industries_str}")
    
    with col3:
        st.markdown("**Documents & Status**")
        
        ins_exp = row.get('insurance_exp', '')
        if ins_exp:
            try:
                dt = datetime.fromisoformat(ins_exp)
                ins_exp = dt.strftime("%m/%d/%Y")
            except Exception:
                pass
        st.write(f"Insurance Exp: {ins_exp or 'N/A'}")
        
        reg_exp = row.get('registration_exp', '')
        if reg_exp:
            try:
                dt = datetime.fromisoformat(reg_exp)
                reg_exp = dt.strftime("%m/%d/%Y")
            except Exception:
                pass
        st.write(f"Registration Exp: {reg_exp or 'N/A'}")
        
        submission_date = row.get('submission_date', '')
        if submission_date:
            try:
                dt = datetime.fromisoformat(submission_date)
                submission_date = dt.strftime("%m/%d/%Y")
            except Exception:
                pass
        st.write(f"Submitted: {submission_date or 'N/A'}")
        
        if is_approved:
            st.success("Status: Approved ✅")
        else:
            st.warning("Status: Pending Approval")
    
    st.markdown("---")
    
    st.markdown("#### Actions")
    action_cols = st.columns(4)
    
    with action_cols[0]:
        if st.button("🖼️ View Photos & PDF", key=f"action_view_{enrollment_id}", type="secondary", use_container_width=True):
            st.session_state.show_photos_panel = enrollment_id
            st.rerun()
    
    with action_cols[1]:
        if is_approved:
            st.markdown(
                '<div style="background: #10b981; color: white; padding: 10px 12px; '
                'border-radius: 8px; text-align: center; font-weight: 600; font-size: 14px;">'
                '✅ Approved</div>',
                unsafe_allow_html=True
            )
        else:
            if st.button("✅ Approve", key=f"action_approve_{enrollment_id}", type="primary", use_container_width=True):
                from byov_app import post_to_dashboard_single_request

                record = dict(row)
                single_result = post_to_dashboard_single_request(record, enrollment_id=enrollment_id)

                if single_result.get('error'):
                    st.error(f"❌ Error: {single_result.get('error')}")
                else:
                    status_code = single_result.get('status_code', 0)
                    resp = single_result.get('response')
                    
                    if status_code in (201,) or (200 <= status_code < 300 and status_code != 207):
                        try:
                            database.approve_enrollment(enrollment_id)
                        except Exception:
                            pass
                        
                        notif_result = _send_approval_notification(record, enrollment_id)
                        
                        st.success(f"✅ Enrollment approved and synced to dashboard!")
                        
                        if notif_result is True:
                            st.info("📧 Approval notification sent successfully.")
                        elif notif_result and notif_result.get('error'):
                            st.warning(f"⚠️ Notification failed: {notif_result.get('error')}")
                        
                        st.rerun()
                    elif status_code == 207:
                        try:
                            database.approve_enrollment(enrollment_id)
                        except Exception:
                            pass
                        
                        notif_result = _send_approval_notification(record, enrollment_id)
                        
                        st.warning(f"⚠️ Approved with warnings (some photos may have failed)")
                        if single_result.get('failed_photos'):
                            with st.expander("Failed Photo Details"):
                                st.json(single_result.get('failed_photos'))
                        st.rerun()
                    else:
                        st.error(f"❌ Dashboard responded with status {status_code}: {resp}")
    
    with action_cols[2]:
        docs = database.get_documents_for_enrollment(enrollment_id)
        signature_pdf = [d["file_path"] for d in docs if d["doc_type"] == "signature"]
        
        if signature_pdf and file_storage.file_exists(signature_pdf[0]):
            pdf_bytes = file_storage.read_file(signature_pdf[0])
            st.download_button(
                label="⬇️ Download PDF",
                data=pdf_bytes,
                file_name=os.path.basename(signature_pdf[0]),
                mime="application/pdf",
                key=f"download_pdf_{enrollment_id}",
                use_container_width=True
            )
        else:
            st.button("⬇️ No PDF Available", disabled=True, use_container_width=True)
    
    with action_cols[3]:
        is_confirming = st.session_state.delete_confirm.get(enrollment_id, False)
        btn_label = "⚠️ Confirm Delete" if is_confirming else "🗑️ Delete"
        
        if st.button(btn_label, key=f"action_delete_{enrollment_id}", type="secondary", use_container_width=True):
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
                    st.session_state.selected_enrollment_id = None
                    st.success(f"✅ Deleted enrollment")
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"Error deleting: {e}")
            else:
                st.session_state.delete_confirm[enrollment_id] = True
                st.rerun()
    
    if st.session_state.get('show_photos_panel') == enrollment_id:
        _render_photos_panel(enrollment_id)


def _render_photos_panel(enrollment_id):
    """Render the photos and PDF viewer panel."""
    st.markdown("---")
    st.markdown("### 📸 Photos & Documents")
    
    col1, col2 = st.columns([6, 1])
    with col2:
        if st.button("✖ Close", key=f"close_photos_{enrollment_id}", type="primary"):
            st.session_state.show_photos_panel = None
            st.rerun()
    
    docs = database.get_documents_for_enrollment(enrollment_id)
    
    vehicle = [d["file_path"] for d in docs if d["doc_type"] == "vehicle"]
    registration = [d["file_path"] for d in docs if d["doc_type"] == "registration"]
    insurance = [d["file_path"] for d in docs if d["doc_type"] == "insurance"]
    signature_pdf = [d["file_path"] for d in docs if d["doc_type"] == "signature"]
    
    tabs = st.tabs(["📄 Signed PDF", "🚗 Vehicle", "📋 Registration", "🛡️ Insurance"])
    
    with tabs[0]:
        if signature_pdf and file_storage.file_exists(signature_pdf[0]):
            try:
                pdf_bytes = file_storage.read_file(signature_pdf[0])
                
                import base64
                base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
                
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.info(f"📄 {os.path.basename(signature_pdf[0])}")
                with col2:
                    st.download_button(
                        label="⬇️ Download",
                        data=pdf_bytes,
                        file_name=os.path.basename(signature_pdf[0]),
                        mime="application/pdf",
                        key=f"download_pdf_panel_{enrollment_id}"
                    )
                
                @st.cache_data(ttl=300, show_spinner=False)
                def render_pdf_page(pdf_bytes_hash, page_number):
                    try:
                        from pdf2image import convert_from_bytes
                        images = convert_from_bytes(pdf_bytes, first_page=page_number, last_page=page_number, dpi=150)
                        if images:
                            from io import BytesIO
                            img_buffer = BytesIO()
                            images[0].save(img_buffer, format='PNG')
                            return img_buffer.getvalue()
                    except Exception:
                        pass
                    return None
                
                def get_pdf_page_count(pdf_bytes):
                    try:
                        import PyPDF2
                        from io import BytesIO
                        reader = PyPDF2.PdfReader(BytesIO(pdf_bytes))
                        return len(reader.pages)
                    except Exception:
                        pass
                    return None
                
                try:
                    total_pages = get_pdf_page_count(pdf_bytes)
                except Exception as page_err:
                    st.error(f"Could not determine page count: {page_err}")
                    st.info("Showing full PDF in embedded viewer.")
                    pdf_viewer_html = f'''
                    <div style="width: 100%; height: 700px; border: 1px solid #ddd; border-radius: 8px; overflow: hidden;">
                        <iframe src="data:application/pdf;base64,{base64_pdf}" 
                                width="100%" height="100%" style="border: none;">
                        </iframe>
                    </div>
                    '''
                    st.markdown(pdf_viewer_html, unsafe_allow_html=True)
                    total_pages = None
                
                if total_pages:
                    if f"pdf_page_{enrollment_id}" not in st.session_state:
                        st.session_state[f"pdf_page_{enrollment_id}"] = 1
                    
                    current_page = st.session_state[f"pdf_page_{enrollment_id}"]
                    
                    if current_page > total_pages:
                        current_page = 1
                        st.session_state[f"pdf_page_{enrollment_id}"] = 1
                    
                    nav_col1, nav_col2, nav_col3, nav_col4, nav_col5 = st.columns([1, 1, 2, 1, 1])
                    
                    with nav_col1:
                        if st.button("⏮ First", key=f"first_page_panel_{enrollment_id}", use_container_width=True):
                            st.session_state[f"pdf_page_{enrollment_id}"] = 1
                    
                    with nav_col2:
                        if st.button("◀ Prev", key=f"prev_page_panel_{enrollment_id}", use_container_width=True):
                            if current_page > 1:
                                st.session_state[f"pdf_page_{enrollment_id}"] = current_page - 1
                    
                    with nav_col3:
                        st.markdown(f"<div style='text-align: center; padding: 8px; background: #0d6efd; color: white; border-radius: 4px; font-weight: bold;'>Page {current_page} of {total_pages}</div>", unsafe_allow_html=True)
                    
                    with nav_col4:
                        if st.button("Next ▶", key=f"next_page_panel_{enrollment_id}", use_container_width=True):
                            if current_page < total_pages:
                                st.session_state[f"pdf_page_{enrollment_id}"] = current_page + 1
                    
                    with nav_col5:
                        if st.button("Last ⏭", key=f"last_page_panel_{enrollment_id}", use_container_width=True):
                            st.session_state[f"pdf_page_{enrollment_id}"] = total_pages
                    
                    st.caption(f"📝 Signature is on page {total_pages}")
                    
                    page_buttons = st.columns(min(total_pages, 10))
                    for i, col in enumerate(page_buttons[:total_pages]):
                        page_num = i + 1
                        with col:
                            btn_type = "primary" if page_num == current_page else "secondary"
                            if st.button(str(page_num), key=f"page_btn_panel_{enrollment_id}_{page_num}", type=btn_type, use_container_width=True):
                                st.session_state[f"pdf_page_{enrollment_id}"] = page_num
                    
                    current_page = st.session_state[f"pdf_page_{enrollment_id}"]
                    
                    pdf_hash = hash(pdf_bytes[:1000])
                    page_image = render_pdf_page(pdf_hash, current_page)
                    
                    if page_image:
                        st.image(page_image, use_container_width=True)
                        if current_page == total_pages:
                            st.success("📝 This is the signed page with the technician's signature.")
                    else:
                        st.warning("Unable to render page. Use Download button to view full PDF.")
                        pdf_viewer_html = f'''
                        <div style="width: 100%; height: 700px; border: 1px solid #ddd; border-radius: 8px; overflow: hidden;">
                            <iframe src="data:application/pdf;base64,{base64_pdf}#page={current_page}" 
                                    width="100%" height="100%" style="border: none;">
                            </iframe>
                        </div>
                        '''
                        st.markdown(pdf_viewer_html, unsafe_allow_html=True)
                
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


def page_admin_control_center():
    st.title("BYOV Admin Control Center")
    st.caption("Manage enrollments and configure notifications")
    
    st.markdown("""
    <style>
    button[data-baseweb="tab"] {
        padding: 8px 16px !important;
        font-size: 13px !important;
        white-space: normal !important;
    }
    
    div[data-testid="stButton"] button {
        font-size: 12px;
        font-weight: 600;
        border-radius: 8px;
        padding: 8px 12px;
        border: none;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        transition: all 0.2s ease;
        white-space: normal;
        overflow: visible;
        text-overflow: clip;
    }
    
    div[data-testid="stButton"] button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.15);
    }
    
    div[data-testid="stDownloadButton"] button {
        font-size: 12px;
        font-weight: 600;
        border-radius: 8px;
        padding: 8px 12px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        transition: all 0.2s ease;
    }
    
    div[data-testid="stDataFrame"] {
        border-radius: 10px;
        overflow: hidden;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }
    </style>
    """, unsafe_allow_html=True)

    enrollments = _get_all_enrollments()

    tab1, tab2, tab3 = st.tabs(["📋 Enrollments", "📧 Notification Settings", "📊 Overview"])
    
    with tab1:
        _enrollments_tab(enrollments)
        st.markdown("---")
        st.caption("Select an enrollment, review details, then click Approve to sync to dashboard.")
    
    with tab2:
        _notification_settings_tab()
    
    with tab3:
        _overview_tab(enrollments)


if __name__ == '__main__':
    page_admin_control_center()
