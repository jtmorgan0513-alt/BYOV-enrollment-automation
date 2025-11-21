
import json
import os
from datetime import date, datetime
import io
import re

import pandas as pd
import streamlit as st
import uuid 

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
from email.utils import formatdate
import requests

from streamlit_drawable_canvas import st_canvas
from PIL import Image
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter


DATA_FILE = "enrollments.json"

# State to template mapping
STATE_TEMPLATE_MAP = {
    "CA": "template_2.pdf",
    "WA": "template_2.pdf", 
    "IL": "template_2.pdf"
}
DEFAULT_TEMPLATE = "template_1.pdf"

# US States list
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

# Industry options
INDUSTRIES = ["Cook", "Dish", "Laundry", "Micro", "Ref", "HVAC", "L&G"]


# ------------------------
# DATA HELPERS
# ------------------------
def load_enrollments():
    """Load enrollments from JSON file."""
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []


def save_enrollments(records):
    """Save enrollments to JSON file."""
    with open(DATA_FILE, "w") as f:
        json.dump(records, f, indent=2, default=str)

def delete_enrollment(record_id: str):
    """Remove a record from enrollments.json by its id."""
    data = load_enrollments()
    new_data = [r for r in data if r.get("id") != record_id]
    save_enrollments(new_data)
    # return True if something was actually deleted
    return len(new_data) != len(data)


def sanitize_filename(name: str) -> str:
    """Sanitize a string to be safe for use in filenames."""
    # Remove or replace special characters
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    # Remove leading/trailing spaces and dots
    name = name.strip('. ')
    return name if name else "unnamed"


def get_template_for_state(state: str) -> str:
    """Get the appropriate PDF template for a given state."""
    # Extract state abbreviation if full name provided
    state_abbrev = state[:2].upper() if len(state) > 2 else state.upper()
    return STATE_TEMPLATE_MAP.get(state_abbrev, DEFAULT_TEMPLATE)


def create_upload_folder(tech_id: str, record_id: str) -> str:
    """Create and return the upload folder path for a technician."""
    safe_tech_id = sanitize_filename(tech_id)
    folder_name = f"{safe_tech_id}_{record_id}"
    base_path = os.path.join("uploads", folder_name)
    
    # Create subfolders
    os.makedirs(os.path.join(base_path, "vehicle"), exist_ok=True)
    os.makedirs(os.path.join(base_path, "insurance"), exist_ok=True)
    os.makedirs(os.path.join(base_path, "registration"), exist_ok=True)
    os.makedirs("pdfs", exist_ok=True)
    
    return base_path


def save_uploaded_files(uploaded_files, folder_path: str, prefix: str) -> list:
    """Save uploaded files and return list of paths."""
    file_paths = []
    for idx, uploaded_file in enumerate(uploaded_files, 1):
        # Get file extension
        file_ext = os.path.splitext(uploaded_file.name)[1]
        # Create filename
        filename = f"{prefix}_{idx}{file_ext}"
        file_path = os.path.join(folder_path, filename)
        
        # Save file
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        file_paths.append(file_path)
    
    return file_paths


def generate_signed_pdf(template_path: str, signature_image, output_path: str, 
                        sig_x: int = 90, sig_y: int = 450, date_x: int = 310, date_y: int = 450) -> bool:
    """Generate a PDF with signature and date overlay on page 6."""
    try:
        # Read the template PDF
        reader = PdfReader(template_path)
        writer = PdfWriter()
        
        # Create signature overlay
        packet = io.BytesIO()
        can = canvas.Canvas(packet, pagesize=letter)
        
        # Save signature image temporarily and draw it
        if signature_image is not None:
            # Create a temporary file for the signature image
            temp_sig_path = "temp_signature.png"
            signature_image.save(temp_sig_path, format='PNG')
            
            # Draw signature on canvas (page 6 is index 5)
            # Associate Signature box position (red box)
            can.drawImage(temp_sig_path, sig_x, sig_y, width=120, height=40, 
                         preserveAspectRatio=True, mask='auto')
            
            # Clean up temp file after drawing
            import os as os_module
            if os_module.path.exists(temp_sig_path):
                try:
                    os_module.remove(temp_sig_path)
                except:
                    pass  # Will be cleaned up later if deletion fails
        
        # Add current date in the Date box (green box)
        can.setFont("Helvetica", 10)
        current_date = datetime.now().strftime("%m/%d/%Y")
        can.drawString(date_x, date_y, current_date)
        
        can.save()
        packet.seek(0)
        
        # Read the overlay
        overlay_pdf = PdfReader(packet)
        
        # Merge pages
        for page_num in range(len(reader.pages)):
            page = reader.pages[page_num]
            
            # Add signature overlay to page 6 (index 5)
            if page_num == 5 and len(overlay_pdf.pages) > 0:
                page.merge_page(overlay_pdf.pages[0])
            
            writer.add_page(page)
        
        # Write output
        with open(output_path, "wb") as output_file:
            writer.write(output_file)
        
        return True
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        st.error(f"PDF generation error: {str(e)}")
        st.error(f"Details: {error_details}")
        return False

def send_email_notification(record):
    email_config = st.secrets["email"]

    sender = email_config["sender"]
    app_password = email_config["app_password"]
    recipient = email_config["recipient"]

    subject = f"New BYOV Enrollment: {record['full_name']} (Tech {record['tech_id']})"
    
    # Build email body with all collected information
    industries_str = ", ".join(record.get('industries', [])) if record.get('industries') else "None"
    
    body = f"""
A new BYOV enrollment has been submitted.

Technician: {record['full_name']}
Tech ID: {record['tech_id']}
District: {record['district']}
State: {record.get('state', 'N/A')}
Industries: {industries_str}

Vehicle:
Year: {record['year']}
Make: {record['make']}
Model: {record['model']}
VIN: {record['vin']}

Insurance Exp: {record['insurance_exp']}
Registration Exp: {record['registration_exp']}

Template Used: {record.get('template_used', 'N/A')}
Vehicle Photos: {len(record.get('vehicle_photos_paths', []))}
Insurance Documents: {len(record.get('insurance_docs_paths', []))}
Registration Documents: {len(record.get('registration_docs_paths', []))}

Comments: {record['comment']}

This is an automated notification from the BYOV app.
"""

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Date"] = formatdate(localtime=True)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    # Attach signed PDF
    try:
        if record.get('signature_pdf_path') and os.path.exists(record['signature_pdf_path']):
            with open(record['signature_pdf_path'], "rb") as f:
                pdf_name = f"BYOV_Enrollment_{record['tech_id']}_{record['full_name']}.pdf"
                pdf_attach = MIMEApplication(f.read(), _subtype="pdf")
                pdf_attach.add_header('Content-Disposition', 'attachment', filename=pdf_name)
                msg.attach(pdf_attach)
    except Exception as e:
        st.warning(f"Could not attach signed PDF: {str(e)}")

    # Attach vehicle photos
    try:
        for idx, photo_path in enumerate(record.get('vehicle_photos_paths', []), 1):
            if os.path.exists(photo_path):
                with open(photo_path, "rb") as f:
                    file_ext = os.path.splitext(photo_path)[1]
                    if file_ext.lower() in ['.jpg', '.jpeg', '.png']:
                        img_attach = MIMEImage(f.read())
                        img_attach.add_header('Content-Disposition', 'attachment', 
                                            filename=f"{record['tech_id']}_vehicle_{idx}{file_ext}")
                    else:
                        img_attach = MIMEApplication(f.read())
                        img_attach.add_header('Content-Disposition', 'attachment',
                                            filename=f"{record['tech_id']}_vehicle_{idx}{file_ext}")
                    msg.attach(img_attach)
    except Exception as e:
        st.warning(f"Could not attach vehicle photos: {str(e)}")

    # Attach insurance documents
    try:
        for idx, doc_path in enumerate(record.get('insurance_docs_paths', []), 1):
            if os.path.exists(doc_path):
                with open(doc_path, "rb") as f:
                    file_ext = os.path.splitext(doc_path)[1]
                    doc_attach = MIMEApplication(f.read())
                    doc_attach.add_header('Content-Disposition', 'attachment',
                                        filename=f"{record['tech_id']}_insurance_{idx}{file_ext}")
                    msg.attach(doc_attach)
    except Exception as e:
        st.warning(f"Could not attach insurance documents: {str(e)}")

    # Attach registration documents
    try:
        for idx, doc_path in enumerate(record.get('registration_docs_paths', []), 1):
            if os.path.exists(doc_path):
                with open(doc_path, "rb") as f:
                    file_ext = os.path.splitext(doc_path)[1]
                    doc_attach = MIMEApplication(f.read())
                    doc_attach.add_header('Content-Disposition', 'attachment',
                                        filename=f"{record['tech_id']}_registration_{idx}{file_ext}")
                    msg.attach(doc_attach)
    except Exception as e:
        st.warning(f"Could not attach registration documents: {str(e)}")

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, app_password)
            server.sendmail(sender, recipient, msg.as_string())
        return True
    except Exception as e:
        st.error(f"Email sending failed: {str(e)}")
        return False

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
# NEW ENROLLMENT PAGE
# ------------------------
def page_new_enrollment():
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
                
                st.balloons()
                
            except Exception as e:
                st.error(f"❌ Error processing enrollment: {str(e)}")
                st.exception(e)

# ------------------------
# ADMIN DASHBOARD PAGE
# ------------------------
def page_admin_dashboard():
    st.title("BYOV Admin Dashboard")
    st.caption("Review and export vehicle enrollments.")

    records = load_enrollments()
    if not records:
        st.info("No enrollments found yet.")
        return

    df = pd.DataFrame(records)

    # Convert date columns
    for col in ["insurance_exp", "registration_exp"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.date

    # Format industries column for display
    if "industries" in df.columns:
        df["industries_display"] = df["industries"].apply(
            lambda x: ", ".join(x) if isinstance(x, list) else str(x) if x else "None"
        )

    # Summary metrics
    total = len(df)
    active = (df["status"] == "Active").sum() if "status" in df.columns else total

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Enrollments", total)
    with col2:
        st.metric("Active", active)
    with col3:
        if "state" in df.columns:
            unique_states = df["state"].nunique()
            st.metric("States", unique_states)

    st.markdown("---")

    # Search box
    query = st.text_input(
        "Search by Technician, Tech ID, District, State, VIN, Make, or Model",
        "",
    )

    filtered = df.copy()
    if query:
        q = query.lower()
        searchable_cols = ["full_name", "tech_id", "district", "state", "vin", "make", "model"]
        mask = False
        for col in searchable_cols:
            if col in filtered.columns:
                col_values = filtered[col].astype(str).str.lower()
                if isinstance(mask, bool):
                    mask = col_values.str.contains(q, na=False)
                else:
                    mask = mask | col_values.str.contains(q, na=False)
        filtered = filtered[mask]

    st.subheader("Enrollments Table")
    
    # Select columns to display
    display_cols = ["full_name", "tech_id", "district", "state", "vin", "make", "model", "status"]
    if "industries_display" in filtered.columns:
        display_cols.insert(4, "industries_display")
    if "template_used" in filtered.columns:
        display_cols.append("template_used")
    
    # Filter to only existing columns
    display_cols = [col for col in display_cols if col in filtered.columns]
    
    st.dataframe(filtered[display_cols], use_container_width=True)

    # File viewing section
    st.markdown("---")
    st.subheader("View Enrollment Files")
    
    if not filtered.empty:
        # Create a selector for which enrollment to view
        enrollment_options = filtered.apply(
            lambda row: f"{row.get('full_name', 'Unknown')} ({row.get('tech_id', '?')}) - {row.get('vin', '?')[:8]}...",
            axis=1
        ).tolist()
        
        selected_enrollment_idx = st.selectbox(
            "Select an enrollment to view files:",
            range(len(filtered)),
            format_func=lambda i: enrollment_options[i]
        )
        
        if selected_enrollment_idx is not None:
            selected_record = filtered.iloc[selected_enrollment_idx]
            
            with st.expander(f"📁 Files for {selected_record.get('full_name', 'Unknown')}", expanded=True):
                # Signed PDF
                st.write("**Signed BYOV Agreement:**")
                pdf_path = selected_record.get('signature_pdf_path')
                if pdf_path and os.path.exists(pdf_path):
                    with open(pdf_path, "rb") as f:
                        st.download_button(
                            label="📄 Download Signed Agreement",
                            data=f.read(),
                            file_name=os.path.basename(pdf_path),
                            mime="application/pdf"
                        )
                else:
                    st.info("No signed agreement PDF found")
                
                st.markdown("---")
                
                # Vehicle photos
                st.write("**Vehicle Photos:**")
                vehicle_paths = selected_record.get('vehicle_photos_paths', [])
                if isinstance(vehicle_paths, list) and vehicle_paths:
                    cols = st.columns(4)
                    for idx, photo_path in enumerate(vehicle_paths):
                        if os.path.exists(photo_path):
                            with cols[idx % 4]:
                                # Display image if it's an image file
                                if photo_path.lower().endswith(('.jpg', '.jpeg', '.png')):
                                    st.image(photo_path, caption=f"Photo {idx+1}", width=150)
                                
                                # Download button
                                with open(photo_path, "rb") as f:
                                    st.download_button(
                                        label=f"⬇ Photo {idx+1}",
                                        data=f.read(),
                                        file_name=os.path.basename(photo_path),
                                        key=f"vehicle_{selected_enrollment_idx}_{idx}"
                                    )
                else:
                    st.info("No vehicle photos found")
                
                st.markdown("---")
                
                # Insurance documents
                st.write("**Insurance Documents:**")
                insurance_paths = selected_record.get('insurance_docs_paths', [])
                if isinstance(insurance_paths, list) and insurance_paths:
                    for idx, doc_path in enumerate(insurance_paths):
                        if os.path.exists(doc_path):
                            with open(doc_path, "rb") as f:
                                file_ext = os.path.splitext(doc_path)[1]
                                mime_type = "application/pdf" if file_ext.lower() == ".pdf" else "image/jpeg"
                                st.download_button(
                                    label=f"📎 Insurance Doc {idx+1} ({os.path.basename(doc_path)})",
                                    data=f.read(),
                                    file_name=os.path.basename(doc_path),
                                    mime=mime_type,
                                    key=f"insurance_{selected_enrollment_idx}_{idx}"
                                )
                else:
                    st.info("No insurance documents found")
                
                st.markdown("---")
                
                # Registration documents
                st.write("**Registration Documents:**")
                registration_paths = selected_record.get('registration_docs_paths', [])
                if isinstance(registration_paths, list) and registration_paths:
                    for idx, doc_path in enumerate(registration_paths):
                        if os.path.exists(doc_path):
                            with open(doc_path, "rb") as f:
                                file_ext = os.path.splitext(doc_path)[1]
                                mime_type = "application/pdf" if file_ext.lower() == ".pdf" else "image/jpeg"
                                st.download_button(
                                    label=f"📎 Registration Doc {idx+1} ({os.path.basename(doc_path)})",
                                    data=f.read(),
                                    file_name=os.path.basename(doc_path),
                                    mime=mime_type,
                                    key=f"registration_{selected_enrollment_idx}_{idx}"
                                )
                else:
                    st.info("No registration documents found")

    # Export buttons
    st.markdown("---")
    st.markdown("### Export")
    col_csv, col_json = st.columns(2)
    with col_csv:
        csv_data = filtered.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download CSV",
            data=csv_data,
            file_name="enrollments.csv",
            mime="text/csv",
        )
    with col_json:
        json_data = filtered.to_json(orient="records", indent=2, date_format="iso")
        st.download_button(
            "Download JSON",
            data=json_data,
            file_name="enrollments.json",
            mime="application/json",
        )
    
    # ------------------------
    # Delete a record
    # ------------------------
    st.markdown("---")
    st.subheader("Delete a Record")

    if filtered.empty:
        st.info("No records available to delete (based on current search).")
    else:
        # Use the filtered result so search box narrows what you can delete
        indices = list(filtered.index)

        def format_record(idx):
            row = filtered.loc[idx]
            full_name = row.get("full_name", "Unknown")
            tech = row.get("tech_id", "?")
            vin_val = row.get("vin", "?")
            return f"{full_name} | Tech {tech} | VIN {vin_val}"

        selected_idx = st.selectbox(
            "Select a record to delete (applies to filtered results above):",
            indices,
            format_func=format_record,
        )

        if st.button("🗑 Delete selected record"):
            if selected_idx is not None:
                row = filtered.loc[selected_idx]
                record_id = str(row.get("id", ""))

                if not record_id or record_id == "":
                    st.error(
                        "This record has no ID and cannot be deleted here "
                        "(it was probably created before IDs were added)."
                    )
                else:
                    if delete_enrollment(record_id):
                        st.success("Record deleted.")
                        st.rerun()
                    else:
                        st.error("Record not found or already deleted.")


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
    
    # Check for required PDF templates
    templates_ok = True
    if not os.path.exists(DEFAULT_TEMPLATE):
        st.error(f"⚠ Required template file '{DEFAULT_TEMPLATE}' not found!")
        templates_ok = False
    if not os.path.exists("template_2.pdf"):
        st.warning(f"⚠ Template file 'template_2.pdf' not found. CA, WA, IL states will use default template.")
    
    if not templates_ok:
        st.stop()

    # Sidebar navigation
    st.sidebar.title("BYOV Program")
    
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

    if page == "New Enrollment":
        page_new_enrollment()
    elif page == "Admin Dashboard":
        page_admin_dashboard()
    elif page == "Admin Settings":
        page_admin_settings()


if __name__ == "__main__":
    main()
