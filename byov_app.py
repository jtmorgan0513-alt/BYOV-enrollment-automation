import json
import os
import re
import shutil
from datetime import date, datetime
import io

import streamlit as st
import uuid
import requests
import time
import logging

from streamlit_drawable_canvas import st_canvas
from PIL import Image
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
# AgGrid is optional; the admin dashboard uses a server-side table by default

# Shared DB module (SQLite)
import database
from database import get_enrollment_by_id, get_documents_for_enrollment
from notifications import send_email_notification
from admin_dashboard import page_admin_control_center
import backup_database


DATA_FILE = "enrollments.json"

# State to template mapping
STATE_TEMPLATE_MAP = {
    "CA": "template_2.pdf",
    "WA": "template_2.pdf",
    "IL": "template_2.pdf",
}
DEFAULT_TEMPLATE = "template_1.pdf"

# US States list (used in admin forms)
US_STATES = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
    "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
    "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
    "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
    "New Hampshire", "New Jersey", "New Mexico", "New York",
    "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
    "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
    "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
    "West Virginia", "Wisconsin", "Wyoming"
]

INDUSTRIES = ["Cook", "Dish", "Laundry", "Micro", "Ref", "HVAC", "L&G"]


def load_enrollments():
    """Compatibility loader: return enrollments enriched with document paths.

    The application previously used a JSON file structure. The new
    `database` module stores enrollments and documents separately; this
    function adapts DB rows to the legacy record shape expected by the
    rest of the app (including *_paths lists and `signature_pdf_path`).
    """
    rows = database.get_all_enrollments()
    records = []
    for r in rows:
        rec = dict(r)  # copy
        # populate documents
        docs = database.get_documents_for_enrollment(rec.get('id'))
        rec['vehicle_photos_paths'] = [d['file_path'] for d in docs if d['doc_type'] == 'vehicle']
        rec['insurance_docs_paths'] = [d['file_path'] for d in docs if d['doc_type'] == 'insurance']
        rec['registration_docs_paths'] = [d['file_path'] for d in docs if d['doc_type'] == 'registration']
        sigs = [d['file_path'] for d in docs if d['doc_type'] == 'signature']
        rec['signature_pdf_path'] = sigs[0] if sigs else None
        # keep backward-compatible keys
        records.append(rec)
    return records


def save_enrollments(records):
    """Legacy no-op: new DB is authoritative. Kept for compatibility."""
    return


def delete_enrollment(identifier: str) -> tuple[bool, str]:
    """Delete enrollment and associated files from DB and filesystem.

    `identifier` may be the numeric enrollment id or the technician id.
    """
    try:
        # Find enrollment by id or tech_id
        rows = database.get_all_enrollments()
        target = None
        for r in rows:
            if str(r.get('id')) == str(identifier) or str(r.get('tech_id', '')) == str(identifier):
                target = r
                break

        if not target:
            return False, f"Record not found for Tech ID or ID: {identifier}"

        enrollment_id = target.get('id')

        # collect file paths from documents
        docs = database.get_documents_for_enrollment(enrollment_id)
        files_to_delete = [d['file_path'] for d in docs if d.get('file_path')]

        deleted_files = 0
        for p in files_to_delete:
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                    deleted_files += 1
                except Exception:
                    pass

        # delete parent upload folder if present (assumes uploaded files in uploads/ID_*/...)
        if files_to_delete:
            upload_dir = os.path.dirname(os.path.dirname(files_to_delete[0]))
            if os.path.exists(upload_dir) and os.path.isdir(upload_dir):
                try:
                    shutil.rmtree(upload_dir)
                except Exception:
                    pass

        # delete from DB (documents cascade)
        database.delete_enrollment(enrollment_id)

        return True, f"✅ Successfully deleted enrollment ID {enrollment_id} and {deleted_files} associated files."
    except Exception as e:
        return False, f"❌ Error deleting enrollment: {e}"


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = name.strip('. ')
    return name or 'unnamed'


def create_upload_folder(tech_id: str, record_id: str) -> str:
    safe_tech_id = sanitize_filename(tech_id)
    folder_name = f"{safe_tech_id}_{record_id}"
    base_path = os.path.join("uploads", folder_name)
    os.makedirs(os.path.join(base_path, "vehicle"), exist_ok=True)
    os.makedirs(os.path.join(base_path, "insurance"), exist_ok=True)
    os.makedirs(os.path.join(base_path, "registration"), exist_ok=True)
    os.makedirs("pdfs", exist_ok=True)
    return base_path


def save_uploaded_files(uploaded_files, folder_path: str, prefix: str) -> list:
    """Save uploaded files and compress images for email notifications."""
    file_paths = []
    for idx, uploaded_file in enumerate(uploaded_files, 1):
        ext = os.path.splitext(uploaded_file.name)[1].lower()
        filename = f"{prefix}_{idx}{ext}"
        path = os.path.join(folder_path, filename)
        
        # Compress images (JPG, JPEG, PNG) for email notifications
        if ext in ['.jpg', '.jpeg', '.png']:
            try:
                img = Image.open(uploaded_file)
                
                # Convert to RGB if needed (for PNG with alpha)
                if img.mode in ('RGBA', 'LA', 'P'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = background
                
                # Resize for email-friendly size (max 1200px on longest side)
                max_size = 1200
                if max(img.size) > max_size:
                    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                
                # Save with higher compression for smaller file size
                # Quality 75 provides good balance between size and quality
                img.save(path, 'JPEG', quality=75, optimize=True)
                
                # Log file size reduction
                try:
                    original_size = len(uploaded_file.getvalue())
                    compressed_size = os.path.getsize(path)
                    reduction = ((original_size - compressed_size) / original_size) * 100
                    if reduction > 0:
                        print(f"Compressed {filename}: {original_size/1024:.1f}KB → {compressed_size/1024:.1f}KB ({reduction:.1f}% reduction)")
                except Exception:
                    pass
                
            except Exception as e:
                # If compression fails, save original
                print(f"Warning: Image compression failed for {filename}: {e}")
                with open(path, 'wb') as f:
                    uploaded_file.seek(0)
                    f.write(uploaded_file.getbuffer())
        else:
            # Non-image files: save as-is
            with open(path, 'wb') as f:
                f.write(uploaded_file.getbuffer())
        
        file_paths.append(path)
    return file_paths


def generate_signed_pdf(template_path: str, signature_image, output_path: str,
                        sig_x: int = 90, sig_y: int = 450, date_x: int = 310, date_y: int = 450) -> bool:
    """Generate a PDF with signature and date overlay on page 6 (index 5).
    Returns True on success, False on failure.
    """
    try:
        reader = PdfReader(template_path)
        writer = PdfWriter()

        # Create signature/date overlay
        packet = io.BytesIO()
        can = canvas.Canvas(packet, pagesize=letter)

        # Draw signature image if provided
        if signature_image is not None:
            temp_sig_path = "temp_signature.png"
            signature_image.save(temp_sig_path, format='PNG')
            can.drawImage(temp_sig_path, sig_x, sig_y, width=120, height=40,
                          preserveAspectRatio=True, mask='auto')
            try:
                os.remove(temp_sig_path)
            except Exception:
                pass

        # Draw date
        can.setFont("Helvetica", 10)
        current_date = datetime.now().strftime("%m/%d/%Y")
        can.drawString(date_x, date_y, current_date)

        can.save()
        packet.seek(0)

        overlay_pdf = PdfReader(packet)

        # Merge overlay onto each page, but ensure page 6 (index 5) receives the overlay
        for i in range(len(reader.pages)):
            page = reader.pages[i]
            if i == 5 and len(overlay_pdf.pages) > 0:
                page.merge_page(overlay_pdf.pages[0])
            writer.add_page(page)

        with open(output_path, "wb") as f:
            writer.write(f)

        return True
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        try:
            st.error(f"PDF generation error: {str(e)}")
            st.error(f"Details: {error_details}")
        except Exception:
            pass
        return False


def show_money_rain(count: int = 30, duration_ms: int = 5000):
    """Render a falling money (dollar) animation using pure HTML/CSS.

    Uses CSS keyframes only (no <script>) so it works reliably on
    Streamlit Cloud and newer Streamlit versions with stricter JS policies.
    The overlay fades out automatically after the given duration.
    """
    try:
        # Build bill divs with slight randomization for left position and delay
        bills = []
        for i in range(count):
            left = (i * 73) % 100  # spread across width
            delay = (i % 7) * 0.15
            dur = 3 + (i % 5) * 0.4
            rotate = (i * 37) % 360
            scale = 0.8 + (i % 3) * 0.15
            bills.append(
                f'<div class="bill" style="left:{left}%; animation-delay:{delay}s; animation-duration:{dur}s; transform: rotate({rotate}deg) scale({scale});">💵</div>'
            )

        fade_delay_s = max(0, duration_ms) / 1000.0

        html = f"""
        <style>
        .money-rain-wrapper {{
            pointer-events: none;
            position: fixed;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            overflow: hidden;
            z-index: 99999;
            opacity: 1;
            animation: fadeOut 0.6s ease-out forwards;
            animation-delay: {fade_delay_s}s;
        }}
        .money-rain-wrapper .bill {{
            position: absolute;
            top: -10%;
            font-size: 28px;
            will-change: transform, opacity;
            opacity: 0.95;
            text-shadow: 0 1px 0 rgba(0,0,0,0.12);
            filter: drop-shadow(0 4px 8px rgba(0,0,0,0.12));
            animation-name: fallAndRotate;
            animation-timing-function: linear;
            animation-iteration-count: 1;
        }}

        @keyframes fallAndRotate {{
            0% {{ transform: translateY(-10vh) rotate(0deg); opacity: 1; }}
            70% {{ opacity: 1; }}
            100% {{ transform: translateY(110vh) rotate(360deg); opacity: 0; }}
        }}

        @keyframes fadeOut {{
            to {{ opacity: 0; visibility: hidden; }}
        }}
        </style>

        <div class="money-rain-wrapper">
            {''.join(bills)}
        </div>
        """
        st.markdown(html, unsafe_allow_html=True)
    except Exception:
        # Silent fallback to built-in balloons if HTML injection is blocked
        try:
            st.balloons()
        except Exception:
            pass

# send_email_notification was moved to `notifications.py` to allow reuse by the
# admin control center without importing the whole Streamlit app.

def decode_vin(vin: str):
    vin = vin.strip().upper()
    if len(vin) < 11:
        return {}

    try:
        url = f"https://vpic.nhtsa.dot.gov/api/vehicles/decodevinvaluesextended/{vin}?format=json"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        results = data.get("Results", [])
        if not results:
            return {}

        result = results[0]

        year = result.get("ModelYear") or ""
        make = result.get("Make") or ""
        model = result.get("Model") or ""

        if not (year or make or model):
            return {}

        return {
            "year": year,
            "make": make,
            "model": model,
        }

    except Exception:
        return {}


def post_to_dashboard(record: dict, enrollment_id: int) -> dict:
    """Create technician in Replit dashboard with complete data and photo uploads.
    
    Authentication Flow:
    1. POST /api/login with username/password to get session cookie
    2. POST /api/technicians with complete enrollment data using session
    3. Upload photos using GCS flow (get URL → PUT file → save photo record)
    
    Returns status dict with photo_count for UI messaging.
    """
    try:
        # Get configuration from Streamlit secrets
        dashboard_url = st.secrets["replit"]["REPLIT_DASHBOARD_URL"]
        username = st.secrets["replit"]["REPLIT_DASHBOARD_USERNAME"]
        password = st.secrets["replit"]["REPLIT_DASHBOARD_PASSWORD"]
    except Exception:
        # Fallback to environment variables if secrets not available
        dashboard_url = os.getenv("REPLIT_DASHBOARD_URL", "https://byovdashboard.replit.app")
        username = os.getenv("REPLIT_DASHBOARD_USERNAME", "admin")
        password = os.getenv("REPLIT_DASHBOARD_PASSWORD", "admin123")
    
    try:
        from datetime import datetime
        
        # Step 1: Create session and login
        session = requests.Session()
        
        login_payload = {
            "username": username,
            "password": password
        }
        
        login_resp = session.post(
            f"{dashboard_url}/api/login",
            json=login_payload,
            timeout=10
        )
        
        if not login_resp.ok:
            return {
                "error": f"Login failed with status {login_resp.status_code}",
                "body": login_resp.text[:200]
            }
        
        # Step 2: Format dates for dashboard (ISO to YYYY-MM-DD)
        def format_date(date_str):
            if not date_str:
                return None
            try:
                dt = datetime.fromisoformat(date_str)
                return dt.strftime("%Y-%m-%d")
            except Exception:
                return None
        
        submission_date = record.get("submission_date", "")
        date_started = format_date(submission_date) or datetime.now().strftime("%Y-%m-%d")
        # Accept multiple possible field names coming from DB or legacy code
        insurance_exp = format_date(
            record.get("insurance_exp") or record.get("insurance_expiration") or record.get("insuranceExpiration")
        )
        registration_exp = format_date(
            record.get("registration_exp") or record.get("registration_expiration") or record.get("registrationExpiration")
        )
        
        # Step 3: Check if technician already exists
        tech_id = record.get("tech_id", "").upper()  # MUST BE UPPERCASE
        if not tech_id:
            return {"error": "record missing tech_id"}
        
        check_resp = session.get(
            f"{dashboard_url}/api/technicians",
            params={"techId": tech_id},
            timeout=10
        )
        
        if check_resp.ok:
            try:
                existing = check_resp.json()
                if isinstance(existing, list) and existing:
                    return {"status": "exists", "photo_count": 0}
            except Exception:
                pass
        
        # Step 4: Format industry as comma-separated string (accept 'industry' or 'industries')
        industry_raw = record.get('industry')
        if industry_raw is None:
            industry_raw = record.get('industries', [])
        if isinstance(industry_raw, list):
            industry = ", ".join(industry_raw) if industry_raw else ""
        else:
            industry = str(industry_raw) if industry_raw else ""

        # Referred by (accept either 'referred_by' or 'referredBy')
        referred_by_val = record.get('referred_by') or record.get('referredBy') or ""

        # Step 5: Create technician payload with complete field mapping
        payload = {
            "name": record.get("full_name"),
            "techId": tech_id,  # UPPERCASE
            "region": record.get("state"),
            "district": record.get("district"),
            "referredBy": referred_by_val,
            "enrollmentStatus": "Enrolled",  # Always "Enrolled" on approval
            "dateStartedByov": date_started,
            "vinNumber": record.get("vin"),
            "vehicleMake": record.get("make"),
            "vehicleModel": record.get("model"),
            "vehicleYear": record.get("year"),
            "industry": industry,  # Comma-separated
            "insuranceExpiration": insurance_exp,  # YYYY-MM-DD
            "registrationExpiration": registration_exp  # YYYY-MM-DD
        }
        
        # Step 6: POST to create technician
        create_resp = session.post(
            f"{dashboard_url}/api/technicians",
            json=payload,
            timeout=15
        )
        
        if not (200 <= create_resp.status_code < 300):
            return {
                "error": f"dashboard responded {create_resp.status_code}",
                "body": create_resp.text[:200]
            }
        
        # Get created technician ID from response
        try:
            tech_data = create_resp.json()
            dashboard_tech_id = tech_data.get("id")
        except Exception:
            return {"error": "Failed to parse technician response"}
        
        if not dashboard_tech_id:
            return {"error": "No technician ID in response"}
        
        # Step 7: Upload photos using GCS flow
        photo_count = 0
        failed_uploads = []

        # Simple logging helper for diagnosing dashboard sync issues
        def dashboard_log(message: str):
            try:
                os.makedirs('logs', exist_ok=True)
                with open(os.path.join('logs', 'dashboard_sync.log'), 'a', encoding='utf-8') as lf:
                    lf.write(f"{datetime.now().isoformat()} {message}\n")
            except Exception:
                pass

        # Generic retry wrapper for operations that return a requests.Response
        def retry_request(func, attempts=3, backoff_base=0.5):
            last_exc = None
            for attempt in range(1, attempts + 1):
                try:
                    resp = func()
                    # If callable returned a Response-like object, check .ok
                    if hasattr(resp, 'ok'):
                        if resp.ok:
                            return resp
                        else:
                            raise RuntimeError(f"status_{resp.status_code}")
                    # Otherwise return value directly
                    return resp
                except Exception as e:
                    last_exc = e
                    dashboard_log(f"Retry attempt {attempt} failed: {e}")
                    if attempt < attempts:
                        time.sleep(backoff_base * (2 ** (attempt - 1)))
            raise last_exc

        # If record doesn't include file paths, try to load from local DB using enrollment_id
        vehicle_paths = []
        insurance_paths = []
        registration_paths = []
        try:
            if record.get("vehicle_photos_paths"):
                vehicle_paths = list(record.get("vehicle_photos_paths") or [])
            if record.get("insurance_docs_paths"):
                insurance_paths = list(record.get("insurance_docs_paths") or [])
            if record.get("registration_docs_paths"):
                registration_paths = list(record.get("registration_docs_paths") or [])

            # Fallback: fetch from database documents if enrollment_id provided
            if enrollment_id and not (vehicle_paths or insurance_paths or registration_paths):
                docs = database.get_documents_for_enrollment(enrollment_id)
                for d in docs:
                    p = d.get('file_path')
                    if not p:
                        continue
                    if d.get('doc_type') == 'vehicle':
                        vehicle_paths.append(p)
                    elif d.get('doc_type') == 'insurance':
                        insurance_paths.append(p)
                    elif d.get('doc_type') == 'registration':
                        registration_paths.append(p)
        except Exception:
            # If DB access fails, continue and attempt uploads for any paths present
            pass

        from mimetypes import guess_type

        category_to_paths = {
            'vehicle': vehicle_paths,
            'insurance': insurance_paths,
            'registration': registration_paths
        }

        # Upload files to GCS and collect registration entries. We'll attempt a
        # batch register endpoint on the dashboard first (/photos/batch). If that
        # endpoint isn't supported or fails, we fall back to per-photo POSTs.
        uploaded_entries = []  # each: {uploadURL, category, mimeType, path}

        for category, paths in category_to_paths.items():
            for photo_path in (paths or []):
                if not photo_path or not os.path.exists(photo_path):
                    failed_uploads.append({'path': photo_path, 'reason': 'missing'})
                    continue

                try:
                    # Get upload URL from dashboard (with retries)
                    try:
                        upload_req = retry_request(lambda: session.post(
                            f"{dashboard_url}/api/objects/upload",
                            json={"category": category},
                            timeout=10
                        ), attempts=3, backoff_base=0.6)
                    except Exception as e:
                        dashboard_log(f"Failed to get upload URL for {photo_path}: {e}")
                        failed_uploads.append({'path': photo_path, 'reason': str(e)})
                        continue

                    upload_data = upload_req.json()
                    gcs_url = upload_data.get("uploadURL")
                    if not gcs_url:
                        dashboard_log(f"No uploadURL returned for {photo_path}: {upload_data}")
                        failed_uploads.append({'path': photo_path, 'reason': 'no_upload_url'})
                        continue

                    # Upload file to GCS (with retries)
                    mime_type, _ = guess_type(photo_path)
                    if not mime_type:
                        mime_type = 'application/octet-stream'

                    try:
                        def do_put():
                            with open(photo_path, 'rb') as f:
                                r = requests.put(gcs_url, data=f, headers={"Content-Type": mime_type}, timeout=60)
                                return r
                        gcs_resp = retry_request(do_put, attempts=3, backoff_base=0.6)
                    except Exception as e:
                        dashboard_log(f"GCS PUT failed for {photo_path}: {e}")
                        failed_uploads.append({'path': photo_path, 'reason': str(e)})
                        continue

                    dashboard_log(f"Uploaded {photo_path} to GCS: {gcs_url}")

                    # Append to batch registration list
                    uploaded_entries.append({
                        'uploadURL': gcs_url,
                        'category': category,
                        'mimeType': mime_type,
                        'path': photo_path
                    })

                except Exception as exc:
                    dashboard_log(f"Unexpected error handling {photo_path}: {exc}")
                    failed_uploads.append({'path': photo_path, 'reason': str(exc)})
                    continue

        # Attempt batch registration if we have entries
        if uploaded_entries:
            try:
                batch_payload = {'photos': [
                    { 'uploadURL': e['uploadURL'], 'category': e['category'], 'mimeType': e['mimeType'] }
                    for e in uploaded_entries
                ]}

                batch_resp = session.post(
                    f"{dashboard_url}/api/technicians/{dashboard_tech_id}/photos/batch",
                    json=batch_payload,
                    timeout=20
                )

                if batch_resp.ok:
                    # Assume batch returns list of registered photos or a success status
                    try:
                        resp_data = batch_resp.json()
                        registered = len(resp_data) if isinstance(resp_data, list) else len(uploaded_entries)
                    except Exception:
                        registered = len(uploaded_entries)
                    photo_count += registered
                    dashboard_log(f"Batch registered {registered} photos for technician {dashboard_tech_id}")
                else:
                    dashboard_log(f"Batch registration failed with status {batch_resp.status_code}; falling back to per-photo registration")
                    # Batch not supported or failed: fall back to per-photo registration
                    for e in uploaded_entries:
                        try:
                            photo_payload = {
                                'uploadURL': e['uploadURL'],
                                'category': e['category'],
                                'mimeType': e['mimeType']
                            }
                            try:
                                photo_resp = retry_request(lambda: session.post(
                                    f"{dashboard_url}/api/technicians/{dashboard_tech_id}/photos",
                                    json=photo_payload,
                                    timeout=10
                                ), attempts=3, backoff_base=0.6)
                                photo_count += 1
                                dashboard_log(f"Registered photo {e.get('path')} for tech {dashboard_tech_id}")
                            except Exception as reg_exc:
                                dashboard_log(f"Photo registration failed for {e.get('path')}: {reg_exc}")
                                failed_uploads.append({'path': e.get('path'), 'reason': str(reg_exc)})
                        except Exception as exc:
                            dashboard_log(f"Per-photo registration unexpected error: {exc}")
                            failed_uploads.append({'path': e.get('path'), 'reason': str(exc)})
            except Exception as exc:
                # If batch attempt itself errored, attempt per-photo registration
                for e in uploaded_entries:
                    try:
                        photo_payload = {
                            'uploadURL': e['uploadURL'],
                            'category': e['category'],
                            'mimeType': e['mimeType']
                        }
                        try:
                            photo_resp = retry_request(lambda: session.post(
                                f"{dashboard_url}/api/technicians/{dashboard_tech_id}/photos",
                                json=photo_payload,
                                timeout=10
                            ), attempts=3, backoff_base=0.6)
                            photo_count += 1
                            dashboard_log(f"Registered photo {e.get('path')} for tech {dashboard_tech_id} after batch error")
                        except Exception as reg_exc:
                            dashboard_log(f"Per-photo registration failed for {e.get('path')} after batch error: {reg_exc}")
                            failed_uploads.append({'path': e.get('path'), 'reason': str(reg_exc)})
                    except Exception as exc2:
                        failed_uploads.append({'path': e.get('path'), 'reason': str(exc2)})

        result = {"status": "created", "photo_count": photo_count}
        if failed_uploads:
            result['failed_uploads'] = failed_uploads
        return result
            
    except Exception as e:
        return {"error": str(e)}


def post_to_dashboard_single_request(record: dict, enrollment_id: int = None, endpoint_path="/api/external/technicians") -> dict:
    """
    Create technician and attach photos in a single request using the external
    API that accepts base64-embedded photos.

    Payload shape follows the external API specification. Photos are
    included as objects with `category` and `base64` (either data URL or raw
    base64). Enforces 10MB per photo limit.
    """
    try:
        # Config
        dashboard_url = st.secrets.get("replit", {}).get("REPLIT_DASHBOARD_URL") or os.getenv("REPLIT_DASHBOARD_URL")
        username = st.secrets.get("replit", {}).get("REPLIT_DASHBOARD_USERNAME") or os.getenv("REPLIT_DASHBOARD_USERNAME")
        password = st.secrets.get("replit", {}).get("REPLIT_DASHBOARD_PASSWORD") or os.getenv("REPLIT_DASHBOARD_PASSWORD")
    except Exception:
        dashboard_url = os.getenv("REPLIT_DASHBOARD_URL", "https://byovdashboard.replit.app")
        username = os.getenv("REPLIT_DASHBOARD_USERNAME", "admin")
        password = os.getenv("REPLIT_DASHBOARD_PASSWORD", "admin123")

    if not dashboard_url:
        return {"error": "dashboard url not configured"}

    session = requests.Session()
    try:
        login_resp = session.post(f"{dashboard_url}/api/login", json={"username": username, "password": password}, timeout=10)
        if not login_resp.ok:
            return {"error": f"Login failed {login_resp.status_code}", "body": login_resp.text[:200]}
    except Exception as e:
        return {"error": f"Login exception: {e}"}

    # Helper to format dates to YYYY-MM-DD
    from datetime import datetime
    def format_date(date_str):
        if not date_str:
            return None
        try:
            dt = datetime.fromisoformat(date_str)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return None

    # Tech id
    tech_id = (record.get('tech_id') or record.get('techId') or '').upper()
    if not tech_id:
        return {"error": "missing tech_id"}

    # Build payload mapping according to external API
    payload = {
        "name": record.get("full_name") or record.get("name"),
        "techId": tech_id,
        "region": record.get("region") or record.get("state"),
        "district": record.get("district"),
        "enrollmentStatus": record.get("enrollmentStatus", "Enrolled"),
        "truckId": record.get("truckId") or record.get("truck_id"),
        "mobilePhoneNumber": record.get("mobilePhoneNumber") or record.get("mobile") or record.get("phone"),
        "techEmail": record.get("techEmail") or record.get("email"),
        "cityState": record.get("cityState"),
        "vinNumber": record.get("vin") or record.get("vinNumber"),
        "insuranceExpiration": format_date(record.get("insurance_exp") or record.get("insuranceExpiration")),
        "registrationExpiration": format_date(record.get("registration_exp") or record.get("registrationExpiration")),
    }

    # Optional fields: vehicleMake/Model/Year/industry/dateStartedByov
    if record.get('make'):
        payload['vehicleMake'] = record.get('make')
    if record.get('model'):
        payload['vehicleModel'] = record.get('model')
    if record.get('year'):
        payload['vehicleYear'] = record.get('year')
    industry_raw = record.get('industry') if record.get('industry') is not None else record.get('industries', [])
    if isinstance(industry_raw, (list, tuple)):
        payload['industry'] = ", ".join(industry_raw)
    elif industry_raw:
        payload['industry'] = str(industry_raw)
    date_started = format_date(record.get('submission_date') or record.get('dateStartedByov'))
    if date_started:
        payload['dateStartedByov'] = date_started

    # Collect documents (file paths) to include as base64 photos
    docs = []
    try:
        if enrollment_id:
            docs = database.get_documents_for_enrollment(enrollment_id) or []
        else:
            docs = record.get('documents') or []
    except Exception:
        docs = record.get('documents') or []

    photos = []
    failed_photos = []
    import base64 as _b64, mimetypes as _mimetypes
    MAX_BYTES = 10 * 1024 * 1024  # 10MB

    for d in docs:
        path = d.get('file_path') if isinstance(d, dict) else None
        category = d.get('doc_type') or d.get('category') or 'vehicle'
        if not path or not os.path.exists(path):
            failed_photos.append({'path': path, 'error': 'missing'})
            continue
        try:
            size = os.path.getsize(path)
            if size > MAX_BYTES:
                failed_photos.append({'path': path, 'error': 'size_exceeded', 'size': size})
                continue
            with open(path, 'rb') as fh:
                b = fh.read()
            raw_b64 = _b64.b64encode(b).decode('ascii')
            mime = _mimetypes.guess_type(path)[0] or 'application/octet-stream'
            # Prefer data URL when we have a known mime (matches example)
            if mime.startswith('image/') or mime == 'application/pdf':
                data_url = f"data:{mime};base64,{raw_b64}"
                photos.append({'category': category, 'base64': data_url})
            else:
                photos.append({'category': category, 'base64': raw_b64})
        except Exception as e:
            failed_photos.append({'path': path, 'error': str(e)})

    if photos:
        payload['photos'] = photos

    # POST to external endpoint
    url = dashboard_url.rstrip('/') + endpoint_path
    try:
        resp = session.post(url, json=payload, timeout=30)
    except Exception as e:
        return {"error": f"request failed: {e}", "failed_photos": failed_photos}

    # Interpret response
    result = {"status_code": resp.status_code}
    try:
        resp_json = resp.json()
    except Exception:
        resp_json = {"raw_text": resp.text}
    result['response'] = resp_json
    result['photo_count'] = len(photos)
    if failed_photos:
        result['failed_photos'] = failed_photos

    # On success/partial, persist dashboard id if present
    tech_id_returned = None
    if isinstance(resp_json, dict):
        # Response may include technician obj or id
        tech = resp_json.get('technician') or resp_json.get('technicianCreated') or resp_json
        if isinstance(tech, dict):
            tech_id_returned = tech.get('id') or tech.get('techId')
        else:
            tech_id_returned = resp_json.get('id') or resp_json.get('technicianId')

    if enrollment_id and tech_id_returned:
        try:
            report = {"photo_count": len(photos)}
            if failed_photos:
                report['failed_uploads'] = failed_photos
            report['response'] = resp_json
            database.set_dashboard_sync_info(enrollment_id, dashboard_tech_id=str(tech_id_returned), report=report)
        except Exception:
            pass

    # Interpret status codes: 201 -> success, 207 -> partial
    if resp.status_code in (201, 207) or (200 <= resp.status_code < 300):
        return result
    else:
        return result


def create_technician_on_dashboard(record: dict) -> dict:
    """Create a technician on the external dashboard using admin credentials.

    Returns: {status: 'created'|'exists', dashboard_tech_id: str, error: str}
    """
    try:
        dashboard_url = st.secrets.get("replit", {}).get("REPLIT_DASHBOARD_URL") or os.getenv("REPLIT_DASHBOARD_URL")
        username = st.secrets.get("replit", {}).get("REPLIT_DASHBOARD_USERNAME") or os.getenv("REPLIT_DASHBOARD_USERNAME")
        password = st.secrets.get("replit", {}).get("REPLIT_DASHBOARD_PASSWORD") or os.getenv("REPLIT_DASHBOARD_PASSWORD")
    except Exception:
        dashboard_url = os.getenv("REPLIT_DASHBOARD_URL", "https://byovdashboard.replit.app")
        username = os.getenv("REPLIT_DASHBOARD_USERNAME", "admin")
        password = os.getenv("REPLIT_DASHBOARD_PASSWORD", "admin123")

    session = requests.Session()
    try:
        login_resp = session.post(f"{dashboard_url}/api/login", json={"username": username, "password": password}, timeout=10)
        if not login_resp.ok:
            return {"error": f"Login failed {login_resp.status_code}", "body": login_resp.text[:200]}
    except Exception as e:
        return {"error": f"Login exception: {e}"}

    # Format minimal fields same as post_to_dashboard
    from datetime import datetime
    def format_date(date_str):
        if not date_str:
            return None
        try:
            dt = datetime.fromisoformat(date_str)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return None

    submission_date = record.get("submission_date", "")
    date_started = format_date(submission_date) or datetime.now().strftime("%Y-%m-%d")

    tech_id = (record.get('tech_id') or '').upper()
    if not tech_id:
        return {"error": "missing tech_id"}

    # Format industry
    industry_raw = record.get('industry') if record.get('industry') is not None else record.get('industries', [])
    if isinstance(industry_raw, list):
        industry = ", ".join(industry_raw) if industry_raw else ""
    else:
        industry = str(industry_raw) if industry_raw else ""

    referred_by_val = record.get('referred_by') or record.get('referredBy') or ""

    payload = {
        "name": record.get("full_name"),
        "techId": tech_id,
        "region": record.get("state"),
        "district": record.get("district"),
        "referredBy": referred_by_val,
        "enrollmentStatus": "Enrolled",
        "dateStartedByov": date_started,
        "vinNumber": record.get("vin"),
        "vehicleMake": record.get("make"),
        "vehicleModel": record.get("model"),
        "vehicleYear": record.get("year"),
        "industry": industry,
        "insuranceExpiration": format_date(record.get("insurance_exp")),
        "registrationExpiration": format_date(record.get("registration_exp"))
    }

    try:
        create_resp = session.post(f"{dashboard_url}/api/technicians", json=payload, timeout=15)
        if not (200 <= create_resp.status_code < 300):
            return {"error": f"create responded {create_resp.status_code}", "body": create_resp.text[:200]}
        try:
            data = create_resp.json()
            dashboard_tech_id = data.get('id')
        except Exception:
            return {"error": "failed to parse create response"}
        if not dashboard_tech_id:
            return {"error": "no id returned"}
        return {"status": "created", "dashboard_tech_id": dashboard_tech_id}
    except Exception as e:
        return {"error": str(e)}


def upload_photos_for_technician(enrollment_id: int, dashboard_tech_id: str = None) -> dict:
    """Upload photos for a given enrollment to the dashboard technician id.

    If `dashboard_tech_id` is not provided, attempts to look up by tech_id on the dashboard.
    Returns: {photo_count: int, failed_uploads: [...]}
    """
    try:
        dashboard_url = st.secrets.get("replit", {}).get("REPLIT_DASHBOARD_URL") or os.getenv("REPLIT_DASHBOARD_URL")
        username = st.secrets.get("replit", {}).get("REPLIT_DASHBOARD_USERNAME") or os.getenv("REPLIT_DASHBOARD_USERNAME")
        password = st.secrets.get("replit", {}).get("REPLIT_DASHBOARD_PASSWORD") or os.getenv("REPLIT_DASHBOARD_PASSWORD")
    except Exception:
        dashboard_url = os.getenv("REPLIT_DASHBOARD_URL", "https://byovdashboard.replit.app")
        username = os.getenv("REPLIT_DASHBOARD_USERNAME", "admin")
        password = os.getenv("REPLIT_DASHBOARD_PASSWORD", "admin123")

    session = requests.Session()
    try:
        login_resp = session.post(f"{dashboard_url}/api/login", json={"username": username, "password": password}, timeout=10)
        if not login_resp.ok:
            return {"error": f"Login failed {login_resp.status_code}", "body": login_resp.text[:200]}
    except Exception as e:
        return {"error": f"Login exception: {e}"}

    # Load enrollment record and document paths
    try:
        record = database.get_enrollment_by_id(enrollment_id)
    except Exception:
        record = None

    if not record:
        return {"error": "enrollment not found"}

    tech_id = (record.get('tech_id') or '').upper()
    if not dashboard_tech_id:
        # Try to find technician by techId on dashboard
        try:
            check_resp = session.get(f"{dashboard_url}/api/technicians", params={"techId": tech_id}, timeout=10)
            if check_resp.ok:
                try:
                    existing = check_resp.json()
                    if isinstance(existing, list) and existing:
                        dashboard_tech_id = existing[0].get('id')
                except Exception:
                    pass
        except Exception:
            pass

    if not dashboard_tech_id:
        return {"error": "dashboard technician id not provided and lookup failed"}

    # Reuse upload logic from post_to_dashboard
    photo_count = 0
    failed_uploads = []

    def dashboard_log(message: str):
        try:
            os.makedirs('logs', exist_ok=True)
            with open(os.path.join('logs', 'dashboard_sync.log'), 'a', encoding='utf-8') as lf:
                lf.write(f"{datetime.now().isoformat()} {message}\n")
        except Exception:
            pass

    def retry_request(func, attempts=3, backoff_base=0.5):
        last_exc = None
        for attempt in range(1, attempts + 1):
            try:
                resp = func()
                if hasattr(resp, 'ok'):
                    if resp.ok:
                        return resp
                    else:
                        raise RuntimeError(f"status_{resp.status_code}")
                return resp
            except Exception as e:
                last_exc = e
                dashboard_log(f"Retry attempt {attempt} failed: {e}")
                if attempt < attempts:
                    time.sleep(backoff_base * (2 ** (attempt - 1)))
        raise last_exc

    # Collect file paths
    try:
        docs = database.get_documents_for_enrollment(enrollment_id)
        vehicle_paths = [d['file_path'] for d in docs if d['doc_type'] == 'vehicle']
        insurance_paths = [d['file_path'] for d in docs if d['doc_type'] == 'insurance']
        registration_paths = [d['file_path'] for d in docs if d['doc_type'] == 'registration']
    except Exception:
        vehicle_paths = record.get('vehicle_photos_paths', []) or []
        insurance_paths = record.get('insurance_docs_paths', []) or []
        registration_paths = record.get('registration_docs_paths', []) or []

    from mimetypes import guess_type

    category_to_paths = {
        'vehicle': vehicle_paths,
        'insurance': insurance_paths,
        'registration': registration_paths
    }

    uploaded_entries = []
    for category, paths in category_to_paths.items():
        for photo_path in (paths or []):
            if not photo_path or not os.path.exists(photo_path):
                failed_uploads.append({'path': photo_path, 'reason': 'missing'})
                continue
            try:
                try:
                    upload_req = retry_request(lambda: session.post(
                        f"{dashboard_url}/api/objects/upload",
                        json={"category": category},
                        timeout=10
                    ), attempts=3, backoff_base=0.6)
                except Exception as e:
                    dashboard_log(f"Failed to get upload URL for {photo_path}: {e}")
                    failed_uploads.append({'path': photo_path, 'reason': str(e)})
                    continue

                upload_data = upload_req.json()
                gcs_url = upload_data.get("uploadURL")
                if not gcs_url:
                    dashboard_log(f"No uploadURL returned for {photo_path}: {upload_data}")
                    failed_uploads.append({'path': photo_path, 'reason': 'no_upload_url'})
                    continue

                mime_type, _ = guess_type(photo_path)
                if not mime_type:
                    mime_type = 'application/octet-stream'

                try:
                    def do_put():
                        with open(photo_path, 'rb') as f:
                            r = requests.put(gcs_url, data=f, headers={"Content-Type": mime_type}, timeout=60)
                            return r
                    gcs_resp = retry_request(do_put, attempts=3, backoff_base=0.6)
                except Exception as e:
                    dashboard_log(f"GCS PUT failed for {photo_path}: {e}")
                    failed_uploads.append({'path': photo_path, 'reason': str(e)})
                    continue

                dashboard_log(f"Uploaded {photo_path} to GCS: {gcs_url}")
                uploaded_entries.append({'uploadURL': gcs_url, 'category': category, 'mimeType': mime_type, 'path': photo_path})
            except Exception as exc:
                dashboard_log(f"Unexpected error handling {photo_path}: {exc}")
                failed_uploads.append({'path': photo_path, 'reason': str(exc)})
                continue

    # Register uploaded entries
    if uploaded_entries:
        try:
            batch_payload = {'photos': [ {'uploadURL': e['uploadURL'], 'category': e['category'], 'mimeType': e['mimeType']} for e in uploaded_entries ]}
            batch_resp = session.post(f"{dashboard_url}/api/technicians/{dashboard_tech_id}/photos/batch", json=batch_payload, timeout=20)
            if batch_resp.ok:
                try:
                    resp_data = batch_resp.json()
                    registered = len(resp_data) if isinstance(resp_data, list) else len(uploaded_entries)
                except Exception:
                    registered = len(uploaded_entries)
                photo_count += registered
                dashboard_log(f"Batch registered {registered} photos for technician {dashboard_tech_id}")
            else:
                dashboard_log(f"Batch registration failed with status {batch_resp.status_code}; falling back to per-photo registration")
                for e in uploaded_entries:
                    try:
                        photo_payload = {'uploadURL': e['uploadURL'], 'category': e['category'], 'mimeType': e['mimeType']}
                        try:
                            photo_resp = retry_request(lambda: session.post(f"{dashboard_url}/api/technicians/{dashboard_tech_id}/photos", json=photo_payload, timeout=10), attempts=3, backoff_base=0.6)
                            photo_count += 1
                            dashboard_log(f"Registered photo {e.get('path')} for tech {dashboard_tech_id}")
                        except Exception as reg_exc:
                            dashboard_log(f"Photo registration failed for {e.get('path')}: {reg_exc}")
                            failed_uploads.append({'path': e.get('path'), 'reason': str(reg_exc)})
                    except Exception as exc:
                        dashboard_log(f"Per-photo registration unexpected error: {exc}")
                        failed_uploads.append({'path': e.get('path'), 'reason': str(exc)})
        except Exception as exc:
            for e in uploaded_entries:
                try:
                    photo_payload = {'uploadURL': e['uploadURL'], 'category': e['category'], 'mimeType': e['mimeType']}
                    try:
                        photo_resp = retry_request(lambda: session.post(f"{dashboard_url}/api/technicians/{dashboard_tech_id}/photos", json=photo_payload, timeout=10), attempts=3, backoff_base=0.6)
                        photo_count += 1
                        dashboard_log(f"Registered photo {e.get('path')} for tech {dashboard_tech_id} after batch error")
                    except Exception as reg_exc:
                        dashboard_log(f"Per-photo registration failed for {e.get('path')} after batch error: {reg_exc}")
                        failed_uploads.append({'path': e.get('path'), 'reason': str(reg_exc)})
                except Exception as exc2:
                    failed_uploads.append({'path': e.get('path'), 'reason': str(exc2)})

    report = {"photo_count": photo_count}
    if failed_uploads:
        report['failed_uploads'] = failed_uploads

    # Persist report to DB for retries
    try:
        database.set_dashboard_sync_info(enrollment_id, dashboard_tech_id=dashboard_tech_id, report=report)
    except Exception:
        pass

    result = {"photo_count": photo_count}
    if failed_uploads:
        result['failed_uploads'] = failed_uploads
    return result


def retry_failed_uploads(enrollment_id: int) -> dict:
    """Retry previously failed photo uploads recorded in `last_upload_report`.

    Returns: {retried_count: int, remaining_failed: int, still_failed: [...]} 
    """
    try:
        dashboard_url = st.secrets.get("replit", {}).get("REPLIT_DASHBOARD_URL") or os.getenv("REPLIT_DASHBOARD_URL")
        username = st.secrets.get("replit", {}).get("REPLIT_DASHBOARD_USERNAME") or os.getenv("REPLIT_DASHBOARD_USERNAME")
        password = st.secrets.get("replit", {}).get("REPLIT_DASHBOARD_PASSWORD") or os.getenv("REPLIT_DASHBOARD_PASSWORD")
    except Exception:
        dashboard_url = os.getenv("REPLIT_DASHBOARD_URL", "https://byovdashboard.replit.app")
        username = os.getenv("REPLIT_DASHBOARD_USERNAME", "admin")
        password = os.getenv("REPLIT_DASHBOARD_PASSWORD", "admin123")

    session = requests.Session()
    try:
        login_resp = session.post(f"{dashboard_url}/api/login", json={"username": username, "password": password}, timeout=10)
        if not login_resp.ok:
            return {"error": f"Login failed {login_resp.status_code}", "body": login_resp.text[:200]}
    except Exception as e:
        return {"error": f"Login exception: {e}"}

    # Load enrollment and report
    try:
        record = database.get_enrollment_by_id(enrollment_id)
    except Exception:
        record = None
    if not record:
        return {"error": "enrollment not found"}

    # Determine dashboard technician id
    dashboard_id = record.get('dashboard_tech_id')
    tech_id = (record.get('tech_id') or '').upper()
    if not dashboard_id:
        try:
            check_resp = session.get(f"{dashboard_url}/api/technicians", params={"techId": tech_id}, timeout=10)
            if check_resp.ok:
                try:
                    existing = check_resp.json()
                    if isinstance(existing, list) and existing:
                        dashboard_id = existing[0].get('id')
                except Exception:
                    pass
        except Exception:
            pass

    if not dashboard_id:
        return {"error": "dashboard technician id not found"}

    # Parse last_upload_report
    last_report = record.get('last_upload_report')
    if not last_report:
        return {"error": "no last_upload_report available"}
    try:
        if isinstance(last_report, str):
            report_obj = json.loads(last_report)
        else:
            report_obj = last_report
    except Exception:
        report_obj = last_report if isinstance(last_report, dict) else {}

    failed = report_obj.get('failed_uploads', []) if isinstance(report_obj, dict) else []
    if not failed:
        return {"retried_count": 0, "remaining_failed": 0}

    # Map file paths to document categories
    try:
        docs = database.get_documents_for_enrollment(enrollment_id)
        path_to_category = {d.get('file_path'): d.get('doc_type') for d in docs}
    except Exception:
        path_to_category = {}

    from mimetypes import guess_type

    retried = 0
    still_failed = []

    def dashboard_log(message: str):
        try:
            os.makedirs('logs', exist_ok=True)
            with open(os.path.join('logs', 'dashboard_sync.log'), 'a', encoding='utf-8') as lf:
                lf.write(f"{datetime.now().isoformat()} {message}\n")
        except Exception:
            pass

    def retry_request(func, attempts=3, backoff_base=0.5):
        last_exc = None
        for attempt in range(1, attempts + 1):
            try:
                resp = func()
                if hasattr(resp, 'ok'):
                    if resp.ok:
                        return resp
                    else:
                        raise RuntimeError(f"status_{resp.status_code}")
                return resp
            except Exception as e:
                last_exc = e
                dashboard_log(f"Retry attempt {attempt} failed: {e}")
                if attempt < attempts:
                    time.sleep(backoff_base * (2 ** (attempt - 1)))
        raise last_exc

    for entry in failed:
        path = entry.get('path') if isinstance(entry, dict) else None
        if not path or not os.path.exists(path):
            still_failed.append({'path': path, 'reason': 'missing'})
            continue

        category = path_to_category.get(path, 'vehicle')
        try:
            try:
                upload_req = retry_request(lambda: session.post(f"{dashboard_url}/api/objects/upload", json={"category": category}, timeout=10), attempts=3, backoff_base=0.6)
            except Exception as e:
                dashboard_log(f"Failed to get upload URL for {path}: {e}")
                still_failed.append({'path': path, 'reason': str(e)})
                continue

            upload_data = upload_req.json()
            gcs_url = upload_data.get('uploadURL')
            if not gcs_url:
                dashboard_log(f"No uploadURL returned for {path}: {upload_data}")
                still_failed.append({'path': path, 'reason': 'no_upload_url'})
                continue

            mime_type, _ = guess_type(path)
            if not mime_type:
                mime_type = 'application/octet-stream'

            try:
                def do_put():
                    with open(path, 'rb') as f:
                        r = requests.put(gcs_url, data=f, headers={"Content-Type": mime_type}, timeout=60)
                        return r
                gcs_resp = retry_request(do_put, attempts=3, backoff_base=0.6)
            except Exception as e:
                dashboard_log(f"GCS PUT failed for {path}: {e}")
                still_failed.append({'path': path, 'reason': str(e)})
                continue

            # Register photo for technician
            try:
                photo_payload = {'uploadURL': gcs_url, 'category': category, 'mimeType': mime_type}
                try:
                    reg_resp = retry_request(lambda: session.post(f"{dashboard_url}/api/technicians/{dashboard_id}/photos", json=photo_payload, timeout=10), attempts=3, backoff_base=0.6)
                    retried += 1
                    dashboard_log(f"Retried and registered photo {path} for tech {dashboard_id}")
                except Exception as reg_exc:
                    dashboard_log(f"Photo registration failed for {path}: {reg_exc}")
                    still_failed.append({'path': path, 'reason': str(reg_exc)})
            except Exception as exc:
                dashboard_log(f"Unexpected registration error for {path}: {exc}")
                still_failed.append({'path': path, 'reason': str(exc)})

        except Exception as exc:
            dashboard_log(f"Unexpected error retrying {path}: {exc}")
            still_failed.append({'path': path, 'reason': str(exc)})

    # Update report and persist
    new_photo_count = (report_obj.get('photo_count', 0) if isinstance(report_obj, dict) else 0) + retried
    new_report = {"photo_count": new_photo_count}
    if still_failed:
        new_report['failed_uploads'] = still_failed

    try:
        database.set_dashboard_sync_info(enrollment_id, dashboard_tech_id=dashboard_id, report=new_report)
    except Exception:
        pass

    return {"retried_count": retried, "remaining_failed": len(still_failed), "still_failed": still_failed}


# ------------------------
# WIZARD STEP FUNCTIONS
# ------------------------
def wizard_step_1():
    """Step 1: Technician Info & Industry Selection"""
    st.subheader("Technician Information")
    
    # Initialize wizard_data in session state if not exists
    if 'wizard_data' not in st.session_state:
        st.session_state.wizard_data = {}
    
    data = st.session_state.wizard_data
    
    # Technician fields
    full_name = st.text_input(
        "Full Name", 
        value=data.get('full_name', ''),
        key="wiz_full_name"
    )
    
    tech_id = st.text_input(
        "Tech ID", 
        value=data.get('tech_id', ''),
        key="wiz_tech_id"
    )
    
    district = st.text_input(
        "District", 
        value=data.get('district', ''),
        key="wiz_district"
    )

    referred_by = st.text_input(
        "Referred By",
        value=data.get('referred_by', ''),
        key="wiz_referred_by"
    )
    
    state_idx = 0
    saved_state = data.get('state')
    if saved_state and saved_state in US_STATES:
        state_idx = US_STATES.index(saved_state) + 1
    state = st.selectbox(
        "State", 
        [""] + US_STATES,
        index=state_idx,
        key="wiz_state"
    )
    
    # Industry selection
    st.subheader("Industry Selection")
    st.write("Select all industries that apply:")
    
    saved_industries = data.get('industry', data.get('industries', []))
    selected_industries = []
    
    cols = st.columns(4)
    for idx, industry in enumerate(INDUSTRIES):
        with cols[idx % 4]:
            checked = st.checkbox(
                industry, 
                value=industry in saved_industries,
                key=f"wiz_industry_{industry}"
            )
            if checked:
                selected_industries.append(industry)
    
    # Navigation
    st.markdown("---")
    
    # Validation
    errors = []
    if not full_name:
        errors.append("Full Name is required")
    if not tech_id:
        errors.append("Tech ID is required")
    if not district:
        errors.append("District is required")
    if not state:
        errors.append("State selection is required")
    
    if errors:
        st.warning("Please complete the following:\n" + "\n".join(f"• {msg}" for msg in errors))
    
    if st.button("Next ➡", disabled=bool(errors), type="primary", width='stretch'):
        # Save to session state
        st.session_state.wizard_data.update({
            'full_name': full_name,
            'tech_id': tech_id,
            'district': district,
            'state': state,
            'referred_by': referred_by,
            'industry': selected_industries,
            'industries': selected_industries
        })
        st.session_state.wizard_step = 2
        st.rerun()


def wizard_step_2():
    """Step 2: Vehicle Info & Documents"""
    st.subheader("Vehicle Information & Documents")
    
    data = st.session_state.wizard_data
    
    # VIN Section
    st.markdown("### Vehicle Identification")
    
    vin = st.text_input(
        "VIN (Vehicle Identification Number)", 
        value=data.get('vin', ''),
        key="wiz_vin"
    )
    
    decode_clicked = st.button("Decode VIN (lookup year/make/model)")
    
    if decode_clicked:
        vin_value = st.session_state.get("wiz_vin", "").strip()
        if not vin_value:
            st.warning("Enter a VIN above before decoding.")
        else:
            with st.spinner("Decoding VIN..."):
                decoded = decode_vin(vin_value)
                if decoded:
                    st.session_state.wizard_data['year'] = decoded.get("year", "")
                    st.session_state.wizard_data['make'] = decoded.get("make", "")
                    st.session_state.wizard_data['model'] = decoded.get("model", "")
                    st.success(
                        f"Decoded VIN: {decoded.get('year', '?')} "
                        f"{decoded.get('make', '?')} "
                        f"{decoded.get('model', '?')}"
                    )
                    st.rerun()
                else:
                    st.error("Could not decode VIN from the NHTSA API. Check the VIN and try again.")
    
        # Sync decoded values to session state keys if they exist
    if 'year' in data and 'wiz_year' not in st.session_state:
        st.session_state.wiz_year = data['year']
    if 'make' in data and 'wiz_make' not in st.session_state:
        st.session_state.wiz_make = data['make']
    if 'model' in data and 'wiz_model' not in st.session_state:
        st.session_state.wiz_model = data['model']
    
    col1, col2, col3 = st.columns(3)
    with col1:
        year = st.text_input(
            "Vehicle Year", 
            key="wiz_year"
        )
    with col2:
        make = st.text_input(
            "Vehicle Make", 
            key="wiz_make"
        )
    with col3:
        model = st.text_input(
            "Vehicle Model", 
            key="wiz_model"
        )
    
    st.markdown("---")
    
    # Vehicle Photos
    st.markdown("### Vehicle Photos")
    st.caption("Upload 4 photos minimum: Front, Back, Left Side, Right Side")
    
    vehicle_photos = st.file_uploader(
        "Vehicle Photos",
        accept_multiple_files=True,
        type=["jpg", "jpeg", "png", "pdf"],
        key="wiz_vehicle_photos",
        label_visibility="collapsed"
    )
    
    if vehicle_photos:
        if len(vehicle_photos) >= 4:
            st.success(f"✓ {len(vehicle_photos)} vehicle photos uploaded")
        else:
            st.warning(f"⚠ {len(vehicle_photos)} uploaded - need at least 4 vehicle photos")
    else:
        st.warning("⚠ No vehicle photos uploaded yet")
    
    st.markdown("---")
    
    # Registration
    st.markdown("### Registration")
    col1, col2 = st.columns(2)
    with col1:
        registration_exp_default = data.get('registration_exp')
        if isinstance(registration_exp_default, str):
            try:
                registration_exp_default = datetime.strptime(registration_exp_default, "%Y-%m-%d").date()
            except Exception:
                registration_exp_default = None
        registration_exp = st.date_input(
            "Registration Expiration Date",
            value=registration_exp_default if registration_exp_default else None,
            key="wiz_registration_exp"
        )
    
    with col2:
        registration_docs = st.file_uploader(
            "Registration Photo/Document",
            accept_multiple_files=True,
            type=["jpg", "jpeg", "png", "pdf"],
            key="wiz_registration_docs"
        )
        
        if registration_docs:
            st.success(f"✓ {len(registration_docs)} document(s) uploaded")
    
    st.markdown("---")
    
    # Insurance
    st.markdown("### Insurance")
    col1, col2 = st.columns(2)
    with col1:
        insurance_exp_default = data.get('insurance_exp')
        if isinstance(insurance_exp_default, str):
            try:
                insurance_exp_default = datetime.strptime(insurance_exp_default, "%Y-%m-%d").date()
            except Exception:
                insurance_exp_default = None
        insurance_exp = st.date_input(
            "Insurance Expiration Date",
            value=insurance_exp_default if insurance_exp_default else None,
            key="wiz_insurance_exp"
        )
    
    with col2:
        insurance_docs = st.file_uploader(
            "Insurance Photo/Document",
            accept_multiple_files=True,
            type=["jpg", "jpeg", "png", "pdf"],
            key="wiz_insurance_docs"
        )
        
        if insurance_docs:
            st.success(f"✓ {len(insurance_docs)} document(s) uploaded")
    
    # Navigation
    st.markdown("---")
    
    # Validation
    errors = []
    if not vin:
        errors.append("VIN is required")
    if not year or not make or not model:
        errors.append("Vehicle Year, Make, and Model are required")
    if not vehicle_photos or len(vehicle_photos) < 4:
        errors.append("At least 4 vehicle photos are required")
    if not registration_docs:
        errors.append("Registration document is required")
    if not registration_exp:
        errors.append("Registration expiration date is required")
    if not insurance_docs:
        errors.append("Insurance document is required")
    if not insurance_exp:
        errors.append("Insurance expiration date is required")
    
    can_proceed = len(errors) == 0
    
    if errors:
        st.warning("Please complete the following:\n" + "\n".join(f"• {msg}" for msg in errors))
    
    col_nav1, col_nav2 = st.columns([1, 1])
    with col_nav1:
        if st.button("⬅ Back", width='stretch'):
            st.session_state.wizard_step = 1
            st.rerun()
    
    with col_nav2:
        if st.button("Next ➡", disabled=not can_proceed, type="primary", width='stretch'):
            # Save to session state
            st.session_state.wizard_data.update({
                'vin': vin,
                'year': year,
                'make': make,
                'model': model,
                'vehicle_photos': vehicle_photos,
                'registration_exp': registration_exp,
                'registration_docs': registration_docs,
                'insurance_exp': insurance_exp,
                'insurance_docs': insurance_docs
            })
            st.session_state.wizard_step = 3
            st.rerun()


def wizard_step_3():
    """Step 3: BYOV Policy & Signature"""
    st.subheader("BYOV Policy Agreement")
    
    data = st.session_state.wizard_data
    
    # Determine template based on state
    state = data.get('state', '')
    state_abbrev = state[:2].upper() if len(state) > 2 else state.upper()
    template_file = STATE_TEMPLATE_MAP.get(state_abbrev, DEFAULT_TEMPLATE)
    
    st.info(f"📄 BYOV Policy for {state}")
    
    # PDF Download Section
    if os.path.exists(template_file):
        with open(template_file, "rb") as f:
            template_bytes = f.read()
        
        st.download_button(
            label="📥 Download BYOV Policy (Required)",
            data=template_bytes,
            file_name="BYOV_Policy.pdf",
            mime="application/pdf",
            help="Download and review this document before signing below",
            width='stretch'
        )
    else:
        st.error(f"⚠ Template file '{template_file}' not found. Please contact administrator.")
        st.stop()
    
    st.markdown("---")
    
    # Policy Acknowledgement
    st.markdown("### Policy Acknowledgement")
    
    st.markdown("""
    I confirm that I have opened and fully reviewed the BYOV Policy, including the mileage 
    reimbursement rules and current reimbursement rates. I understand that the first 35 minutes 
    of my morning commute and the first 35 minutes of my afternoon commute are not eligible for 
    reimbursement and must not be included when entering mileage.
    """)
    
    acknowledged = st.checkbox(
        "I acknowledge and agree to the terms stated above",
        value=data.get('acknowledged', False),
        key="wiz_acknowledged"
    )
    
    # Signature section (only show if acknowledged)
    signature_drawn = False
    canvas_result_data = None
    
    if acknowledged:
        st.markdown("---")
        st.markdown("### Signature")
        
        st.write("Please sign below:")
        
        # Signature canvas
        canvas_result = st_canvas(
            fill_color="rgba(255, 255, 255, 0)",
            stroke_width=2,
            stroke_color="#000000",
            background_color="#FFFFFF",
            height=200,
            width=600,
            drawing_mode="freedraw",
            key="wiz_signature_canvas",
        )
        
        canvas_result_data = canvas_result
        
        # Check if signature is drawn
        if canvas_result_data and canvas_result_data.image_data is not None:
            import numpy as np
            img_array = np.array(canvas_result_data.image_data)
            if img_array[:, :, 3].max() > 0:
                signature_drawn = True
                st.success("✓ Signature captured")
            else:
                st.info("Please sign in the box above")
    else:
        st.info("Please check the acknowledgement box above to reveal the signature box.")
    
    # Additional Comments
    st.markdown("---")
    comment = st.text_area(
        "Additional Comments (100 characters max)",
        value=data.get('comment', ''),
        max_chars=100,
        key="wiz_comment"
    )
    
    # Navigation
    st.markdown("---")
    
    # Validation
    can_proceed = acknowledged and signature_drawn
    
    if not can_proceed:
        errors = []
        if not acknowledged:
            errors.append("Please acknowledge the policy terms")
        if not signature_drawn:
            errors.append("Please provide your signature")
        
        st.warning("Please complete the following:\n" + "\n".join(f"• {msg}" for msg in errors))
    
    col_nav1, col_nav2 = st.columns([1, 1])
    with col_nav1:
        if st.button("⬅ Back", width='stretch'):
            st.session_state.wizard_step = 2
            st.rerun()
    
    with col_nav2:
        if st.button("Next ➡", disabled=not can_proceed, type="primary", width='stretch'):
            # Save signature and other data to session state
            st.session_state.wizard_data.update({
                'acknowledged': acknowledged,
                'template_file': template_file,
                'comment': comment
            })
            
            if canvas_result_data and canvas_result_data.image_data is not None:
                st.session_state.wizard_data['signature_image'] = canvas_result_data.image_data
            
            st.session_state.wizard_step = 4
            st.rerun()


def wizard_step_4():
    """Step 4: Review & Submit"""
    st.subheader("Review Your Enrollment")
    
    data = st.session_state.wizard_data
    
    st.write("Please review all information before submitting. Use the Back button if you need to make changes.")
    
    # Technician Info
    st.markdown("---")
    with st.container():
        st.markdown("#### 👤 Technician Information")
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Full Name:** {data.get('full_name', 'N/A')}")
            st.write(f"**Tech ID:** {data.get('tech_id', 'N/A')}")
        with col2:
            st.write(f"**District:** {data.get('district', 'N/A')}")
            st.write(f"**State:** {data.get('state', 'N/A')}")
            st.write(f"**Referred By:** {data.get('referred_by', 'N/A')}")
    
    # Industries
    st.markdown("---")
    with st.container():
        st.markdown("#### 🏭 Industries Selected")
        industries = data.get('industry', data.get('industries', []))
        if industries:
            st.write(", ".join(industries))
        else:
            st.write("None selected")
    
    # Vehicle Info
    st.markdown("---")
    with st.container():
        st.markdown("#### 🚗 Vehicle Information")
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**VIN:** {data.get('vin', 'N/A')}")
            st.write(f"**Year:** {data.get('year', 'N/A')}")
        with col2:
            st.write(f"**Make:** {data.get('make', 'N/A')}")
            st.write(f"**Model:** {data.get('model', 'N/A')}")
    
    # Documents
    st.markdown("---")
    with st.container():
        st.markdown("#### 📎 Documents Uploaded")
        col1, col2, col3 = st.columns(3)
        with col1:
            vehicle_count = len(data.get('vehicle_photos', []))
            st.success(f"✓ {vehicle_count} Vehicle Photos")
        with col2:
            insurance_count = len(data.get('insurance_docs', []))
            st.success(f"✓ {insurance_count} Insurance Doc(s)")
        with col3:
            registration_count = len(data.get('registration_docs', []))
            st.success(f"✓ {registration_count} Registration Doc(s)")
    
    # Expiration Dates
    st.markdown("---")
    with st.container():
        st.markdown("#### 📅 Expiration Dates")
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Insurance Expires:** {data.get('insurance_exp', 'N/A')}")
        with col2:
            st.write(f"**Registration Expires:** {data.get('registration_exp', 'N/A')}")
    
    # Policy Status
    st.markdown("---")
    with st.container():
        st.markdown("#### 📝 BYOV Policy")
        if data.get('acknowledged'):
            st.success("✓ Policy Acknowledged")
        if data.get('signature_image') is not None:
            st.success("✓ Signature Provided")
    
    # Comments
    if data.get('comment'):
        st.markdown("---")
        with st.container():
            st.markdown("#### 💬 Additional Comments")
            st.write(data.get('comment'))
    
    # Navigation & Submit
    st.markdown("---")
    
    col_nav1, col_nav2 = st.columns([1, 1])
    with col_nav1:
        if st.button("⬅ Go Back", width='stretch'):
            st.session_state.wizard_step = 3
            st.rerun()
    
    with col_nav2:
        submit_clicked = st.button("✅ Submit Enrollment", type="primary", width='stretch')
    
    if submit_clicked:
        with st.spinner("Processing enrollment..."):
            try:
                # Generate unique ID
                record_id = str(uuid.uuid4())
                
                # Create upload folders
                upload_base = create_upload_folder(data['tech_id'], record_id)
                
                # Save vehicle photos
                vehicle_folder = os.path.join(upload_base, "vehicle")
                vehicle_paths = save_uploaded_files(data['vehicle_photos'], vehicle_folder, "vehicle")
                
                # Save insurance documents
                insurance_folder = os.path.join(upload_base, "insurance")
                insurance_paths = save_uploaded_files(data['insurance_docs'], insurance_folder, "insurance")
                
                # Save registration documents
                registration_folder = os.path.join(upload_base, "registration")
                registration_paths = save_uploaded_files(data['registration_docs'], registration_folder, "registration")
                
                # Generate signed PDF
                signature_img = None
                if data.get('signature_image') is not None:
                    signature_img = Image.fromarray(data['signature_image'].astype('uint8'), 'RGBA')
                
                pdf_filename = f"{sanitize_filename(data['tech_id'])}_{record_id}.pdf"
                pdf_output_path = os.path.join("pdfs", pdf_filename)
                
                # Use EXACT signature positions - 6.25 inches from bottom
                sig_x = 90
                sig_y = 450
                date_x = 310
                date_y = 450
                
                pdf_success = generate_signed_pdf(
                    data['template_file'],
                    signature_img,
                    pdf_output_path,
                    sig_x=sig_x,
                    sig_y=sig_y,
                    date_x=date_x,
                    date_y=date_y
                )
                
                if not pdf_success:
                    st.error("❌ PDF generation failed. Cannot submit enrollment. Please try again.")
                    return
                
                # Create enrollment record in the database
                db_record = {
                    "full_name": data['full_name'],
                    "tech_id": data['tech_id'],
                    "district": data['district'],
                    "state": data['state'],
                    "referred_by": data.get('referred_by', ''),
                    # Store both new 'industry' and legacy 'industries' for compatibility
                    "industry": data.get('industry', data.get('industries', [])),
                    "industries": data.get('industries', data.get('industry', [])),
                    "year": data['year'],
                    "make": data['make'],
                    "model": data['model'],
                    "vin": data['vin'],
                    "insurance_exp": str(data['insurance_exp']),
                    "registration_exp": str(data['registration_exp']),
                    "template_used": data['template_file'],
                    "comment": data.get('comment', ''),
                    "submission_date": datetime.now().isoformat()
                }

                # Create a backup before making any DB writes
                try:
                    backup_database.backup_database()
                except Exception:
                    # Non-fatal: continue even if backup fails, but log to console
                    try:
                        print("Warning: backup failed before insert/update")
                    except Exception:
                        pass

                # Check for existing enrollment by tech_id or VIN to avoid duplicates
                existing = None
                try:
                    for e in database.get_all_enrollments():
                        if str(e.get('tech_id', '')).strip() and e.get('tech_id') == db_record.get('tech_id'):
                            existing = e
                            break
                        if db_record.get('vin') and e.get('vin') and e.get('vin') == db_record.get('vin'):
                            existing = e
                            break
                except Exception:
                    existing = None

                if existing:
                    # Update the existing enrollment instead of inserting a duplicate
                    enrollment_db_id = existing.get('id')
                    try:
                        database.update_enrollment(enrollment_db_id, db_record)
                    except Exception:
                        # If update fails, fallback to insert
                        enrollment_db_id = database.insert_enrollment(db_record)

                    # Add documents but avoid duplicates by file path
                    try:
                        existing_docs = database.get_documents_for_enrollment(enrollment_db_id)
                        existing_paths = {d.get('file_path') for d in existing_docs}
                    except Exception:
                        existing_paths = set()

                    for p in vehicle_paths:
                        if p not in existing_paths:
                            database.add_document(enrollment_db_id, 'vehicle', p)
                    for p in insurance_paths:
                        if p not in existing_paths:
                            database.add_document(enrollment_db_id, 'insurance', p)
                    for p in registration_paths:
                        if p not in existing_paths:
                            database.add_document(enrollment_db_id, 'registration', p)
                    if pdf_output_path and pdf_output_path not in existing_paths:
                        database.add_document(enrollment_db_id, 'signature', pdf_output_path)

                    created_new = False
                else:
                    # No existing record — insert new enrollment
                    enrollment_db_id = database.insert_enrollment(db_record)

                    # Store documents in DB and keep the filepaths for notification
                    for p in vehicle_paths:
                        database.add_document(enrollment_db_id, 'vehicle', p)
                    for p in insurance_paths:
                        database.add_document(enrollment_db_id, 'insurance', p)
                    for p in registration_paths:
                        database.add_document(enrollment_db_id, 'registration', p)
                    # signed PDF
                    database.add_document(enrollment_db_id, 'signature', pdf_output_path)

                    created_new = True

                # Build application-level record for notifications and UI
                record = {
                    "id": enrollment_db_id,
                    "tech_id": data['tech_id'],
                    "full_name": data['full_name'],
                    "referred_by": data.get('referred_by', ''),
                    "district": data['district'],
                    "state": data['state'],
                    "industry": data.get('industry', data.get('industries', [])),
                    "industries": data.get('industries', data.get('industry', [])),
                    "vin": data['vin'],
                    "year": data['year'],
                    "make": data['make'],
                    "model": data['model'],
                    "insurance_exp": str(data['insurance_exp']),
                    "registration_exp": str(data['registration_exp']),
                    "status": "Active",
                    "comment": data.get('comment', ''),
                    "template_used": data['template_file'],
                    "signature_pdf_path": pdf_output_path,
                    "vehicle_photos_paths": vehicle_paths,
                    "insurance_docs_paths": insurance_paths,
                    "registration_docs_paths": registration_paths,
                    "submission_date": datetime.now().isoformat()
                }

                # Send default email notification
                email_sent = send_email_notification(record)
                if email_sent:
                    banner_msg = "✅ Enrollment submitted successfully and email notification sent!"
                else:
                    banner_msg = "✅ Enrollment saved, but email notification failed. Administrator has been notified."

                # NOTE: Dashboard sync is now handled by admin approval in admin_dashboard.py
                # No automatic sync on submission - admin must review and approve first

                # Evaluate DB-backed notification rules for "On Submission"
                try:
                    rules = database.get_notification_rules()
                    sent_logs = database.get_sent_notifications(enrollment_db_id)
                    sent_rule_ids = {s.get('rule_id') for s in sent_logs}

                    for rule in rules:
                        # rule: dict with keys id, rule_name, trigger, days_before, recipients, enabled
                        if not rule.get('enabled'):
                            continue
                        if rule.get('trigger') != 'On Submission':
                            continue

                        rid = rule.get('id')
                        if rid in sent_rule_ids:
                            # already sent for this enrollment, skip
                            continue

                        recipients = rule.get('recipients') or []
                        subject = f"{rule.get('rule_name', 'BYOV Notification')}"

                        try:
                            ok = send_email_notification(record, recipients=recipients, subject=subject)
                            if ok:
                                database.log_notification_sent(enrollment_db_id, rid)
                        except Exception:
                            # Don't allow rule send failures to interrupt the user flow
                                pass
                except Exception:
                    # Non-fatal: if rules evaluation fails, continue
                    pass
                
                # Clear wizard data
                st.session_state.wizard_data = {}
                st.session_state.wizard_step = 1

                show_money_rain()

                # Show success message and banner
                st.markdown("---")
                st.success(banner_msg)
                
                if st.button("Submit Another Enrollment"):
                    st.rerun()
                
            except Exception as e:
                import traceback
                st.error(f"❌ Error processing enrollment: {str(e)}")
                st.error(f"Details: {traceback.format_exc()}")


# ------------------------
# NEW ENROLLMENT PAGE
# ------------------------
def page_new_enrollment():
    """Main enrollment page with wizard navigation"""
    
    # Initialize wizard step if not exists
    if 'wizard_step' not in st.session_state:
        st.session_state.wizard_step = 1
    
    # Progress indicator
    current_step = st.session_state.wizard_step
    
    # Progress bar
    progress_cols = st.columns(4)
    step_labels = [
        "Technician Info",
        "Vehicle & Docs",
        "Policy & Signature",
        "Review & Submit"
    ]
    
    for idx, (col, label) in enumerate(zip(progress_cols, step_labels), 1):
        with col:
            if idx < current_step:
                st.markdown(f"<div style='text-align: center; color: #28a745;'>✓ {label}</div>", unsafe_allow_html=True)
            elif idx == current_step:
                st.markdown(f"<div style='text-align: center; color: #007bff; font-weight: bold;'>● {label}</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div style='text-align: center; color: #6c757d;'>○ {label}</div>", unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Render appropriate step
    if current_step == 1:
        wizard_step_1()
    elif current_step == 2:
        wizard_step_2()
    elif current_step == 3:
        wizard_step_3()
    elif current_step == 4:
        wizard_step_4()
    else:
        st.error("Invalid wizard step")
        st.session_state.wizard_step = 1
        st.rerun()


# OLD PAGE - REMOVE EVERYTHING BELOW UNTIL ADMIN DASHBOARD
def page_new_enrollment_OLD():
    st.title("BYOV Vehicle Enrollment")
    st.caption("Submit your vehicle information for the Bring Your Own Vehicle program.")

    st.subheader("Technician & Vehicle Information")

    col1, col2 = st.columns(2)

    # Left column: tech info
    with col1:
        tech_id = st.text_input("Technician ID")
        full_name = st.text_input("Full Name")
        district = st.text_input("District Number")
        state = st.selectbox("State", [""] + US_STATES)

    # Right column: VIN + vehicle info
    with col2:
        vin = st.text_input("VIN (Vehicle Identification Number)", key="vin")

        decode_clicked = st.button("Decode VIN (lookup year/make/model)")

        if decode_clicked:
            vin_value = st.session_state.get("vin", "").strip()
            if not vin_value:
                st.warning("Enter a VIN above before decoding.")
            else:
                decoded = decode_vin(vin_value)
                if decoded:
                    # Pre-fill vehicle fields before they are instantiated
                    st.session_state["vehicle_year"] = decoded.get("year", "")
                    st.session_state["vehicle_make"] = decoded.get("make", "")
                    st.session_state["vehicle_model"] = decoded.get("model", "")
                    st.info(
                        f"Decoded VIN: {decoded.get('year', '?')} "
                        f"{decoded.get('make', '?')} "
                        f"{decoded.get('model', '?')}"
                    )
                else:
                    st.warning("Could not decode VIN from the NHTSA API. Check the VIN and try again.")

        year = st.text_input(
            "Vehicle Year",
            key="vehicle_year",
        )
        make = st.text_input(
            "Vehicle Make",
            key="vehicle_make",
        )
        model = st.text_input(
            "Vehicle Model",
            key="vehicle_model",
        )

    # Industry selection
    st.subheader("Industry Selection")
    st.write("Select all industries that apply:")
    
    industries = []
    cols = st.columns(4)
    for idx, industry in enumerate(INDUSTRIES):
        with cols[idx % 4]:
            if st.checkbox(industry, key=f"industry_{industry}"):
                industries.append(industry)

    st.subheader("Expiration Dates")
    col3, col4 = st.columns(2)
    with col3:
        insurance_exp = st.date_input("Insurance Expiration Date", value=None)
    with col4:
        registration_exp = st.date_input("Registration Expiration Date", value=None)
    
    comment = st.text_area("Additional Comments (100 characters max)", max_chars=100)
    
    # PDF Template download and signature section (MOVED BEFORE FILE UPLOADS)
    st.markdown("---")
    st.subheader("BYOV Program Agreement")
    
    # Determine which template to use
    template_file = DEFAULT_TEMPLATE
    if state:
        # Get state abbreviation
        state_abbrev = state[:2].upper()
        template_file = STATE_TEMPLATE_MAP.get(state_abbrev, DEFAULT_TEMPLATE)
    
    st.info(f"📄 Template for your state: **{template_file}**")
    
    # Download template button
    if os.path.exists(template_file):
        with open(template_file, "rb") as f:
            template_bytes = f.read()
        
        st.download_button(
            label="📥 Download BYOV Agreement Template (Required)",
            data=template_bytes,
            file_name=template_file,
            mime="application/pdf",
            help="Download and review this document before signing below"
        )
        
        # Track if user downloaded template
        if 'template_downloaded' not in st.session_state:
            st.session_state.template_downloaded = False
        
        if st.button("I have reviewed the template"):
            st.session_state.template_downloaded = True
            st.rerun()
    else:
        st.error(f"⚠ Template file '{template_file}' not found. Please contact administrator.")
    
    # Show acknowledgement and signature section after template review
    signature_drawn = False
    canvas_result_data = None
    
    if st.session_state.get('template_downloaded', False):
        st.markdown("---")
        st.subheader("Acknowledgement")
        
        st.markdown("""
        **ACKNOWLEDGEMENT**
        
        I confirm that I have opened and fully reviewed the BYOV Policy, including the mileage 
        reimbursement rules and current reimbursement rates. I understand that the first 35 minutes 
        of my morning commute and the first 35 minutes of my afternoon commute are not eligible for 
        reimbursement and must not be included when entering mileage.
        """)
        
        # Checkbox to confirm acknowledgement
        acknowledged = st.checkbox(
            "I acknowledge and agree to the terms stated above",
            key="acknowledgement_checkbox"
        )
        
        # Show signature section only after acknowledgement is checked
        if acknowledged:
            st.markdown("---")
            st.subheader("Signature")
            
            st.write("Please sign below:")
            
            # Signature canvas
            canvas_result = st_canvas(
                fill_color="rgba(255, 255, 255, 0)",  # Transparent
                stroke_width=2,
                stroke_color="#000000",  # Black stroke color
                background_color="#FFFFFF",  # White background
                height=200,
                width=600,
                drawing_mode="freedraw",
                key="signature_canvas",
            )
            
            # Check if signature is drawn
            canvas_result_data = canvas_result
            if canvas_result_data.image_data is not None:
                # Check if there's any non-white pixel
                import numpy as np
                img_array = np.array(canvas_result_data.image_data)
                if img_array[:, :, 3].max() > 0:  # Check alpha channel
                    signature_drawn = True
            
            if signature_drawn:
                st.success("✓ Signature captured")
            else:
                st.info("Please sign in the box above")
        else:
            st.info("Please check the acknowledgement box above to proceed with signature.")
    
    # File uploads section (MOVED AFTER SIGNATURE)
    st.markdown("---")
    st.subheader("Document Uploads")
    
    st.info("📸 Please upload clear, legible photos/documents. Accepted formats: JPG, JPEG, PNG, PDF")
    
    # Vehicle photos
    vehicle_photos = st.file_uploader(
        "Vehicle Photos (Front, Back, Left Side, Right Side - minimum 4 required)",
        accept_multiple_files=True,
        type=["jpg", "jpeg", "png", "pdf"],
        key="vehicle_photos"
    )
    
    if vehicle_photos:
        if len(vehicle_photos) >= 4:
            st.success(f"✓ {len(vehicle_photos)} vehicle photos uploaded")
        else:
            st.warning(f"⚠ {len(vehicle_photos)} uploaded - need at least 4 vehicle photos")
    else:
        st.warning("⚠ No vehicle photos uploaded yet")
    
    # Registration documents
    registration_docs = st.file_uploader(
        "Registration Document(s)",
        accept_multiple_files=True,
        type=["jpg", "jpeg", "png", "pdf"],
        key="registration_docs"
    )
    
    if registration_docs:
        st.success(f"✓ {len(registration_docs)} registration document(s) uploaded")
    
    # Insurance documents
    insurance_docs = st.file_uploader(
        "Insurance Document(s)",
        accept_multiple_files=True,
        type=["jpg", "jpeg", "png", "pdf"],
        key="insurance_docs"
    )
    
    if insurance_docs:
        st.success(f"✓ {len(insurance_docs)} insurance document(s) uploaded")
    
    # Submit button
    st.markdown("---")
    
    # Validation checks
    can_submit = True
    validation_messages = []
    
    if not tech_id or not full_name or not vin:
        can_submit = False
        validation_messages.append("Technician ID, Full Name, and VIN are required")
    
    if not state:
        can_submit = False
        validation_messages.append("State selection is required")
    
    if not vehicle_photos or len(vehicle_photos) < 4:
        can_submit = False
        validation_messages.append("At least 4 vehicle photos are required")
    
    if not registration_docs:
        can_submit = False
        validation_messages.append("Registration document(s) required")
    if not registration_exp:
        can_submit = False
        validation_messages.append("Registration expiration date is required")
    
    if not insurance_docs:
        can_submit = False
        validation_messages.append("Insurance document(s) required")
    if not insurance_exp:
        can_submit = False
        validation_messages.append("Insurance expiration date is required")
    
    if not st.session_state.get('template_downloaded', False):
        can_submit = False
        validation_messages.append("Please download and review the BYOV agreement template")
    
    if not signature_drawn:
        can_submit = False
        validation_messages.append("Signature is required")
    
    # Show validation messages
    if validation_messages:
        st.warning("Please complete the following:\n" + "\n".join(f"• {msg}" for msg in validation_messages))
    
    submitted = st.button("Submit Enrollment", disabled=not can_submit, type="primary")

    if submitted:
        with st.spinner("Processing enrollment..."):
            try:
                # Generate unique ID
                record_id = str(uuid.uuid4())
                
                # Create upload folders
                upload_base = create_upload_folder(tech_id, record_id)
                
                # Save vehicle photos
                vehicle_folder = os.path.join(upload_base, "vehicle")
                vehicle_paths = save_uploaded_files(vehicle_photos, vehicle_folder, "vehicle")
                
                # Save registration documents
                registration_folder = os.path.join(upload_base, "registration")
                registration_paths = save_uploaded_files(registration_docs, registration_folder, "registration")
                
                # Save insurance documents
                insurance_folder = os.path.join(upload_base, "insurance")
                insurance_paths = save_uploaded_files(insurance_docs, insurance_folder, "insurance")
                
                # Generate signed PDF
                signature_img = None
                if canvas_result_data and canvas_result_data.image_data is not None:
                    signature_img = Image.fromarray(canvas_result_data.image_data.astype('uint8'), 'RGBA')
                
                pdf_filename = f"{sanitize_filename(tech_id)}_{record_id}.pdf"
                pdf_output_path = os.path.join("pdfs", pdf_filename)
                
                # Use session state for signature position (default values or admin-adjusted)
                sig_x = st.session_state.get('sig_x', 90)
                sig_y = st.session_state.get('sig_y', 450)
                date_x = st.session_state.get('date_x', 310)
                date_y = st.session_state.get('date_y', 450)
                
                pdf_success = generate_signed_pdf(
                    template_file, 
                    signature_img, 
                    pdf_output_path,
                    sig_x=sig_x,
                    sig_y=sig_y,
                    date_x=date_x,
                    date_y=date_y
                )
                
                if not pdf_success:
                    st.error("❌ PDF generation failed. Cannot submit enrollment. Please try again.")
                    return
                
                # Create enrollment record
                records = load_enrollments()
                record = {
                    "id": record_id,
                    "tech_id": tech_id,
                    "full_name": full_name,
                    "district": district,
                    "state": state,
                    "industries": industries,
                    "vin": vin,
                    "year": year,
                    "make": make,
                    "model": model,
                    "insurance_exp": str(insurance_exp),
                    "registration_exp": str(registration_exp),
                    "status": "Active",
                    "comment": comment,
                    "template_used": template_file,
                    "signature_pdf_path": pdf_output_path,
                    "vehicle_photos_paths": vehicle_paths,
                    "insurance_docs_paths": insurance_paths,
                    "registration_docs_paths": registration_paths,
                    "submission_date": datetime.now().isoformat()
                }
                records.append(record)
                save_enrollments(records)
                
                # Send email notification
                ok = send_email_notification(record)
                
                if ok:
                    st.success("✅ Enrollment submitted successfully and email notification sent!")
                else:
                    st.warning("✅ Enrollment saved, but email notification failed. Administrator has been notified.")
                
                # Clear session state
                st.session_state.template_downloaded = False
                
                show_money_rain()
                
            except Exception as e:
                st.error(f"❌ Error processing enrollment: {str(e)}")
                st.exception(e)

# ------------------------
# FILE GALLERY MODAL
# ------------------------
def render_file_gallery_modal(original_row, selected_row, tech_id):
    """Render a modal-style file gallery with grid layout matching the screenshot"""
    
    # Modal styling CSS
    st.markdown("""
    <style>
    .file-gallery-modal {
        background: var(--background-color);
        border-radius: 8px;
        padding: 24px;
        margin-top: 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    .file-gallery-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 24px;
        padding-bottom: 16px;
        border-bottom: 1px solid #e0e0e0;
    }
    .file-gallery-title {
        font-size: 20px;
        font-weight: 600;
        color: #1a1a1a;
    }
    .file-section {
        margin-bottom: 32px;
    }
    .file-section-title {
        font-size: 14px;
        font-weight: 600;
        color: #666;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 16px;
    }
    .file-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 16px;
        margin-bottom: 16px;
    }
    .file-card {
        background: #fafafa;
        border: 1px solid #e8e8e8;
        border-radius: 6px;
        padding: 12px;
        transition: all 0.2s ease;
        cursor: pointer;
        position: relative;
    }
    .file-card:hover {
        background: #f5f5f5;
        border-color: #d0d0d0;
        box-shadow: 0 2px 6px rgba(0,0,0,0.08);
        transform: translateY(-1px);
    }
    .file-thumbnail {
        width: 100%;
        height: 120px;
        object-fit: cover;
        border-radius: 4px;
        margin-bottom: 8px;
        background: #e0e0e0;
    }
    .file-pdf-icon {
        width: 100%;
        height: 120px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 4px;
        margin-bottom: 8px;
        font-size: 48px;
        color: white;
    }
    .file-info {
        display: flex;
        flex-direction: column;
        gap: 4px;
    }
    .file-name {
        font-size: 13px;
        font-weight: 500;
        color: #1a1a1a;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .file-meta {
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .file-size {
        font-size: 12px;
        color: #666;
    }
    .file-tag {
        background: #e3f2fd;
        color: #1976d2;
        font-size: 11px;
        font-weight: 500;
        padding: 2px 8px;
        border-radius: 12px;
    }
    .action-buttons {
        display: flex;
        gap: 12px;
        margin-top: 24px;
        padding-top: 24px;
        border-top: 1px solid #e0e0e0;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Modal container with close button
    col_header1, col_header2 = st.columns([4, 1])
    with col_header1:
        st.markdown(f"""
        <div class="file-gallery-modal">
            <div class="file-gallery-header">
                <div class="file-gallery-title">Files for {selected_row.get('Name', 'Unknown')}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    with col_header2:
        if st.button("✖ Close", key="close_modal_top", width='stretch'):
            if 'show_file_modal' in st.session_state:
                del st.session_state.show_file_modal
            st.rerun()
    
    # Collect all files with metadata
    def get_file_size(path):
        try:
            size_bytes = os.path.getsize(path)
            if size_bytes < 1024:
                return f"{size_bytes} B"
            elif size_bytes < 1024 * 1024:
                return f"{size_bytes / 1024:.1f} KB"
            else:
                return f"{size_bytes / (1024 * 1024):.1f} MB"
        except:
            return "Unknown"
    
    def render_file_grid(files, category, icon="📎"):
        if not files:
            st.info(f"No {category.lower()} found")
            return
        
        st.markdown(f'<div class="file-section-title">{icon} {category}</div>', unsafe_allow_html=True)
        
        # Create grid layout using columns
        cols_per_row = 3
        for i in range(0, len(files), cols_per_row):
            cols = st.columns(cols_per_row)
            for j, file_path in enumerate(files[i:i + cols_per_row]):
                if os.path.exists(file_path):
                    with cols[j]:
                        file_name = os.path.basename(file_path)
                        file_size = get_file_size(file_path)
                        file_ext = os.path.splitext(file_path)[1].lower()
                        
                        # Card container
                        with st.container():
                            st.markdown(f"""
                            <div class="file-card">
                            """, unsafe_allow_html=True)
                            
                            # Thumbnail or icon (optimized for small display)
                            if file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
                                try:
                                    # Load and create thumbnail to reduce memory usage
                                    img = Image.open(file_path)
                                    # Create thumbnail (max 300px wide to save memory)
                                    img.thumbnail((300, 300), Image.Resampling.LANCZOS)
                                    st.image(img, width='stretch')
                                except Exception:
                                    st.markdown('<div class="file-thumbnail"></div>', unsafe_allow_html=True)
                            elif file_ext == '.pdf':
                                st.markdown('<div class="file-pdf-icon">📄</div>', unsafe_allow_html=True)
                            else:
                                st.markdown('<div class="file-pdf-icon">📎</div>', unsafe_allow_html=True)
                            
                            # File info
                            st.markdown(f"""
                            <div class="file-info">
                                <div class="file-name" title="{file_name}">{file_name}</div>
                                <div class="file-meta">
                                    <span class="file-size">{file_size}</span>
                                    <span class="file-tag">BYOV</span>
                                </div>
                            </div>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            # Download button (full width, compact)
                            with open(file_path, "rb") as f:
                                mime_type = "application/pdf" if file_ext == ".pdf" else "image/jpeg"
                                st.download_button(
                                    label="⬇ Download",
                                    data=f.read(),
                                    file_name=file_name,
                                    mime=mime_type,
                                    key=f"dl_{category}_{tech_id}_{i}_{j}",
                                    width='stretch'
                                )
    
    # Signed PDF section
    pdf_path = original_row.get('signature_pdf_path')
    if pdf_path and os.path.exists(pdf_path):
        render_file_grid([pdf_path], "Signed Agreement", "📄")
        st.markdown("---")
    
    # Vehicle photos
    vehicle_paths = original_row.get('vehicle_photos_paths', [])
    if isinstance(vehicle_paths, list) and vehicle_paths:
        valid_paths = [p for p in vehicle_paths if os.path.exists(p)]
        if valid_paths:
            render_file_grid(valid_paths, "Vehicle Photos", "🚗")
            st.markdown("---")
    
    # Insurance documents
    insurance_paths = original_row.get('insurance_docs_paths', [])
    if isinstance(insurance_paths, list) and insurance_paths:
        valid_paths = [p for p in insurance_paths if os.path.exists(p)]
        if valid_paths:
            render_file_grid(valid_paths, "Insurance Documents", "🛡️")
            st.markdown("---")
    
    # Registration documents
    registration_paths = original_row.get('registration_docs_paths', [])
    if isinstance(registration_paths, list) and registration_paths:
        valid_paths = [p for p in registration_paths if os.path.exists(p)]
        if valid_paths:
            render_file_grid(valid_paths, "Registration Documents", "📋")
    
    # Bottom close button
    st.markdown("---")
    if st.button("✖ Close File Viewer", key="close_modal_bottom", width='stretch'):
        if 'show_file_modal' in st.session_state:
            del st.session_state.show_file_modal
        st.rerun()

# ------------------------
# ADMIN SETTINGS PAGE (Hidden)
# ------------------------
def page_admin_settings():
    st.title("🔧 Admin Settings")
    st.caption("Signature position calibration and system settings")
    
    st.warning("⚠ This page is for administrators only. Changes here affect PDF signature placement.")
    
    st.subheader("Signature Position Calibration")
    
    st.info("""
    **PDF Coordinate System:**
    - Standard letter size: 8.5" x 11" = 612 x 792 points
    - Origin (0,0) is at bottom-left corner
    - X increases to the right
    - Y increases upward
    """)
    
    # Initialize session state for coordinates
    if 'sig_x' not in st.session_state:
        st.session_state.sig_x = 90
    if 'sig_y' not in st.session_state:
        st.session_state.sig_y = 450
    if 'date_x' not in st.session_state:
        st.session_state.date_x = 310
    if 'date_y' not in st.session_state:
        st.session_state.date_y = 450
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Signature Position:**")
        sig_x = st.slider(
            "Signature X Position (left margin)",
            min_value=0,
            max_value=600,
            value=st.session_state.sig_x,
            step=5,
            help="Distance from left edge in points (72 points = 1 inch)"
        )
        st.session_state.sig_x = sig_x
        st.write(f"X = {sig_x} points ({sig_x/72:.2f} inches from left)")
        
        sig_y = st.slider(
            "Signature Y Position (from bottom)",
            min_value=0,
            max_value=800,
            value=st.session_state.sig_y,
            step=5,
            help="Distance from bottom edge in points (72 points = 1 inch)"
        )
        st.session_state.sig_y = sig_y
        st.write(f"Y = {sig_y} points ({sig_y/72:.2f} inches from bottom)")
    
    with col2:
        st.write("**Date Position:**")
        date_x = st.slider(
            "Date X Position (left margin)",
            min_value=0,
            max_value=600,
            value=st.session_state.date_x,
            step=5,
            help="Distance from left edge in points (72 points = 1 inch)"
        )
        st.session_state.date_x = date_x
        st.write(f"X = {date_x} points ({date_x/72:.2f} inches from left)")
        
        date_y = st.slider(
            "Date Y Position (from bottom)",
            min_value=0,
            max_value=800,
            value=st.session_state.date_y,
            step=5,
            help="Distance from bottom edge in points (72 points = 1 inch)"
        )
        st.session_state.date_y = date_y
        st.write(f"Y = {date_y} points ({date_y/72:.2f} inches from bottom)")
    
    st.markdown("---")
    
    st.subheader("Test Signature Preview")
    st.write("Draw a test signature to preview placement:")
    
    # Test signature canvas
    test_canvas = st_canvas(
        fill_color="rgba(255, 255, 255, 0)",
        stroke_width=2,
        stroke_color="#000000",
        background_color="rgba(255, 255, 255, 0)",
        height=150,
        width=400,
        drawing_mode="freedraw",
        key="test_signature_canvas",
    )
    
    if test_canvas.image_data is not None:
        import numpy as np
        img_array = np.array(test_canvas.image_data)
        if img_array[:, :, 3].max() > 0:
            st.success("Test signature captured")
            
            # Option to generate test PDF
            if st.button("Generate Test PDF with Current Settings"):
                try:
                    test_template = "template_1.pdf"
                    if os.path.exists(test_template):
                        test_sig_img = Image.fromarray(test_canvas.image_data.astype('uint8'), 'RGBA')
                        test_output = "test_signature_preview.pdf"
                        
                        success = generate_signed_pdf(
                            test_template,
                            test_sig_img,
                            test_output,
                            sig_x=sig_x,
                            sig_y=sig_y,
                            date_x=date_x,
                            date_y=date_y
                        )
                        
                        if success:
                            with open(test_output, "rb") as f:
                                st.download_button(
                                    label="📥 Download Test PDF",
                                    data=f.read(),
                                    file_name="test_signature_preview.pdf",
                                    mime="application/pdf"
                                )
                            st.success("Test PDF generated! Download to verify signature placement.")
                        else:
                            st.error("Failed to generate test PDF")
                    else:
                        st.error("Template file not found")
                except Exception as e:
                    st.error(f"Error: {str(e)}")
    
    st.markdown("---")
    st.subheader("Template Files")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Template 1 (Default):**")
        if os.path.exists(DEFAULT_TEMPLATE):
            st.success(f"✓ {DEFAULT_TEMPLATE} found")
        else:
            st.error(f"✗ {DEFAULT_TEMPLATE} not found")
    
    with col2:
        st.write("**Template 2 (CA, WA, IL):**")
        template_2 = "template_2.pdf"
        if os.path.exists(template_2):
            st.success(f"✓ {template_2} found")
        else:
            st.error(f"✗ {template_2} not found")


# ------------------------
# MAIN APP
# ------------------------
def main():
    st.set_page_config(
        page_title="BYOV Program",
        layout="centered",
        initial_sidebar_state="expanded",
    )
    
    # Theme-aware styling with mobile optimization
    st.markdown("""
        <style>
        .stApp {
            background-color: var(--background-color);
        }
        .main {
            background-color: var(--background-color);
            max-width: 1200px;
            padding: 1rem;
        }
        [data-testid="stSidebar"] {
            background-color: var(--secondary-background-color);
        }
        
        /* Mobile responsive adjustments */
        @media (max-width: 768px) {
            .main {
                padding: 0.5rem;
            }
            .stButton>button, .stDownloadButton>button {
                font-size: 14px;
                padding: 0.5rem;
            }
            h1 {
                font-size: 1.5rem !important;
            }
            h2 {
                font-size: 1.25rem !important;
            }
            h3 {
                font-size: 1.1rem !important;
            }
            .stTextInput>div>div>input {
                font-size: 14px;
            }
        }
        /* Sears blue theme for buttons and checkboxes */
        :root, .stApp {
            --primaryColor: #0d6efd !important;
            --primary-color: #0d6efd !important;
            --accent-color: #0d6efd !important;
            --theme-primary: #0d6efd !important;
        }
        .stButton>button, .stDownloadButton>button, button, [data-testid="stSidebar"] button {
            background-color: #0d6efd !important;
            color: #fff !important;
            border: 1px solid #0d6efd !important;
            box-shadow: none !important;
        }
        .stButton>button:hover, .stDownloadButton>button:hover, button:hover, [data-testid="stSidebar"] button:hover {
            background-color: #0b5ed7 !important;
        }
        .stButton>button:focus, button:focus, [data-testid="stSidebar"] button:focus {
            outline: 3px solid rgba(13,110,253,0.18) !important;
            box-shadow: 0 0 0 3px rgba(13,110,253,0.08) !important;
        }
        /* Accent color for native checkboxes and radios (modern browsers) */
        input[type="checkbox"], input[type="radio"] {
            accent-color: #0d6efd !important;
            -webkit-appearance: auto !important;
        }
        /* Force colored checkbox backgrounds where browsers use SVGs */
        input[type="checkbox"]:checked::before, input[type="checkbox"]:checked {
            background-color: #0d6efd !important;
            border-color: #0d6efd !important;
        }
        /* Fallback: style labels near checkboxes to look accented */
        .stCheckbox, .stRadio {
            color: inherit !important;
        }
        </style>
        """, unsafe_allow_html=True)
    
    # Check for required PDF templates
    templates_ok = True
    if not os.path.exists(DEFAULT_TEMPLATE):
        st.error(f"⚠ Required template file '{DEFAULT_TEMPLATE}' not found!")
        templates_ok = False
    if not os.path.exists("template_2.pdf"):
        st.warning(f"⚠ Template file 'template_2.pdf' not found. CA, WA, IL states will use default template.")
    
    if not templates_ok:
        st.stop()

    # Sidebar navigation with Sears branding
    logo_path = "Sears Image.png"
    if os.path.exists(logo_path):
        st.sidebar.image(logo_path, width=200)
    
    st.sidebar.markdown("**BYOV Program Management**")
    st.sidebar.caption("Technician Enrollment")
    st.sidebar.markdown("---")
    
    st.sidebar.title("Select a page")
    
    # Check for admin mode
    admin_mode = st.query_params.get("admin") == "true"
    
    page_options = ["New Enrollment", "Admin Control Center"]
    if admin_mode:
        page_options.append("Admin Settings")
    
    page = st.sidebar.radio(
        "Select a page",
        page_options,
    )
    
    if admin_mode:
        st.sidebar.info("🔧 Admin mode enabled")

    if page == "New Enrollment":
        page_new_enrollment()
    elif page == "Admin Control Center":
        page_admin_control_center()
    elif page == "Admin Settings":
        page_admin_settings()


if __name__ == "__main__":
    main()
