import json
import os
import re
import shutil
from datetime import date, datetime
import io

import streamlit as st
import uuid
import requests

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
    file_paths = []
    for idx, uploaded_file in enumerate(uploaded_files, 1):
        ext = os.path.splitext(uploaded_file.name)[1]
        filename = f"{prefix}_{idx}{ext}"
        path = os.path.join(folder_path, filename)
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
    """Render a falling money (dollar) animation using HTML/CSS/JS.

    This replaces Streamlit's `st.balloons()` with a lightweight client-side
    animation so users see dollar emojis drifting down when a submission
    completes.
    """
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
    </style>

    <div class="money-rain-wrapper" id="money-rain-wrapper">
        {''.join(bills)}
    </div>
    <script>
    // Remove the animation container after a short delay so it doesn't persist
    setTimeout(function() {{
        var el = document.getElementById('money-rain-wrapper');
        if (el) {{
            el.style.transition = 'opacity 600ms ease-out';
            el.style.opacity = '0';
            setTimeout(function() {{ el.remove(); }}, 700);
        }}
    }}, {duration_ms});
    </script>
    """
    st.markdown(html, unsafe_allow_html=True)

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
    
    saved_industries = data.get('industries', [])
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
    
    if st.button("Next ➡", disabled=bool(errors), type="primary", use_container_width=True):
        # Save to session state
        st.session_state.wizard_data.update({
            'full_name': full_name,
            'tech_id': tech_id,
            'district': district,
            'state': state,
            'referred_by': referred_by,
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
        registration_exp_default = data.get('registration_exp', date.today())
        if isinstance(registration_exp_default, str):
            registration_exp_default = datetime.strptime(registration_exp_default, "%Y-%m-%d").date()
        registration_exp = st.date_input(
            "Registration Expiration Date",
            value=registration_exp_default,
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
        insurance_exp_default = data.get('insurance_exp', date.today())
        if isinstance(insurance_exp_default, str):
            insurance_exp_default = datetime.strptime(insurance_exp_default, "%Y-%m-%d").date()
        insurance_exp = st.date_input(
            "Insurance Expiration Date",
            value=insurance_exp_default,
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
    if not insurance_docs:
        errors.append("Insurance document is required")
    
    can_proceed = len(errors) == 0
    
    if errors:
        st.warning("Please complete the following:\n" + "\n".join(f"• {msg}" for msg in errors))
    
    col_nav1, col_nav2 = st.columns([1, 1])
    with col_nav1:
        if st.button("⬅ Back", use_container_width=True):
            st.session_state.wizard_step = 1
            st.rerun()
    
    with col_nav2:
        if st.button("Next ➡", disabled=not can_proceed, type="primary", use_container_width=True):
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
            use_container_width=True
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
        if st.button("⬅ Back", use_container_width=True):
            st.session_state.wizard_step = 2
            st.rerun()
    
    with col_nav2:
        if st.button("Next ➡", disabled=not can_proceed, type="primary", use_container_width=True):
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
        industries = data.get('industries', [])
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
        if st.button("⬅ Go Back", use_container_width=True):
            st.session_state.wizard_step = 3
            st.rerun()
    
    with col_nav2:
        submit_clicked = st.button("✅ Submit Enrollment", type="primary", use_container_width=True)
    
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
                    "industries": data.get('industries', []),
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

                # Build application-level record for notifications and UI
                record = {
                    "id": enrollment_db_id,
                    "tech_id": data['tech_id'],
                    "full_name": data['full_name'],
                    "referred_by": data.get('referred_by', ''),
                    "district": data['district'],
                    "state": data['state'],
                    "industries": data.get('industries', []),
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

                # Send default email notification (keeps backwards compatibility)
                email_sent = send_email_notification(record)

                if email_sent:
                    st.success("✅ Enrollment submitted successfully and email notification sent!")
                else:
                    st.warning("✅ Enrollment saved, but email notification failed. Administrator has been notified.")

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
                
                # Show success message
                st.markdown("---")
                st.success("🎉 Your BYOV enrollment has been submitted successfully!")
                
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
        insurance_exp = st.date_input("Insurance Expiration Date", value=date.today())
    with col4:
        registration_exp = st.date_input("Registration Expiration Date", value=date.today())
    
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
    
    if not insurance_docs:
        can_submit = False
        validation_messages.append("Insurance document(s) required")
    
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
        if st.button("✖ Close", key="close_modal_top", use_container_width=True):
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
                                    st.image(img, use_container_width=True)
                                except:
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
                                    use_container_width=True
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
    if st.button("✖ Close File Viewer", key="close_modal_bottom", use_container_width=True):
        if 'show_file_modal' in st.session_state:
            del st.session_state.show_file_modal
        st.rerun()

# ------------------------
# ADMIN DASHBOARD PAGE
# ------------------------
def page_admin_dashboard():
    st.title("BYOV Admin Dashboard")
    st.caption("Review and export vehicle enrollments.")

    import pandas as pd

    records = load_enrollments()
    if not records:
        st.info("No enrollments found yet.")
        return

    df = pd.DataFrame(records)

    # Format dates
    for col in ["insurance_exp", "registration_exp", "submission_date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    if "submission_date" in df.columns:
        df["Date Enrolled"] = df["submission_date"].dt.strftime("%m/%d/%Y").fillna("")
    else:
        df["Date Enrolled"] = ""

    # Combine Make & Model
    df["Make & Model"] = df["make"].astype(str) + " " + df["model"].astype(str)
    # Ensure state is always a string and never 'None'
    if "state" in df.columns:
        df["State"] = df["state"].fillna("").replace("None", "")
    else:
        df["State"] = ""
    # Format insurance/registration expiration
    if "insurance_exp" in df.columns:
        df["Insurance Exp. Date"] = df["insurance_exp"].dt.strftime("%m/%d/%Y")
    else:
        df["Insurance Exp. Date"] = ""
    if "registration_exp" in df.columns:
        df["Registration Exp. Date"] = df["registration_exp"].dt.strftime("%m/%d/%Y")
    else:
        df["Registration Exp. Date"] = ""

    # Select columns to display
    display_cols = [
        "Date Enrolled", "Insurance Exp. Date", "Registration Exp. Date",
        "full_name", "tech_id", "district", "State", "vin", "year", "Make & Model"
    ]
    display_labels = {
        "Date Enrolled": "Date Enrolled",
        "Insurance Exp. Date": "Insurance Exp. Date",
        "Registration Exp. Date": "Registration Exp. Date",
        "full_name": "Name",
        "tech_id": "Tech ID",
        "district": "District",
        "State": "State",
        "vin": "VIN",
        "year": "Year",
        "Make & Model": "Make & Model"
    }
    df_display = df[display_cols].rename(columns=display_labels)
    # Add visual columns to mimic the UI from the screenshot
    df_display["Photos"] = "View Photos"
    df_display["Send Reminder"] = "—"
    df_display["Actions"] = "Edit | Remove"

    # Custom paginated table (replaces AgGrid)
    st.subheader("Enrollments Table")

    # Export current enrollments as CSV (download button)
    try:
        csv_bytes = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="⬇️ Export CSV",
            data=csv_bytes,
            file_name="enrollments.csv",
            mime="text/csv",
            help="Download current enrollments as a CSV file"
        )
    except Exception:
        st.warning("Unable to prepare CSV export at this time.")

    # Session state for pagination & UI
    st.session_state.setdefault('admin_page', 0)
    st.session_state.setdefault('admin_page_size', 10)
    st.session_state.setdefault('admin_view_id', None)
    st.session_state.setdefault('admin_edit_id', None)
    st.session_state.setdefault('admin_confirm_delete', None)

    # Simple search/filter
    q = st.text_input("Search (Name, Tech ID, VIN)")
    filtered = []
    for r in records:
        if not q:
            filtered.append(r)
            continue
        hay = ' '.join([str(r.get(k, '')).lower() for k in ('full_name', 'tech_id', 'vin')])
        if q.lower() in hay:
            filtered.append(r)

    total = len(filtered)
    page_size = st.session_state.admin_page_size
    page = st.session_state.admin_page
    max_page = max(0, (total - 1) // page_size)

    # Page controls
    p1, p2, p3 = st.columns([1,1,8])
    with p1:
        if st.button("◀ Prev") and page > 0:
            st.session_state.admin_page -= 1
            st.rerun()
    with p2:
        if st.button("Next ▶") and page < max_page:
            st.session_state.admin_page += 1
            st.rerun()
    with p3:
        st.write(f"Showing page {page+1} of {max_page+1} — {total} records")

    start = page * page_size
    end = start + page_size
    page_rows = filtered[start:end]

    # Table header
    hdr_cols = st.columns([1.4, 2.4, 2, 1.2, 1.2, 1.6, 1, 2])
    headers = ["Date", "Name", "Tech ID", "District", "State", "VIN", "Year", "Actions"]
    for col, h in zip(hdr_cols, headers):
        col.markdown(f"**{h}**")

    # Rows
    for rec in page_rows:
        c1, c2, c3, c4, c5, c6, c7, c8 = st.columns([1.4, 2.4, 2, 1.2, 1.2, 1.6, 1, 2])
        submission = rec.get('submission_date') or rec.get('Date Enrolled') or ''
        c1.write(submission)
        c2.write(rec.get('full_name', ''))
        c3.write(rec.get('tech_id', ''))
        c4.write(rec.get('district', ''))
        c5.write(rec.get('state', rec.get('State', '')))
        c6.write(rec.get('vin', ''))
        c7.write(rec.get('year', ''))

        rid = rec.get('id') or rec.get('tech_id')
        with c8:
            if st.button("View Files", key=f"view_{rid}"):
                st.session_state.admin_view_id = rid
            if st.button("Edit", key=f"edit_{rid}"):
                st.session_state.admin_edit_id = rid
            if st.button("Delete", key=f"del_{rid}"):
                st.session_state.admin_confirm_delete = rid

    # Handle View action (open modal immediately)
    if st.session_state.admin_view_id:
        rid = st.session_state.admin_view_id
        target = None
        for r in records:
            if str(r.get('id')) == str(rid) or str(r.get('tech_id')) == str(rid):
                target = r
                break
        if target:
            render_file_gallery_modal(target, target, target.get('tech_id') or target.get('id'))
        st.session_state.admin_view_id = None

    # Handle Edit action (inline form)
    if st.session_state.admin_edit_id:
        eid = st.session_state.admin_edit_id
        target = None
        for r in records:
            if str(r.get('id')) == str(eid) or str(r.get('tech_id')) == str(eid):
                target = r
                break
        if target:
            st.markdown("---")
            st.subheader(f"Edit Enrollment — {target.get('full_name','')}")
            with st.form(key=f"edit_form_{eid}"):
                name = st.text_input("Full Name", value=target.get('full_name',''))
                tech = st.text_input("Tech ID", value=target.get('tech_id',''))
                district = st.text_input("District", value=target.get('district',''))
                state = st.text_input("State", value=target.get('state', target.get('State','')))
                vin = st.text_input("VIN", value=target.get('vin',''))
                year = st.text_input("Year", value=target.get('year',''))
                submitted = st.form_submit_button("Save Changes")
                if submitted:
                    all_records = load_enrollments()
                    for rr in all_records:
                        if str(rr.get('id')) == str(eid) or str(rr.get('tech_id')) == str(eid):
                            rr['full_name'] = name
                            rr['tech_id'] = tech
                            rr['district'] = district
                            rr['state'] = state
                            rr['vin'] = vin
                            rr['year'] = year
                            break
                    save_enrollments(all_records)
                    st.success("Saved changes")
                    st.session_state.admin_edit_id = None
                    st.rerun()
        else:
            st.session_state.admin_edit_id = None

    # Handle Delete confirmation
    if st.session_state.admin_confirm_delete:
        did = st.session_state.admin_confirm_delete
        st.warning("Are you sure you want to permanently delete this record?")
        d1, d2 = st.columns([1,1])
        with d1:
            if st.button("Yes, delete", key=f"confirm_yes_{did}"):
                success, message = delete_enrollment(str(did))
                if success:
                    st.success(message)
                    st.session_state.admin_confirm_delete = None
                    st.rerun()
                else:
                    st.error(message)
        with d2:
            if st.button("Cancel", key=f"confirm_no_{did}"):
                st.session_state.admin_confirm_delete = None


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
        layout="wide",
        initial_sidebar_state="expanded",
    )
    
    # Theme-aware styling
    st.markdown("""
        <style>
        .stApp {
            background-color: var(--background-color);
        }
        .main {
            background-color: var(--background-color);
        }
        [data-testid="stSidebar"] {
            background-color: var(--secondary-background-color);
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
    
    page_options = ["New Enrollment", "Admin Dashboard"]
    if admin_mode:
        page_options.append("Admin Settings")
    
    page = st.sidebar.radio(
        "Select a page",
        page_options,
    )
    
    if admin_mode:
        st.sidebar.info("🔧 Admin mode enabled")

    # Simple admin authentication stored in session_state
    st.session_state.setdefault('admin_authenticated', False)
    # If user selected an admin page, require password before rendering
    if page in ("Admin Dashboard", "Admin Settings"):
        if not st.session_state.get('admin_authenticated'):
            pwd = st.sidebar.text_input("Admin password", type="password")
            if st.sidebar.button("Unlock Admin"):
                if pwd == "admin123":
                    st.session_state.admin_authenticated = True
                    st.sidebar.success("Admin unlocked")
                    # refresh UI to show admin page
                    st.rerun()
                else:
                    st.sidebar.error("Incorrect password")
            # Block access until authenticated
            st.warning("This page requires administrator authentication.")
            return

    if page == "New Enrollment":
        page_new_enrollment()
    elif page == "Admin Dashboard":
        page_admin_dashboard()
    elif page == "Admin Settings":
        page_admin_settings()


if __name__ == "__main__":
    main()
