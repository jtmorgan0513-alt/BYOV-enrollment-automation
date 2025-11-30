import io
import os
import zipfile
import mimetypes
import smtplib
import json
import requests
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.utils import formatdate
from datetime import datetime

import streamlit as st
import file_storage


def get_sears_html_template(record, include_logo=True):
    """Generate a branded HTML email template with Sears styling."""
    
    industries_list = record.get('industry', record.get('industries', []))
    industries_str = ", ".join(industries_list) if industries_list else "None"
    
    submission_date = record.get('submission_date', '')
    if submission_date:
        try:
            dt = datetime.fromisoformat(submission_date)
            submission_date = dt.strftime("%m/%d/%Y at %I:%M %p")
        except Exception:
            pass
    
    logo_section = ""
    if include_logo:
        logo_base64 = "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"
        logo_section = f"""
        <div style="text-align: center; padding: 25px 20px; background-color: #ffffff; border-bottom: 1px solid #e0e0e0;">
            <!-- Sears Home Services Logo -->
            <img src="data:image/png;base64,{logo_base64}" alt="Sears Home Services" style="max-width: 200px; height: auto;" />
        </div>
        """
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>BYOV Enrollment Notification</title>
    </head>
    <body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f5f7fa;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            
            {logo_section}
            
            <!-- Header Banner -->
            <div style="background-color: #e8f4fc; padding: 20px; text-align: center; border-bottom: 3px solid #0d6efd;">
                <h2 style="color: #0d6efd; margin: 0; font-size: 22px;">
                    New BYOV Enrollment Submitted
                </h2>
                <p style="color: #666; margin: 10px 0 0 0; font-size: 14px;">
                    Submitted on {submission_date}
                </p>
            </div>
            
            <!-- Content -->
            <div style="padding: 30px;">
                
                <!-- Technician Information Card -->
                <div style="background: linear-gradient(to right, #f8f9fa, #ffffff); border-left: 4px solid #0d6efd; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                    <h3 style="color: #0d6efd; margin: 0 0 15px 0; font-size: 16px; text-transform: uppercase; letter-spacing: 1px;">
                        👤 Technician Information
                    </h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px 0; color: #666; width: 140px;">Name:</td>
                            <td style="padding: 8px 0; color: #333; font-weight: 600;">{record.get('full_name', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">Tech ID:</td>
                            <td style="padding: 8px 0; color: #333; font-weight: 600;">{record.get('tech_id', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">District:</td>
                            <td style="padding: 8px 0; color: #333;">{record.get('district', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">State:</td>
                            <td style="padding: 8px 0; color: #333;">{record.get('state', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">Referred By:</td>
                            <td style="padding: 8px 0; color: #333;">{record.get('referred_by', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">Industries:</td>
                            <td style="padding: 8px 0; color: #333;">{industries_str}</td>
                        </tr>
                    </table>
                </div>
                
                <!-- Vehicle Information Card -->
                <div style="background: linear-gradient(to right, #f8f9fa, #ffffff); border-left: 4px solid #28a745; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                    <h3 style="color: #28a745; margin: 0 0 15px 0; font-size: 16px; text-transform: uppercase; letter-spacing: 1px;">
                        🚗 Vehicle Information
                    </h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px 0; color: #666; width: 140px;">Year:</td>
                            <td style="padding: 8px 0; color: #333; font-weight: 600;">{record.get('year', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">Make:</td>
                            <td style="padding: 8px 0; color: #333; font-weight: 600;">{record.get('make', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">Model:</td>
                            <td style="padding: 8px 0; color: #333; font-weight: 600;">{record.get('model', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">VIN:</td>
                            <td style="padding: 8px 0; color: #333; font-family: monospace;">{record.get('vin', 'N/A')}</td>
                        </tr>
                    </table>
                </div>
                
                <!-- Documentation Card -->
                <div style="background: linear-gradient(to right, #f8f9fa, #ffffff); border-left: 4px solid #ffc107; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                    <h3 style="color: #856404; margin: 0 0 15px 0; font-size: 16px; text-transform: uppercase; letter-spacing: 1px;">
                        📋 Documentation
                    </h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px 0; color: #666; width: 140px;">Insurance Exp:</td>
                            <td style="padding: 8px 0; color: #333;">{record.get('insurance_exp', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">Registration Exp:</td>
                            <td style="padding: 8px 0; color: #333;">{record.get('registration_exp', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">Template Used:</td>
                            <td style="padding: 8px 0; color: #333;">{record.get('template_used', 'N/A')}</td>
                        </tr>
                    </table>
                </div>
                
                <!-- Files Summary -->
                <div style="background: #f8f9fa; border-radius: 8px; padding: 15px; margin-bottom: 20px; text-align: center;">
                    <p style="margin: 0; color: #666; font-size: 14px;">
                        <strong>Files Uploaded:</strong>
                        Vehicle Photos: {len(record.get('vehicle_photos_paths', [])) if record.get('vehicle_photos_paths') else 0} |
                        Insurance: {len(record.get('insurance_docs_paths', [])) if record.get('insurance_docs_paths') else 0} |
                        Registration: {len(record.get('registration_docs_paths', [])) if record.get('registration_docs_paths') else 0}
                    </p>
                </div>
                
                <!-- Notes -->
                {"" if not record.get('comment') else f'''
                <div style="background: #fff3cd; border-radius: 8px; padding: 15px; margin-bottom: 20px;">
                    <h4 style="color: #856404; margin: 0 0 10px 0; font-size: 14px;">📝 Additional Notes:</h4>
                    <p style="margin: 0; color: #333; font-size: 14px;">{record.get("comment", "")}</p>
                </div>
                '''}
                
            </div>
            
            <!-- Footer -->
            <div style="background-color: #2c3e50; padding: 20px; text-align: center;">
                <p style="color: rgba(255,255,255,0.8); margin: 0; font-size: 12px;">
                    This is an automated notification from the BYOV Enrollment System
                </p>
                <p style="color: rgba(255,255,255,0.6); margin: 10px 0 0 0; font-size: 11px;">
                    Sears Home Services | BYOV Program
                </p>
            </div>
            
        </div>
    </body>
    </html>
    """
    
    return html


def get_plain_text_body(record):
    """Generate plain text email body as fallback."""
    industries_list = record.get('industry', record.get('industries', []))
    industries_str = ", ".join(industries_list) if industries_list else "None"
    
    submission_date = record.get('submission_date', '')
    if submission_date:
        try:
            dt = datetime.fromisoformat(submission_date)
            submission_date = dt.strftime("%m/%d/%Y")
        except Exception:
            pass
    
    return f"""
SEARS HOME SERVICES - BYOV Enrollment System
=============================================

A new BYOV enrollment has been submitted.

TECHNICIAN INFORMATION
----------------------
Name:               {record.get('full_name','')}
Tech ID:            {record.get('tech_id','')}
District:           {record.get('district','')}
State:              {record.get('state', 'N/A')}
Referred By:        {record.get('referred_by', '')}
Industries:         {industries_str}

VEHICLE INFORMATION
-------------------
Year:               {record.get('year','')}
Make:               {record.get('make','')}
Model:              {record.get('model','')}
VIN:                {record.get('vin','')}

DOCUMENTATION
-------------
Insurance Exp:      {record.get('insurance_exp','')}
Registration Exp:   {record.get('registration_exp','')}
Template Used:      {record.get('template_used', 'N/A')}

FILES UPLOADED
--------------
Vehicle Photos:         {len(record.get('vehicle_photos_paths', [])) if record.get('vehicle_photos_paths') else 0} files
Insurance Documents:    {len(record.get('insurance_docs_paths', [])) if record.get('insurance_docs_paths') else 0} files
Registration Documents: {len(record.get('registration_docs_paths', [])) if record.get('registration_docs_paths') else 0} files

ADDITIONAL NOTES
----------------
{record.get('comment', 'None')}

Submitted: {submission_date}

Files are attached to this email when feasible. If the files are too large,
they are available via the BYOV Admin Dashboard.

This is an automated notification from the BYOV Enrollment System.
"""


def send_email_notification(record, recipients=None, subject=None, attach_pdf_only=False):
    """Send an email notification about an enrollment record.

    This function mirrors the email behavior used by the main app but is
    contained in a separate module so it can be invoked from other tools
    (admin dashboard, cron jobs, etc.).
    
    Args:
        record: Enrollment record dictionary
        recipients: Email recipient(s) - string or list
        subject: Custom subject line
        attach_pdf_only: If True, only attach the signed PDF (for HR emails)
    
    Returns True on success, False otherwise.
    """
    email_config = st.secrets.get("email", {})

    sender = email_config.get("sender")
    app_password = email_config.get("app_password")
    default_recipient = email_config.get("recipient")

    if recipients:
        if isinstance(recipients, str):
            recipient_list = [r.strip() for r in recipients.split(',') if r.strip()]
        elif isinstance(recipients, (list, tuple)):
            recipient_list = [r for r in recipients if r]
        else:
            recipient_list = [str(recipients)]
    else:
        recipient_list = [default_recipient] if default_recipient else []

    subject = subject or f"New BYOV Enrollment: {record.get('full_name','Unknown')} (Tech {record.get('tech_id','N/A')})"

    html_body = get_sears_html_template(record)
    plain_body = get_plain_text_body(record)

    msg = MIMEMultipart('alternative')
    msg["From"] = sender or os.getenv("SENDGRID_FROM_EMAIL") or "no-reply@shs.com"
    msg["To"] = ", ".join(recipient_list) if recipient_list else ""
    msg["Date"] = formatdate(localtime=True)
    msg["Subject"] = subject
    
    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    files = []
    
    if attach_pdf_only:
        pdf_path = record.get('signature_pdf_path')
        if pdf_path:
            if file_storage.file_exists(pdf_path):
                files.append(pdf_path)
    else:
        file_keys = [
            'signature_pdf_path',
            'vehicle_photos_paths',
            'insurance_docs_paths',
            'registration_docs_paths'
        ]
        for k in file_keys:
            v = record.get(k)
            if not v:
                continue
            if isinstance(v, list):
                for p in v:
                    if p and file_storage.file_exists(p):
                        files.append(p)
            else:
                if isinstance(v, str) and file_storage.file_exists(v):
                    files.append(v)

    try:
        MAX_ATTACHMENT_SIZE = 20 * 1024 * 1024

        def get_file_size(path):
            try:
                if file_storage.is_object_storage_path(path):
                    content = file_storage.read_file(path)
                    return len(content) if content else 0
                return os.path.getsize(path)
            except Exception:
                return 0

        total_size = sum(get_file_size(p) for p in files) if files else 0

        if files and total_size > MAX_ATTACHMENT_SIZE:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                for p in files:
                    arcname = os.path.basename(p)
                    try:
                        content = file_storage.read_file(p)
                        if content:
                            zf.writestr(arcname, content)
                    except Exception:
                        pass
            zip_buffer.seek(0)
            zipped_size = len(zip_buffer.getvalue())
            if zipped_size <= MAX_ATTACHMENT_SIZE:
                part = MIMEApplication(zip_buffer.read())
                part.add_header('Content-Disposition', 'attachment', filename='enrollment_files.zip')
                msg.attach(part)
        else:
            for p in files:
                try:
                    content = file_storage.read_file(p)
                    if content:
                        ctype, encoding = mimetypes.guess_type(p)
                        if ctype is None:
                            ctype = 'application/octet-stream'
                        maintype, subtype = ctype.split('/', 1)
                        part = MIMEApplication(content, _subtype=subtype)
                        part.add_header('Content-Disposition', 'attachment', filename=os.path.basename(p))
                        msg.attach(part)
                except Exception:
                    continue

        sg_key = email_config.get("sendgrid_api_key") or os.getenv("SENDGRID_API_KEY")
        sg_from = email_config.get("sendgrid_from_email") or os.getenv("SENDGRID_FROM_EMAIL") or sender
        
        if sg_key and sg_from and recipient_list:
            try:
                sg_payload = {
                    "personalizations": [{"to": [{"email": r} for r in recipient_list]}],
                    "from": {"email": sg_from, "name": "Sears Home Services BYOV"},
                    "subject": subject,
                    "content": [
                        {"type": "text/plain", "value": plain_body},
                        {"type": "text/html", "value": html_body}
                    ]
                }
                
                attachments = []
                for p in files:
                    try:
                        content = file_storage.read_file(p)
                        if content:
                            ctype, _ = mimetypes.guess_type(p)
                            if ctype is None:
                                ctype = 'application/octet-stream'
                            attachments.append({
                                "content": base64.b64encode(content).decode('utf-8'),
                                "filename": os.path.basename(p),
                                "type": ctype,
                                "disposition": "attachment"
                            })
                    except Exception:
                        pass
                
                if attachments:
                    sg_payload["attachments"] = attachments
                
                resp = requests.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    headers={
                        "Authorization": f"Bearer {sg_key}",
                        "Content-Type": "application/json"
                    },
                    data=json.dumps(sg_payload),
                    timeout=30
                )
                
                if 200 <= resp.status_code < 300:
                    return True
                else:
                    st.warning(f"SendGrid failed ({resp.status_code}); falling back to SMTP if configured.")
            except Exception as e:
                st.warning(f"SendGrid error: {e}; falling back to SMTP if configured.")

        if not sender or not app_password or not recipient_list:
            if not sg_key:
                st.warning("Email credentials not fully configured. Please set up SendGrid API key or Gmail SMTP credentials.")
            return False

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, app_password)
            server.sendmail(sender, recipient_list, msg.as_string())
        return True
        
    except Exception as e:
        st.error(f"Email sending failed: {str(e)}")
        return False


def send_pdf_to_hr(record, hr_email, custom_subject=None):
    """Send the signed PDF to HR with a custom recipient.
    
    Args:
        record: Enrollment record dictionary (must include signature_pdf_path)
        hr_email: HR email address to send to
        custom_subject: Optional custom subject line
    
    Returns True on success, False otherwise.
    """
    if not hr_email:
        st.error("Please enter an HR email address.")
        return False
    
    subject = custom_subject or f"BYOV Signed Agreement - {record.get('full_name', 'Unknown')} (Tech ID: {record.get('tech_id', 'N/A')})"
    
    return send_email_notification(
        record,
        recipients=hr_email,
        subject=subject,
        attach_pdf_only=True
    )


def get_email_config_status():
    """Get the current email configuration status for display."""
    email_config = st.secrets.get("email", {})
    
    sg_key = email_config.get("sendgrid_api_key") or os.getenv("SENDGRID_API_KEY")
    sg_from = email_config.get("sendgrid_from_email") or os.getenv("SENDGRID_FROM_EMAIL")
    gmail_sender = email_config.get("sender")
    gmail_password = email_config.get("app_password")
    
    status = {
        "sendgrid_configured": bool(sg_key and sg_from),
        "sendgrid_from": sg_from or "Not configured",
        "gmail_configured": bool(gmail_sender and gmail_password),
        "gmail_sender": gmail_sender or "Not configured",
        "primary_method": "SendGrid" if sg_key else ("Gmail SMTP" if gmail_sender else "Not configured")
    }
    
    return status
