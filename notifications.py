import io
import os
import zipfile
import mimetypes
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.utils import formatdate
from datetime import datetime

import streamlit as st


def send_email_notification(record, recipients=None, subject=None):
    """Send an email notification about an enrollment record.

    This function mirrors the email behavior used by the main app but is
    contained in a separate module so it can be invoked from other tools
    (admin dashboard, cron jobs, etc.).
    Returns True on success, False otherwise.
    """
    # Read email config from Streamlit secrets
    email_config = st.secrets.get("email", {})

    sender = email_config.get("sender")
    app_password = email_config.get("app_password")
    default_recipient = email_config.get("recipient")

    # recipients override: can be a string (single email) or list of emails
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

    industries_str = ", ".join(record.get('industries', [])) if record.get('industries') else "None"

    submission_date = record.get('submission_date', '')
    if submission_date:
        try:
            dt = datetime.fromisoformat(submission_date)
            submission_date = dt.strftime("%m/%d/%Y")
        except Exception:
            pass

    body = f"""
A new BYOV enrollment has been submitted.

TECHNICIAN INFORMATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Name:               {record.get('full_name','')}
Tech ID:            {record.get('tech_id','')}
District:           {record.get('district','')}
State:              {record.get('state', 'N/A')}
Referred By:        {record.get('referred_by', '')}
Industries:         {industries_str}

VEHICLE INFORMATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Year:               {record.get('year','')}
Make:               {record.get('make','')}
Model:              {record.get('model','')}
VIN:                {record.get('vin','')}

DOCUMENTATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Insurance Exp:      {record.get('insurance_exp','')}
Registration Exp:   {record.get('registration_exp','')}
Template Used:      {record.get('template_used', 'N/A')}

FILES UPLOADED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Vehicle Photos:         {len(record.get('vehicle_photos_paths', [])) if record.get('vehicle_photos_paths') else 0} files
Insurance Documents:    {len(record.get('insurance_docs_paths', [])) if record.get('insurance_docs_paths') else 0} files
Registration Documents: {len(record.get('registration_docs_paths', [])) if record.get('registration_docs_paths') else 0} files

ADDITIONAL NOTES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{record.get('comment', 'None')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Submitted: {submission_date}

Files are attached to this email when feasible. If the files are too large,
they are available via the BYOV Admin Dashboard.

This is an automated notification from the BYOV Enrollment System.
"""

    msg = MIMEMultipart()
    msg["From"] = sender or "no-reply@example.com"
    msg["To"] = ", ".join(recipient_list) if recipient_list else ""
    msg["Date"] = formatdate(localtime=True)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    # Collect file paths referenced in the record
    file_keys = [
        'signature_pdf_path',
        'vehicle_photos_paths',
        'insurance_docs_paths',
        'registration_docs_paths'
    ]
    files = []
    for k in file_keys:
        v = record.get(k)
        if not v:
            continue
        if isinstance(v, list):
            for p in v:
                if p and os.path.exists(p):
                    files.append(p)
        else:
            if isinstance(v, str) and os.path.exists(v):
                files.append(v)

    try:
        MAX_ATTACHMENT_SIZE = 20 * 1024 * 1024  # 20 MB

        total_size = sum(os.path.getsize(p) for p in files) if files else 0

        if files and total_size > MAX_ATTACHMENT_SIZE:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                for p in files:
                    arcname = os.path.basename(p)
                    try:
                        zf.write(p, arcname=arcname)
                    except Exception:
                        pass
            zip_buffer.seek(0)
            zipped_size = len(zip_buffer.getvalue())
            if zipped_size <= MAX_ATTACHMENT_SIZE:
                part = MIMEApplication(zip_buffer.read())
                part.add_header('Content-Disposition', 'attachment', filename='enrollment_files.zip')
                msg.attach(part)
            else:
                summary = '\n'.join([f"- {os.path.basename(p)} ({os.path.getsize(p)/(1024*1024):.1f} MB)" for p in files])
                extra = "\n\nFiles are too large to include in this email. Files are stored in the BYOV Admin Dashboard:\n" + summary
                msg.attach(MIMEText(extra, 'plain'))
        else:
            for p in files:
                try:
                    ctype, encoding = mimetypes.guess_type(p)
                    if ctype is None:
                        ctype = 'application/octet-stream'
                    maintype, subtype = ctype.split('/', 1)
                    with open(p, 'rb') as fp:
                        part = MIMEApplication(fp.read(), _subtype=subtype)
                        part.add_header('Content-Disposition', 'attachment', filename=os.path.basename(p))
                        msg.attach(part)
                except Exception:
                    continue

        if not sender or not app_password or not recipient_list:
            st.warning("Email credentials or recipient(s) not fully configured; skipping email send.")
            return False

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, app_password)
            # sendmail expects sender, list of recipients
            server.sendmail(sender, recipient_list, msg.as_string())
        return True
    except Exception as e:
        st.error(f"Email sending failed: {str(e)}")
        return False

