"""Streamlit BYOV enrollment app with VIN decoding, email notifications,
photo uploads, and PDF generation with required signatures.
"""

import io
import os
import pathlib
import smtplib
from dataclasses import dataclass
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Iterable, List, Optional

import requests
import streamlit as st
from PIL import Image
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas
from streamlit_drawable_canvas import st_canvas

try:
    from fastapi import FastAPI, File, UploadFile
    from fastapi.responses import JSONResponse
except ImportError:
    # FastAPI is optional for running the Streamlit UI; import lazily.
    FastAPI = None  # type: ignore
    UploadFile = None  # type: ignore
    File = None  # type: ignore
    JSONResponse = None  # type: ignore

UPLOAD_DIR = pathlib.Path("uploads")
PDF_DIR = pathlib.Path("pdfs")
for directory in (UPLOAD_DIR, PDF_DIR):
    directory.mkdir(exist_ok=True)

VIN_DECODER_API = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}?format=json"


def decode_vin(vin: str) -> dict:
    """Decode VIN using NHTSA API."""
    response = requests.get(VIN_DECODER_API.format(vin=vin), timeout=10)
    response.raise_for_status()
    data = response.json()
    results = data.get("Results", [{}])[0]
    return {
        "Make": results.get("Make", ""),
        "Model": results.get("Model", ""),
        "ModelYear": results.get("ModelYear", ""),
    }


@dataclass
class Submission:
    tech_id: str
    first_name: str
    last_name: str
    district: str
    vin: str
    year: str
    make: str
    model: str
    photos: List[pathlib.Path]
    pdf_path: pathlib.Path


def send_email(submission: Submission, recipients: Iterable[str]) -> None:
    """Send an email with submission details and attachments."""
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ.get("SMTP_USERNAME")
    password = os.environ.get("SMTP_PASSWORD")
    sender = os.environ.get("SMTP_FROM", username)

    if not (host and username and password and sender):
        st.warning("Email is not configured. Set SMTP_* environment variables.")
        return

    msg = MIMEMultipart()
    msg["Subject"] = f"BYOV Submission: {submission.tech_id} {submission.vin}"
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)

    body = (
        f"Tech ID: {submission.tech_id}\n"
        f"Name: {submission.first_name} {submission.last_name}\n"
        f"District: {submission.district}\n"
        f"VIN: {submission.vin}\n"
        f"Year: {submission.year}\n"
        f"Make: {submission.make}\n"
        f"Model: {submission.model}\n"
    )
    msg.attach(MIMEText(body, "plain"))

    # Attach PDF
    with open(submission.pdf_path, "rb") as pdf_file:
        pdf_part = MIMEApplication(pdf_file.read(), _subtype="pdf")
        pdf_part.add_header(
            "Content-Disposition", "attachment", filename=submission.pdf_path.name
        )
        msg.attach(pdf_part)

    # Attach photos
    for photo_path in submission.photos:
        with open(photo_path, "rb") as photo_file:
            photo_part = MIMEApplication(photo_file.read())
            photo_part.add_header(
                "Content-Disposition", "attachment", filename=photo_path.name
            )
            msg.attach(photo_part)

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(username, password)
        server.sendmail(sender, recipients, msg.as_string())


def save_photos(files: List[io.BytesIO], names: List[str]) -> List[pathlib.Path]:
    saved = []
    for file_obj, name in zip(files, names):
        destination = UPLOAD_DIR / name
        with open(destination, "wb") as dest:
            dest.write(file_obj.read())
        saved.append(destination)
    return saved


def is_canvas_signed(image_data: Optional[Image.Image]) -> bool:
    if image_data is None:
        return False
    grayscale = image_data.convert("L")
    extrema = grayscale.getextrema()
    # If min == max == 255, the canvas is blank (white)
    return extrema != (255, 255)


def generate_pdf(submission: Submission, signature_image: Image.Image) -> pathlib.Path:
    output_path = PDF_DIR / f"submission_{submission.tech_id}_{submission.vin}.pdf"
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=LETTER)
    width, height = LETTER

    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, height - 72, "BYOV Enrollment")

    c.setFont("Helvetica", 12)
    y = height - 108
    fields = [
        ("Tech ID", submission.tech_id),
        ("Name", f"{submission.first_name} {submission.last_name}"),
        ("District", submission.district),
        ("VIN", submission.vin),
        ("Year", submission.year),
        ("Make", submission.make),
        ("Model", submission.model),
    ]
    for label, value in fields:
        c.drawString(72, y, f"{label}: {value}")
        y -= 18

    c.drawString(72, y - 12, "Signature:")
    sig_buffer = io.BytesIO()
    signature_image.save(sig_buffer, format="PNG")
    sig_buffer.seek(0)
    c.drawImage(sig_buffer, 72, y - 120, width=240, height=80, mask="auto")

    c.showPage()
    c.save()

    buffer.seek(0)
    with open(output_path, "wb") as pdf_file:
        pdf_file.write(buffer.read())

    return output_path


def build_api():
    if FastAPI is None:
        return None

    api = FastAPI()

    @api.post("/photos")
    async def upload_photos(files: List[UploadFile] = File(...)):
        saved_paths = []
        for file in files:
            destination = UPLOAD_DIR / file.filename
            with open(destination, "wb") as dest:
                dest.write(await file.read())
            saved_paths.append(str(destination))
        return JSONResponse({"saved": saved_paths})

    return api


api = build_api()


def run_streamlit_app():
    st.set_page_config(page_title="BYOV Enrollment", layout="centered")
    st.title("BYOV Enrollment Form")

    with st.form("enrollment_form"):
        tech_id = st.text_input("Tech ID", max_chars=50, key="tech_id")
        first_name = st.text_input("First Name", max_chars=50, key="first_name")
        last_name = st.text_input("Last Name", max_chars=50, key="last_name")
        district = st.text_input("District #", max_chars=20, key="district")
        vin = st.text_input("VIN", max_chars=17, key="vin")
        decode_button = st.form_submit_button("Decode VIN")

        year = st.text_input("Year", max_chars=4, key="year")
        make = st.text_input("Make", max_chars=50, key="make")
        model = st.text_input("Model", max_chars=50, key="model")

        photos = st.file_uploader(
            "Upload photos (drag multiple)", accept_multiple_files=True, type=None
        )

        st.subheader("Signature (required)")
        signature_canvas = st_canvas(
            fill_color="rgba(0, 0, 0, 0)",
            stroke_width=2,
            stroke_color="#000000",
            background_color="#FFFFFF",
            height=150,
            width=400,
            drawing_mode="freedraw",
            key="signature_canvas",
        )

        submitted = st.form_submit_button("Submit")

    if decode_button and vin:
        with st.spinner("Decoding VIN..."):
            decoded = decode_vin(vin)
            st.session_state["decoded"] = decoded
            st.success(
                f"Decoded: {decoded.get('ModelYear', '')} {decoded.get('Make', '')} {decoded.get('Model', '')}"
            )
            year_placeholder = decoded.get("ModelYear", "")
            make_placeholder = decoded.get("Make", "")
            model_placeholder = decoded.get("Model", "")
            if year_placeholder:
                st.session_state["year"] = year_placeholder
            if make_placeholder:
                st.session_state["make"] = make_placeholder
            if model_placeholder:
                st.session_state["model"] = model_placeholder

    if submitted:
        if not all([tech_id, first_name, last_name, district, vin, year, make, model]):
            st.error("All fields are required.")
            return

        signature_image = None
        if signature_canvas.image_data is not None:
            signature_image = Image.fromarray(signature_canvas.image_data.astype("uint8"))

        if not is_canvas_signed(signature_image):
            st.error("Signature is required. Please sign before submitting.")
            return

        photo_files = []
        photo_names = []
        for file in photos or []:
            photo_files.append(io.BytesIO(file.getvalue()))
            photo_names.append(file.name)

        saved_photos = save_photos(photo_files, photo_names)

        submission = Submission(
            tech_id=tech_id,
            first_name=first_name,
            last_name=last_name,
            district=district,
            vin=vin,
            year=year,
            make=make,
            model=model,
            photos=saved_photos,
            pdf_path=PDF_DIR / "placeholder.pdf",
        )

        pdf_path = generate_pdf(submission, signature_image)  # type: ignore[arg-type]
        submission.pdf_path = pdf_path

        recipients = [email for email in os.environ.get("SMTP_TO", "").split(",") if email]
        if recipients:
            send_email(submission, recipients)
            st.success("Submission emailed successfully.")
        else:
            st.warning("No SMTP_TO recipients configured; skipping email.")

        st.success(f"Submission complete. PDF saved to {pdf_path}.")


if __name__ == "__main__":
    run_streamlit_app()
