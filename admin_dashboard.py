import os
import streamlit as st
from datetime import datetime
import database
from notifications import send_email_notification, send_pdf_to_hr, get_email_config_status, send_custom_notification
import shutil
import file_storage
import base64

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import ssl
ssl._create_default_https_context = ssl._create_unverified_context

try:
    import sqlite3
except Exception:
    sqlite3 = None


ENROLLMENT_FIELDS = [
    {'key': 'full_name', 'label': 'Full Name', 'group': 'Technician'},
    {'key': 'tech_id', 'label': 'Tech ID', 'group': 'Technician'},
    {'key': 'district', 'label': 'District', 'group': 'Technician'},
    {'key': 'state', 'label': 'State', 'group': 'Technician'},
    {'key': 'referred_by', 'label': 'Referred By', 'group': 'Technician'},
    {'key': 'year', 'label': 'Year', 'group': 'Vehicle'},
    {'key': 'make', 'label': 'Make', 'group': 'Vehicle'},
    {'key': 'model', 'label': 'Model', 'group': 'Vehicle'},
    {'key': 'vin', 'label': 'VIN', 'group': 'Vehicle'},
    {'key': 'industry', 'label': 'Industry', 'group': 'Vehicle'},
    {'key': 'insurance_exp', 'label': 'Insurance Exp', 'group': 'Compliance'},
    {'key': 'registration_exp', 'label': 'Registration Exp', 'group': 'Compliance'},
    {'key': 'submission_date', 'label': 'Submitted', 'group': 'Status'},
    {'key': 'approved', 'label': 'Approved', 'group': 'Status'},
]

DOCUMENT_TYPES = [
    {'key': 'signature', 'label': 'Signed PDF'},
    {'key': 'vehicle', 'label': 'Vehicle Photos'},
    {'key': 'registration', 'label': 'Registration'},
    {'key': 'insurance', 'label': 'Insurance Card'},
]


def _get_all_enrollments():
    return database.get_all_enrollments()


def _get_approval_notification_settings():
    """Get the approval notification settings from the database."""
    try:
        settings = database.get_approval_notification_settings()
        if settings:
            if 'selected_fields' not in settings:
                settings['selected_fields'] = ['full_name', 'tech_id', 'district', 'state', 'year', 'make', 'model', 'vin']
            if 'selected_docs' not in settings:
                settings['selected_docs'] = ['signature']
            return settings
    except Exception:
        pass
    return {
        'enabled': False,
        'recipients': '',
        'subject_template': 'BYOV Enrollment Approved: {full_name} (Tech ID: {tech_id})',
        'include_pdf': True,
        'include_details': True,
        'selected_fields': ['full_name', 'tech_id', 'district', 'state', 'year', 'make', 'model', 'vin'],
        'selected_docs': ['signature']
    }


def _save_approval_notification_settings(settings):
    """Save approval notification settings to database."""
    try:
        database.save_approval_notification_settings(settings)
        return True
    except Exception as e:
        st.error(f"Error saving settings: {e}")
        return False


def _format_date(date_str):
    """Format ISO date string to MM/DD/YYYY."""
    if not date_str:
        return 'N/A'
    try:
        dt = datetime.fromisoformat(str(date_str))
        return dt.strftime("%m/%d/%Y")
    except Exception:
        return str(date_str) if date_str else 'N/A'


def _format_field_value(row, key):
    """Format a field value for display."""
    value = row.get(key)
    
    if key in ('insurance_exp', 'registration_exp', 'submission_date'):
        return _format_date(value)
    elif key == 'approved':
        return '✅ Yes' if value == 1 else '⏳ No'
    elif key == 'industry':
        if isinstance(value, list):
            return ', '.join(value) if value else 'N/A'
        return str(value) if value else 'N/A'
    elif key == 'referred_by':
        return value or row.get('referredBy') or 'N/A'
    else:
        return str(value) if value else 'N/A'


def _build_enrollment_grid(enrollments, visible_columns):
    """Build the enrollment data grid."""
    import pandas as pd
    from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
    
    df_data = []
    for row in enrollments:
        record = {'id': row.get('id')}
        for field in ENROLLMENT_FIELDS:
            if field['key'] in visible_columns or field['key'] in ['full_name', 'tech_id']:
                record[field['label']] = _format_field_value(row, field['key'])
        df_data.append(record)
    
    df = pd.DataFrame(df_data)
    
    if len(df) == 0:
        return None, None
    
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_selection(
        selection_mode="single", 
        use_checkbox=False
    )
    gb.configure_column("id", hide=True)
    
    gb.configure_column("Full Name", pinned="left", width=150, checkboxSelection=True)
    gb.configure_column("Tech ID", pinned="left", width=100)
    
    for field in ENROLLMENT_FIELDS:
        if field['label'] not in ['Full Name', 'Tech ID']:
            if field['key'] in visible_columns:
                gb.configure_column(field['label'], width=120)
            else:
                gb.configure_column(field['label'], hide=True)
    
    grid_options = gb.build()
    
    grid_response = AgGrid(
        df,
        gridOptions=grid_options,
        update_mode=GridUpdateMode.SELECTION_CHANGED,
        allow_unsafe_jscode=False,
        fit_columns_on_grid_load=False,
        height=350,
        theme='streamlit',
        columns_auto_size_mode=1,
        key='enrollment_grid'
    )
    
    selected_rows = grid_response['selected_rows']
    selected_id = None
    if selected_rows is not None and len(selected_rows) > 0:
        selected_id = int(selected_rows.iloc[0]['id'])
    
    return grid_response, selected_id


def _render_column_visibility_controls(visible_columns):
    """Render column visibility checkboxes."""
    with st.expander("⚙️ Show/Hide Columns", expanded=False):
        cols = st.columns(4)
        new_visible = set(visible_columns)
        
        groups = {}
        for field in ENROLLMENT_FIELDS:
            if field['key'] not in ['full_name', 'tech_id']:
                group = field['group']
                if group not in groups:
                    groups[group] = []
                groups[group].append(field)
        
        col_idx = 0
        for group_name, fields in groups.items():
            with cols[col_idx % 4]:
                st.markdown(f"**{group_name}**")
                for field in fields:
                    is_visible = field['key'] in visible_columns
                    if st.checkbox(field['label'], value=is_visible, key=f"col_{field['key']}"):
                        new_visible.add(field['key'])
                    elif field['key'] in new_visible:
                        new_visible.discard(field['key'])
            col_idx += 1
        
        return new_visible


def _render_overview_tab(row, enrollment_id):
    """Render the Overview tab with record details and approve button."""
    is_approved = row.get('approved', 0) == 1
    
    vehicle_info = f"{row.get('year', '')} {row.get('make', '')} {row.get('model', '')}".strip()
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, #0d6efd 0%, #0b5ed7 100%);
        padding: 16px 20px;
        border-radius: 10px;
        margin-bottom: 16px;
    ">
        <h3 style="color: white; margin: 0 0 6px 0; font-size: 20px;">
            {row.get('full_name', 'N/A')}
        </h3>
        <p style="color: rgba(255,255,255,0.9); margin: 0; font-size: 13px;">
            Tech ID: <strong>{row.get('tech_id', 'N/A')}</strong> | 
            District: <strong>{row.get('district', 'N/A')}</strong> | 
            State: <strong>{row.get('state', 'N/A')}</strong> |
            Vehicle: <strong>{vehicle_info}</strong>
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("**Technician**")
        st.write(f"Name: {row.get('full_name', 'N/A')}")
        st.write(f"Tech ID: {row.get('tech_id', 'N/A')}")
        st.write(f"District: {row.get('district', 'N/A')}")
        st.write(f"State: {row.get('state', 'N/A')}")
        referred_by = row.get('referred_by') or row.get('referredBy') or 'N/A'
        st.write(f"Referred By: {referred_by}")
    
    with col2:
        st.markdown("**Vehicle**")
        st.write(f"Year: {row.get('year', 'N/A')}")
        st.write(f"Make: {row.get('make', 'N/A')}")
        st.write(f"Model: {row.get('model', 'N/A')}")
        st.write(f"VIN: {row.get('vin', 'N/A')}")
        industry = row.get('industry') or row.get('industries', [])
        if isinstance(industry, list):
            industry = ', '.join(industry) if industry else 'N/A'
        st.write(f"Industry: {industry}")
    
    with col3:
        st.markdown("**Compliance**")
        st.write(f"Insurance Exp: {_format_date(row.get('insurance_exp'))}")
        st.write(f"Registration Exp: {_format_date(row.get('registration_exp'))}")
        st.write(f"Submitted: {_format_date(row.get('submission_date'))}")
        if is_approved:
            st.success("Status: Approved")
        else:
            st.warning("Status: Pending")
    
    st.markdown("---")
    
    action_cols = st.columns([2, 2, 2, 1])
    
    with action_cols[0]:
        if is_approved:
            st.markdown(
                '<div style="background: #10b981; color: white; padding: 10px 12px; '
                'border-radius: 8px; text-align: center; font-weight: 600;">Already Approved</div>',
                unsafe_allow_html=True
            )
        else:
            if st.button("✅ Approve & Sync to Dashboard", key=f"approve_{enrollment_id}", type="primary", use_container_width=True):
                _handle_approval(row, enrollment_id)
    
    with action_cols[1]:
        docs = database.get_documents_for_enrollment(enrollment_id)
        signature_pdf = [d["file_path"] for d in docs if d["doc_type"] == "signature"]
        
        if signature_pdf and file_storage.file_exists(signature_pdf[0]):
            pdf_bytes = file_storage.read_file(signature_pdf[0])
            st.download_button(
                label="⬇️ Download PDF",
                data=pdf_bytes,
                file_name=os.path.basename(signature_pdf[0]),
                mime="application/pdf",
                key=f"dl_pdf_{enrollment_id}",
                use_container_width=True
            )
        else:
            st.button("No PDF", disabled=True, use_container_width=True)
    
    with action_cols[2]:
        if st.button("📧 Send Notification", key=f"send_notif_{enrollment_id}", use_container_width=True):
            result = _send_approval_notification(row, enrollment_id)
            if result is True:
                st.success("Email sent!")
            elif result and result.get('error'):
                st.error(f"Error: {result.get('error')}")
            else:
                st.warning("Notifications not configured. Go to Notification Settings tab.")
    
    with action_cols[3]:
        st.session_state.setdefault("delete_confirm", {})
        is_confirming = st.session_state.delete_confirm.get(enrollment_id, False)
        
        if st.button("🗑️" if not is_confirming else "⚠️ Confirm", key=f"del_{enrollment_id}", use_container_width=True):
            if is_confirming:
                _handle_delete(row, enrollment_id)
            else:
                st.session_state.delete_confirm[enrollment_id] = True
                st.rerun()


def _handle_approval(row, enrollment_id):
    """Handle the approval workflow."""
    from byov_app import post_to_dashboard_single_request
    
    record = dict(row)
    single_result = post_to_dashboard_single_request(record, enrollment_id=enrollment_id)
    
    if single_result.get('error'):
        st.error(f"Error: {single_result.get('error')}")
    else:
        status_code = single_result.get('status_code', 0)
        
        if status_code in (201,) or (200 <= status_code < 300 and status_code != 207):
            try:
                database.approve_enrollment(enrollment_id)
            except Exception:
                pass
            
            notif_result = _send_approval_notification(record, enrollment_id)
            
            st.success("Enrollment approved and synced to dashboard!")
            
            if notif_result is True:
                st.info("Approval notification sent.")
            elif notif_result and notif_result.get('error'):
                st.warning(f"Notification failed: {notif_result.get('error')}")
            
            st.rerun()
        elif status_code == 207:
            try:
                database.approve_enrollment(enrollment_id)
            except Exception:
                pass
            
            st.warning("Approved with warnings (some photos may have failed)")
            st.rerun()
        else:
            st.error(f"Dashboard error: status {status_code}")


def _handle_delete(row, enrollment_id):
    """Handle enrollment deletion."""
    try:
        tech_id = row.get('tech_id', 'unknown')
        docs = database.get_documents_for_enrollment(enrollment_id)
        
        for doc in docs:
            file_path = doc.get('file_path')
            if file_path:
                file_storage.delete_file(file_path)
        
        if not file_storage.USE_OBJECT_STORAGE:
            if os.path.exists('uploads'):
                for folder in os.listdir('uploads'):
                    if folder.startswith(f"{tech_id}_"):
                        folder_path = os.path.join('uploads', folder)
                        if os.path.isdir(folder_path):
                            shutil.rmtree(folder_path, ignore_errors=True)
            
            if os.path.exists('pdfs'):
                for pdf_file in os.listdir('pdfs'):
                    if pdf_file.startswith(f"{tech_id}_") and pdf_file.endswith('.pdf'):
                        os.remove(os.path.join('pdfs', pdf_file))
        
        database.delete_enrollment(enrollment_id)
        st.session_state.delete_confirm.pop(enrollment_id, None)
        st.session_state.selected_enrollment_id = None
        st.success("Deleted")
        st.rerun()
    except Exception as e:
        st.error(f"Error: {e}")


def _render_documents_tab(row, enrollment_id):
    """Render the Documents tab with inline PDF preview and photos."""
    docs = database.get_documents_for_enrollment(enrollment_id)
    
    vehicle = [d["file_path"] for d in docs if d["doc_type"] == "vehicle"]
    registration = [d["file_path"] for d in docs if d["doc_type"] == "registration"]
    insurance = [d["file_path"] for d in docs if d["doc_type"] == "insurance"]
    signature_pdf = [d["file_path"] for d in docs if d["doc_type"] == "signature"]
    
    st.markdown("#### Signed PDF")
    
    if signature_pdf and file_storage.file_exists(signature_pdf[0]):
        pdf_bytes = file_storage.read_file(signature_pdf[0])
        base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
        
        col1, col2 = st.columns([4, 1])
        with col1:
            st.caption(f"📄 {os.path.basename(signature_pdf[0])}")
        with col2:
            st.download_button(
                label="⬇️ Download",
                data=pdf_bytes,
                file_name=os.path.basename(signature_pdf[0]),
                mime="application/pdf",
                key=f"dl_pdf_docs_{enrollment_id}"
            )
        
        pdf_viewer_html = f'''
        <div style="width: 100%; height: 500px; border: 1px solid #ddd; border-radius: 8px; overflow: hidden; margin-bottom: 16px;">
            <iframe src="data:application/pdf;base64,{base64_pdf}" 
                    width="100%" height="100%" style="border: none;">
            </iframe>
        </div>
        '''
        st.markdown(pdf_viewer_html, unsafe_allow_html=True)
    else:
        st.info("No signed PDF found.")
    
    st.markdown("#### Photos")
    
    photo_tabs = st.tabs(["🚗 Vehicle", "📋 Registration", "🛡️ Insurance"])
    
    photo_groups = [
        (photo_tabs[0], vehicle, "vehicle"),
        (photo_tabs[1], registration, "registration"),
        (photo_tabs[2], insurance, "insurance"),
    ]
    
    for tab, paths, label in photo_groups:
        with tab:
            if paths:
                cols = st.columns(3)
                for idx, p in enumerate(paths):
                    if file_storage.file_exists(p):
                        with cols[idx % 3]:
                            try:
                                img_bytes = file_storage.read_file(p)
                                st.image(img_bytes, width=200)
                                st.caption(os.path.basename(p))
                            except Exception as e:
                                st.error(f"Error: {e}")
            else:
                st.info(f"No {label} photos.")


def _render_notification_settings_tab(row, enrollment_id):
    """Render the Notification Settings tab with field/attachment selectors."""
    settings = _get_approval_notification_settings()
    
    st.markdown("#### Configure Notification Email")
    st.caption("Select which fields and documents to include when sending approval notifications.")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Fields to Include**")
        selected_fields = settings.get('selected_fields', [])
        new_selected_fields = []
        
        for field in ENROLLMENT_FIELDS:
            is_selected = field['key'] in selected_fields
            if st.checkbox(
                f"{field['label']} ({field['group']})", 
                value=is_selected, 
                key=f"field_{field['key']}_{enrollment_id}"
            ):
                new_selected_fields.append(field['key'])
    
    with col2:
        st.markdown("**Documents to Attach**")
        docs = database.get_documents_for_enrollment(enrollment_id)
        selected_docs = settings.get('selected_docs', [])
        new_selected_docs = []
        
        doc_counts = {}
        for d in docs:
            doc_type = d['doc_type']
            doc_counts[doc_type] = doc_counts.get(doc_type, 0) + 1
        
        for doc_type in DOCUMENT_TYPES:
            count = doc_counts.get(doc_type['key'], 0)
            is_selected = doc_type['key'] in selected_docs
            label = f"{doc_type['label']} ({count} file{'s' if count != 1 else ''})"
            if st.checkbox(label, value=is_selected, key=f"doc_{doc_type['key']}_{enrollment_id}", disabled=count == 0):
                if count > 0:
                    new_selected_docs.append(doc_type['key'])
    
    st.markdown("---")
    
    st.markdown("**Recipients & Subject**")
    
    recipients = st.text_input(
        "Email Recipients (comma-separated)",
        value=settings.get('recipients', ''),
        placeholder="hr@company.com, fleet@company.com",
        key=f"recipients_{enrollment_id}"
    )
    
    subject_template = st.text_input(
        "Subject Template",
        value=settings.get('subject_template', 'BYOV Enrollment Approved: {full_name} (Tech ID: {tech_id})'),
        help="Use placeholders: {full_name}, {tech_id}, {district}, {state}, {year}, {make}, {model}",
        key=f"subject_{enrollment_id}"
    )
    
    enabled = st.checkbox(
        "Enable automatic notifications on approval",
        value=settings.get('enabled', False),
        key=f"enabled_{enrollment_id}"
    )
    
    if st.button("💾 Save Notification Settings", key=f"save_settings_{enrollment_id}", type="primary"):
        new_settings = {
            'enabled': enabled,
            'recipients': recipients,
            'subject_template': subject_template,
            'include_pdf': 'signature' in new_selected_docs,
            'include_details': len(new_selected_fields) > 0,
            'selected_fields': new_selected_fields,
            'selected_docs': new_selected_docs
        }
        if _save_approval_notification_settings(new_settings):
            st.success("Settings saved!")
            st.rerun()
    
    st.markdown("---")
    st.markdown("#### Email Preview")
    _render_email_preview(row, new_selected_fields, new_selected_docs, subject_template, enrollment_id)


def _render_email_preview(row, selected_fields, selected_docs, subject_template, enrollment_id):
    """Render a live preview of the notification email."""
    subject = subject_template.format(
        full_name=row.get('full_name', 'N/A'),
        tech_id=row.get('tech_id', 'N/A'),
        district=row.get('district', 'N/A'),
        state=row.get('state', 'N/A'),
        year=row.get('year', ''),
        make=row.get('make', ''),
        model=row.get('model', '')
    )
    
    fields_html = ""
    for field in ENROLLMENT_FIELDS:
        if field['key'] in selected_fields:
            value = _format_field_value(row, field['key'])
            fields_html += f"<tr><td style='padding:4px 8px;font-weight:bold;'>{field['label']}:</td><td style='padding:4px 8px;'>{value}</td></tr>"
    
    docs = database.get_documents_for_enrollment(enrollment_id)
    attachments = []
    for doc_type in selected_docs:
        matching = [d for d in docs if d['doc_type'] == doc_type]
        for d in matching:
            attachments.append(os.path.basename(d['file_path']))
    
    attachments_text = ", ".join(attachments) if attachments else "None"
    
    preview_html = f"""
    <div style="border: 1px solid #ddd; border-radius: 8px; padding: 16px; background: #fafafa; font-family: Arial, sans-serif;">
        <div style="border-bottom: 1px solid #eee; padding-bottom: 8px; margin-bottom: 12px;">
            <strong>Subject:</strong> {subject}
        </div>
        <div style="margin-bottom: 12px;">
            <p>A new BYOV enrollment has been approved:</p>
            <table style="border-collapse: collapse; margin: 12px 0;">
                {fields_html if fields_html else '<tr><td style="color: #888;">No fields selected</td></tr>'}
            </table>
        </div>
        <div style="border-top: 1px solid #eee; padding-top: 8px; font-size: 12px; color: #666;">
            <strong>Attachments:</strong> {attachments_text}
        </div>
    </div>
    """
    
    st.markdown(preview_html, unsafe_allow_html=True)


def _send_approval_notification(record, enrollment_id):
    """Send approval notification based on saved settings using selected fields and documents."""
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
    
    selected_fields = settings.get('selected_fields', ['full_name', 'tech_id', 'district', 'state', 'year', 'make', 'model', 'vin'])
    selected_docs = settings.get('selected_docs', ['signature'])
    
    try:
        result = send_custom_notification(
            record=record,
            recipients=recipients,
            subject=subject,
            selected_fields=selected_fields,
            selected_docs=selected_docs,
            field_metadata=ENROLLMENT_FIELDS,
            enrollment_id=enrollment_id
        )
        return result
    except Exception as e:
        return {'error': str(e)}


def _render_action_panel(enrollment_id, enrollments):
    """Render the tabbed action panel for a selected enrollment."""
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
    
    tech_name = row.get('full_name', 'Selected Record')
    st.markdown(f"### {tech_name}")
    
    tabs = st.tabs(["📋 Overview", "📄 Documents", "📧 Notification Settings"])
    
    with tabs[0]:
        _render_overview_tab(row, enrollment_id)
    
    with tabs[1]:
        _render_documents_tab(row, enrollment_id)
    
    with tabs[2]:
        _render_notification_settings_tab(row, enrollment_id)


def _notification_config_page():
    """Global notification configuration page."""
    st.subheader("Email Configuration")
    
    email_status = get_email_config_status()
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Current Status")
        if email_status['sendgrid_configured']:
            st.success(f"SendGrid: Configured ({email_status['sendgrid_from']})")
        else:
            st.warning("SendGrid: Not configured (add SENDGRID_API_KEY secret)")
        
        if email_status['gmail_configured']:
            st.success(f"Gmail SMTP: Configured ({email_status['gmail_sender']})")
        else:
            st.info("Gmail SMTP: Not configured (optional)")
        
        st.info(f"Primary Method: {email_status['primary_method']}")
    
    with col2:
        st.markdown("#### Setup Instructions")
        st.markdown("""
        **SendGrid:**
        1. Get API key from SendGrid
        2. Add `SENDGRID_API_KEY` to Secrets
        
        **Gmail SMTP:**
        1. Create Gmail App Password
        2. Add to secrets.toml
        """)
    


def _overview_page(enrollments):
    """System overview page."""
    st.subheader("System Overview")
    
    total = len(enrollments)
    approved = sum(1 for e in enrollments if e.get('approved', 0) == 1)
    pending = total - approved
    
    if database.USE_POSTGRES if hasattr(database, 'USE_POSTGRES') else False:
        db_mode = "PostgreSQL"
    elif database.USE_SQLITE:
        db_mode = "SQLite"
    else:
        db_mode = "JSON"
    
    file_mode = file_storage.get_storage_mode().split(" ")[0]
    email_status = get_email_config_status()
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Enrollments", total)
    c2.metric("Approved", approved)
    c3.metric("Pending", pending)
    c4.metric("Database", db_mode)
    
    c5, c6, c7, c8 = st.columns(4)
    c5.metric("File Storage", file_mode)
    c6.metric("Email", email_status['primary_method'])
    
    if db_mode == "PostgreSQL":
        st.success("Database is persistent across deployments.")
    else:
        st.warning("Using local storage. Data may not persist across deployments.")


def page_admin_control_center():
    """Main admin control center page."""
    st.title("BYOV Admin Control Center")
    
    st.markdown("""
    <style>
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { padding: 8px 16px; font-size: 14px; }
    div[data-testid="stButton"] button { border-radius: 8px; font-weight: 600; }
    </style>
    """, unsafe_allow_html=True)
    
    enrollments = _get_all_enrollments()
    
    st.session_state.setdefault("selected_enrollment_id", None)
    st.session_state.setdefault("visible_columns", {'district', 'state', 'year', 'make', 'model', 'vin', 'submission_date', 'approved'})
    
    main_tabs = st.tabs(["📋 Enrollments", "📧 Email Config", "📊 Overview"])
    
    with main_tabs[0]:
        if not enrollments:
            st.info("No enrollments yet. Enrollments will appear here after technicians submit the form.")
        else:
            q = st.text_input("🔍 Search", placeholder="Search by name, tech ID, or VIN...")
            
            if q:
                filtered = [r for r in enrollments if q.lower() in " ".join([str(r.get(k, "")).lower() for k in ("full_name", "tech_id", "vin")])]
            else:
                filtered = enrollments
            
            st.caption(f"{len(filtered)} enrollment{'s' if len(filtered) != 1 else ''}")
            
            new_visible = _render_column_visibility_controls(st.session_state.visible_columns)
            if new_visible != st.session_state.visible_columns:
                st.session_state.visible_columns = new_visible
            
            grid_response, selected_id = _build_enrollment_grid(filtered, st.session_state.visible_columns)
            
            if selected_id:
                st.session_state.selected_enrollment_id = selected_id
            else:
                st.session_state.selected_enrollment_id = None
            
            if st.session_state.selected_enrollment_id:
                _render_action_panel(st.session_state.selected_enrollment_id, enrollments)
    
    with main_tabs[1]:
        _notification_config_page()
    
    with main_tabs[2]:
        _overview_page(enrollments)


if __name__ == '__main__':
    page_admin_control_center()
