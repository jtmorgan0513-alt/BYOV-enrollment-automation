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
        logo_section = f"""
        <div style="text-align: center; padding: 20px; background-color: #ffffff; border-bottom: 2px solid #0066CC;">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 120" width="300" height="90" style="display:block; margin: 0 auto;">
  <!-- Sears text -->
  <text x="20" y="80" font-family="Arial, sans-serif" font-size="72" font-weight="bold" fill="#0066CC">sears</text>
  <!-- Home Services text -->
  <text x="20" y="110" font-family="Arial, sans-serif" font-size="18" font-weight="600" fill="#333333" letter-spacing="4">HOME SERVICES</text>
  <!-- House icon -->
  <circle cx="320" cy="50" r="20" fill="#00CC99"/>
  <path d="M315 50 L320 45 L325 50 L325 60 L315 60 Z" fill="white"/>
</svg>
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
                
                <!-- Footer -->
                <div style="background-color: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center;">
                    <p style="color: #666; margin: 0; font-size: 12px;">
                        This is an automated notification from the BYOV Enrollment System.
                        <br>Please review the enrollment details and take appropriate action.
                    </p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html


def get_plain_text_body(record):
    """Generate a plain text version of the email for clients that don't support HTML."""
    text = f"""BYOV Enrollment Submitted

Technician Information:
- Name: {record.get('full_name', 'N/A')}
- Tech ID: {record.get('tech_id', 'N/A')}
- District: {record.get('district', 'N/A')}
- State: {record.get('state', 'N/A')}
- Referred By: {record.get('referred_by', 'N/A')}

Vehicle Information:
- Year: {record.get('year', 'N/A')}
- Make: {record.get('make', 'N/A')}
- Model: {record.get('model', 'N/A')}
- VIN: {record.get('vin', 'N/A')}

Documentation:
- Insurance Expires: {record.get('insurance_exp', 'N/A')}
- Registration Expires: {record.get('registration_exp', 'N/A')}

This is an automated message from the BYOV Enrollment System.
"""
    return text


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
            for file_path in files:
                try:
                    content = file_storage.read_file(file_path)
                    if content:
                        filename = os.path.basename(file_path)
                        part = MIMEApplication(content)
                        part.add_header('Content-Disposition', 'attachment', filename=filename)
                        msg.attach(part)
                except Exception:
                    pass

        sg_key = email_config.get("sendgrid_api_key") or os.getenv("SENDGRID_API_KEY")
        sg_from = email_config.get("sendgrid_from_email") or os.getenv("SENDGRID_FROM_EMAIL")
        
        if sg_key and recipient_list:
            try:
                sg_payload = {
                    "personalizations": [{"to": [{"email": r} for r in recipient_list]}],
                    "from": {"email": sg_from or sender or "notifications@shs.com"},
                    "subject": subject,
                    "content": [
                        {"type": "text/plain", "value": plain_body},
                        {"type": "text/html", "value": html_body}
                    ]
                }
                
                if files:
                    attachments = []
                    for file_path in files:
                        try:
                            content = file_storage.read_file(file_path)
                            if content:
                                filename = os.path.basename(file_path)
                                b64_content = base64.b64encode(content).decode() if isinstance(content, bytes) else base64.b64encode(content.encode()).decode()
                                attachments.append({
                                    "content": b64_content,
                                    "type": "application/octet-stream",
                                    "filename": filename
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
