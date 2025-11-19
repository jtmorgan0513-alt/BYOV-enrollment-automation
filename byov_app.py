
import json
import os
from datetime import date

import pandas as pd
import streamlit as st
import uuid 

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate
import requests


DATA_FILE = "enrollments.json"


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

def send_email_notification(record):
    email_config = st.secrets["email"]

    sender = email_config["sender"]
    app_password = email_config["app_password"]
    recipient = email_config["recipient"]

    subject = f"New BYOV Enrollment: {record['full_name']} (Tech {record['tech_id']})"
    body = f"""
A new BYOV enrollment has been submitted.

Technician: {record['full_name']}
Tech ID: {record['tech_id']}
District: {record['district']}

Vehicle:
Year: {record['year']}
Make: {record['make']}
Model: {record['model']}
VIN: {record['vin']}

Insurance Exp: {record['insurance_exp']}
Registration Exp: {record['registration_exp']}

Comments: {record['comment']}

This is an automated notification from the BYOV app.
"""

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Date"] = formatdate(localtime=True)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, app_password)
            server.sendmail(sender, recipient, msg.as_string())
        return True
    except Exception:
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

    st.subheader("Expiration Dates")
    col3, col4 = st.columns(2)
    with col3:
        insurance_exp = st.date_input("Insurance Expiration Date", value=date.today())
    with col4:
        registration_exp = st.date_input("Registration Expiration Date", value=date.today())
    
    comment = st.text_area("Additional Comments (100 characters max)", max_chars=100)
    
    submitted = st.button("Submit Enrollment")

    if submitted:
        if not tech_id or not full_name or not vin:
            st.error("Technician ID, Full Name, and VIN are required.")
            return

        records = load_enrollments()
        record = {
	    "id": str(uuid.uuid4()),
            "tech_id": tech_id,
            "full_name": full_name,
            "district": district,
            "vin": vin,
            "year": year,
            "make": make,
            "model": model,
            "insurance_exp": str(insurance_exp),
            "registration_exp": str(registration_exp),
            "status": "Active",
	    "comment": comment,
        }
        records.append(record)
        save_enrollments(records)

        ok = send_email_notification(record)

        if ok:
            st.success("Enrollment submitted and email notification sent.")
        else:
            st.warning("Enrollment saved, but email notification failed. Check email settings.")


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

    # Summary metrics
    total = len(df)
    active = (df["status"] == "Active").sum() if "status" in df.columns else total

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Total Enrollments", total)
    with col2:
        st.metric("Active", active)

    st.markdown("---")

    # Search box
    query = st.text_input(
        "Search by Technician, Tech ID, District, VIN, Make, or Model",
        "",
    )

    filtered = df.copy()
    if query:
        q = query.lower()
        searchable_cols = ["full_name", "tech_id", "district", "vin", "make", "model"]
        mask = False
        for col in searchable_cols:
            if col in filtered.columns:
                col_values = filtered[col].astype(str).str.lower()
                if isinstance(mask, bool):
                    mask = col_values.str.contains(q)
                else:
                    mask = mask | col_values.str.contains(q)
        filtered = filtered[mask]

    st.subheader("Enrollments Table")
    st.dataframe(filtered, use_container_width=True)

    # Export buttons
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
            row = filtered.loc[selected_idx]
            record_id = row.get("id")

            if not record_id:
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
# MAIN APP
# ------------------------
def main():
    st.set_page_config(
        page_title="BYOV Program",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Sidebar navigation
    st.sidebar.title("BYOV Program")
    page = st.sidebar.radio(
        "Select a page",
        ["New Enrollment", "Admin Dashboard"],
    )

    if page == "New Enrollment":
        page_new_enrollment()
    else:
        page_admin_dashboard()


if __name__ == "__main__":
    main()
