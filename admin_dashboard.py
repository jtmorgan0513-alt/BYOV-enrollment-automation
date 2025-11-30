import os
import streamlit as st
from datetime import datetime
import database
from notifications import send_email_notification
import shutil
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode

try:
    import sqlite3
except Exception:
    sqlite3 = None

# ------------------------------------------------------------
# Helper: fetch all enrollments & sent notifications
# ------------------------------------------------------------
def _get_all_enrollments():
    return database.get_all_enrollments()


def _get_all_sent_notifications():
    # Returns list of dicts: {id, enrollment_id, rule_id, sent_at}
    # SQLite direct query for efficiency; fallback aggregates JSON store.
    if database.USE_SQLITE and sqlite3:
        try:
            conn = sqlite3.connect(database.DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT id,enrollment_id,rule_id,sent_at FROM notifications_sent ORDER BY sent_at DESC")
            rows = cur.fetchall()
            conn.close()
            return [
                {"id": r[0], "enrollment_id": r[1], "rule_id": r[2], "sent_at": r[3]} for r in rows
            ]
        except Exception:
            return []
    else:
        # Fallback: iterate each enrollment and collect
        sent = []
        enrolls = _get_all_enrollments()
        for e in enrolls:
            eid = e.get('id')
            for s in database.get_sent_notifications(eid):
                sent.append(s)
        # Sort newest first
        sent.sort(key=lambda x: x.get('sent_at',''), reverse=True)
        return sent


# ------------------------------------------------------------
# UI Components
# ------------------------------------------------------------
def _overview_tab(enrollments):
    st.subheader("Overview")

    total_enrollments = len(enrollments)
    storage_mode = "SQLite" if database.USE_SQLITE else "JSON Fallback"

    c1, c2 = st.columns(2)
    c1.metric("Total Enrollments", total_enrollments)
    c2.metric("Storage Mode", storage_mode)

    if not database.USE_SQLITE:
        st.warning("Running in JSON fallback storage mode. Some features may be limited.")
    
    st.markdown("---")
    st.info("Use the Enrollments tab to view and manage all enrollments.")


def show_diagnostics_section():
    """Standalone diagnostics and maintenance section"""
    import pandas as pd
    
    st.title("🔧 Diagnostics & Maintenance")
    st.markdown("---")
    
    # All diagnostics content
    with st.container():
        st.caption("**Database Migration:**")
        if st.button("⚙️ Run Database Migration (Add Approval Columns)", key="run_migration", type="primary"):
            try:
                import sqlite3
                conn = sqlite3.connect(database.DB_PATH)
                cursor = conn.cursor()
                
                # Check if columns already exist
                cursor.execute("PRAGMA table_info(enrollments)")
                columns = [row[1] for row in cursor.fetchall()]
                
                if 'approved' in columns:
                    st.info("✓ Migration already complete - approved columns exist")
                else:
                    # Add the columns
                    cursor.execute("ALTER TABLE enrollments ADD COLUMN approved INTEGER DEFAULT 0")
                    cursor.execute("ALTER TABLE enrollments ADD COLUMN approved_at TEXT")
                    cursor.execute("ALTER TABLE enrollments ADD COLUMN approved_by TEXT")
                    conn.commit()
                    st.success("✅ Migration successful! Approval tracking columns added.")
                
                conn.close()
            except Exception as e:
                st.error(f"❌ Migration failed: {e}")
        
        st.markdown("---")
        st.caption("**Create Complete Test Enrollment with Sample Data**")
        st.info("📋 This creates a full test enrollment in the database with all fields populated and sample photos. Use the Approve button in the Enrollments tab to test the complete workflow.")
        
        with st.form("test_enrollment_form"):
            col1, col2 = st.columns(2)
            with col1:
                test_tech_id = st.text_input("Tech ID*", value=f"TEST-{datetime.now().strftime('%Y%m%d%H%M%S')}")
                test_name = st.text_input("Full Name*", value="John Test Technician")
                test_district = st.text_input("District*", value="4766")
                test_state = st.selectbox("State*", ["IL", "CA", "TX", "FL", "NY"], index=0)
                test_referred_by = st.text_input("Referred By", value="Test Manager")
                test_phone = st.text_input("Mobile Phone", value="555-123-4567")
                test_email = st.text_input("Email", value="test@example.com")
            
            with col2:
                test_vin = st.text_input("VIN*", value="1HGBH41JXMN109186")
                test_make = st.text_input("Vehicle Make*", value="Honda")
                test_model = st.text_input("Vehicle Model*", value="Accord")
                test_year = st.text_input("Vehicle Year*", value="2024")
                test_industry = st.multiselect("Industry", ["Cook", "Dish", "Laundry", "Micro", "Ref", "HVAC", "L&G"], default=["Cook", "Ref"])
                test_insurance_exp = st.date_input("Insurance Expiration", value=datetime(2025, 12, 31))
                test_reg_exp = st.date_input("Registration Expiration", value=datetime(2025, 12, 31))
            
            test_sample_photos = st.file_uploader("Upload Sample Photos (vehicle, insurance, registration)", accept_multiple_files=True, type=["jpg","jpeg","png","pdf"], key="test_enrollment_photos")
            
            submit_test = st.form_submit_button("✅ Create Test Enrollment", type="primary")
        
        if submit_test:
            try:
                from byov_app import create_upload_folder, save_uploaded_files
                
                # Create test enrollment record with all fields
                test_record = {
                    'tech_id': test_tech_id,
                    'full_name': test_name,
                    'district': test_district,
                    'state': test_state,
                    'referred_by': test_referred_by,
                    'vin': test_vin,
                    'make': test_make,
                    'model': test_model,
                    'year': test_year,
                    'industry': test_industry,
                    'insurance_exp': test_insurance_exp.isoformat() if test_insurance_exp else None,
                    'registration_exp': test_reg_exp.isoformat() if test_reg_exp else None,
                    'submission_date': datetime.now().isoformat(),
                    'approved': 0
                }
                
                # Insert enrollment into database
                enrollment_id = database.insert_enrollment(test_record)
                
                # Save uploaded photos if provided
                photo_count = 0
                if test_sample_photos:
                    upload_base = create_upload_folder(test_tech_id, str(enrollment_id))
                    
                    # Group photos by category
                    vehicle_photos = []
                    insurance_photos = []
                    registration_photos = []
                    
                    for uploaded_file in test_sample_photos:
                        fname_lower = uploaded_file.name.lower()
                        if 'insurance' in fname_lower or 'ins' in fname_lower:
                            insurance_photos.append(uploaded_file)
                        elif 'registration' in fname_lower or 'reg' in fname_lower:
                            registration_photos.append(uploaded_file)
                        else:
                            vehicle_photos.append(uploaded_file)
                    
                    # Save each category batch
                    if vehicle_photos:
                        subfolder = os.path.join(upload_base, 'vehicle')
                        saved_paths = save_uploaded_files(vehicle_photos, subfolder, prefix='vehicle')
                        for p in saved_paths:
                            database.add_document(enrollment_id, 'vehicle', p)
                            photo_count += 1
                    
                    if insurance_photos:
                        subfolder = os.path.join(upload_base, 'insurance')
                        saved_paths = save_uploaded_files(insurance_photos, subfolder, prefix='insurance')
                        for p in saved_paths:
                            database.add_document(enrollment_id, 'insurance', p)
                            photo_count += 1
                    
                    if registration_photos:
                        subfolder = os.path.join(upload_base, 'registration')
                        saved_paths = save_uploaded_files(registration_photos, subfolder, prefix='registration')
                        for p in saved_paths:
                            database.add_document(enrollment_id, 'registration', p)
                            photo_count += 1
                
                st.success(f"✅ Test enrollment #{enrollment_id} created successfully with {photo_count} photos!")
                st.info(f"🎯 **Tech ID:** `{test_tech_id}` — Go to the **Enrollments** tab and click **✅ Approve** to test the full workflow.")
                
            except Exception as e:
                st.error(f"❌ Error creating test enrollment: {e}")
                import traceback
                st.code(traceback.format_exc())

        st.markdown("---")
        st.caption("**Legacy Test Functions** (kept for backward compatibility)")
        st.caption("Verify Replit dashboard login and API availability:")
        if st.button("🔌 Test Dashboard Login", key="test_dashboard_login", type="secondary"):
            try:
                from byov_app import post_to_dashboard
                # Minimal record with required keys to trigger login only
                test_record = {
                    "tech_id": "TEST-CONNECTION",
                    "full_name": "Connectivity Test",
                    "state": "CA",
                    "district": "00",
                    "make": "Test",
                    "model": "Test",
                    "year": "2025",
                    "vin": "TESTVIN0000000000",
                    "submission_date": datetime.now().isoformat()
                }
                result = post_to_dashboard(test_record, enrollment_id=0)
                if result.get("status") in ("created", "exists"):
                    st.success("✅ Dashboard reachable and authenticated successfully.")
                elif result.get("error"):
                    st.error(f"❌ Login or API error: {result.get('error')}\n{result.get('body','')}")
                elif result.get("skipped"):
                    st.warning(f"⚠️ Skipped: {result.get('skipped')}")
                else:
                    st.info(f"ℹ️ Result: {result}")
            except Exception as e:
                st.error(f"Unexpected error during connectivity test: {e}")

        st.markdown("---")
        st.caption("**Create a Test Technician on the Dashboard (no enrollment submission required)**")
        test_tech_id = st.text_input("Test Tech ID", value=f"TEST-{datetime.now().strftime('%Y%m%d%H%M%S')}", key="diag_test_techid")
        test_full_name = st.text_input("Test Full Name", value="Automated Test Technician", key="diag_test_name")
        if st.button("➕ Create Test Technician", key="create_test_technician", type="secondary"):
            try:
                from byov_app import create_technician_on_dashboard
                test_record = {
                    "tech_id": test_tech_id,
                    "full_name": test_full_name,
                    "state": "CA",
                    "district": "00",
                    "make": "Test",
                    "model": "Test",
                    "year": "2025",
                    "vin": f"{test_tech_id}-VIN",
                    "submission_date": datetime.now().isoformat()
                }
                create_result = create_technician_on_dashboard(test_record)
                if create_result.get('status') == 'created':
                    dashboard_id = create_result.get('dashboard_tech_id')
                    # persist the dashboard id in session state for the diagnostics helper
                    st.session_state['diag_test_dashboard_id'] = dashboard_id
                    st.session_state['diag_test_tech_id'] = test_tech_id
                    st.success(f"✅ Test technician created with dashboard id: {dashboard_id}")
                elif create_result.get('error'):
                    st.error(f"❌ Error creating test technician: {create_result.get('error')}")
                else:
                    st.info(f"ℹ️ Result: {create_result}")
            except Exception as e:
                st.error(f"Unexpected error creating test technician: {e}")

        # Additional diagnostics: attach sample photos to the created test technician
        st.markdown("---")
        st.caption("Optional: Upload sample photos and transmit them to the created test technician on the dashboard")

        diag_dashboard_id = st.session_state.get('diag_test_dashboard_id')
        diag_tech_id = st.session_state.get('diag_test_tech_id')

        if not diag_dashboard_id:
            st.info("Create a test technician above to enable sample photo upload.")
        else:
            st.markdown(f"**Target dashboard technician id:** `{diag_dashboard_id}` (Tech ID: `{diag_tech_id}`)")
            sample_files = st.file_uploader("Select sample photos to attach (vehicle photos preferred)", accept_multiple_files=True, type=["jpg","jpeg","png","pdf"], key="diag_sample_photos")
            delete_after = st.checkbox("Delete temporary enrollment and files after transmit", value=False, key="diag_delete_after")

            if sample_files:
                st.write(f"Selected {len(sample_files)} file(s)")
                if st.button("📎 Attach & Transmit Sample Photos", key="diag_attach_transmit", type="primary"):
                    try:
                        from byov_app import create_upload_folder, save_uploaded_files, upload_photos_for_technician
                        # Create a temporary enrollment in the DB to hold document records
                        temp_record = {
                            'full_name': f"DIAG-{diag_tech_id}",
                            'tech_id': diag_tech_id,
                            'district': '00',
                            'state': 'CA',
                            'submission_date': datetime.now().isoformat()
                        }
                        temp_eid = database.insert_enrollment(temp_record)

                        # Ensure upload folder exists and save files as vehicle docs
                        upload_base = create_upload_folder(diag_tech_id, str(temp_eid))
                        saved_paths = save_uploaded_files(sample_files, upload_base, prefix='vehicle')

                        # Persist documents in DB
                        for p in saved_paths:
                            database.add_document(temp_eid, 'vehicle', p)

                        # Call upload helper to transmit to dashboard using explicit dashboard id
                        result = upload_photos_for_technician(temp_eid, dashboard_tech_id=diag_dashboard_id)
                        if result.get('error'):
                            st.error(f"❌ Transmit error: {result.get('error')}")
                        else:
                            count = result.get('photo_count', 0)
                            st.success(f"✅ Transmitted {count} photos to dashboard technician {diag_dashboard_id}.")
                            if result.get('failed_uploads'):
                                st.warning(f"⚠️ {len(result.get('failed_uploads'))} uploads failed. See details below.")
                                with st.expander("Failed Upload Details"):
                                    for f in result.get('failed_uploads'):
                                        st.write(f)

                        # Optionally delete temp enrollment and files
                        if delete_after:
                            try:
                                # remove files from filesystem
                                for p in saved_paths:
                                    try:
                                        if os.path.exists(p):
                                            os.remove(p)
                                    except Exception:
                                        pass
                                # remove folder
                                try:
                                    if os.path.exists(upload_base):
                                        shutil.rmtree(upload_base, ignore_errors=True)
                                except Exception:
                                    pass
                                database.delete_enrollment(temp_eid)
                                st.info(f"Temporary enrollment {temp_eid} and files deleted.")
                            except Exception:
                                st.warning("Could not fully delete temporary enrollment/files; please clean up manually if needed.")

                    except Exception as e:
                        st.error(f"Unexpected error during attach/transmit: {e}")


def _enrollments_tab(enrollments):
    """Enrollments management tab"""
    import pandas as pd
    
    st.subheader("Enrollments")
    
    
    # -----------------------------
    # No enrollments
    # -----------------------------
    if not enrollments:
        st.info("No enrollments yet.")
        return

    # -----------------------------
    # Session state
    # -----------------------------
    st.session_state.setdefault("ecc_search", "")
    st.session_state.setdefault("ecc_page", 0)
    st.session_state.setdefault("ecc_page_size", 10)
    st.session_state.setdefault("open_photos_for_id", None)
    st.session_state.setdefault("selected_enrollment_ids", set())
    st.session_state.setdefault("delete_confirm", {})

    # -----------------------------
    # Search
    # -----------------------------
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

    # -----------------------------
    # Pagination
    # -----------------------------
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

    # -----------------------------
    # Build DataFrame for Display - 10 Columns
    # -----------------------------
    display_rows = []
    for row in page_rows:
        # Transform industry to comma-separated string (accept either 'industry' or 'industries')
        industries_raw = row.get('industry') if row.get('industry') is not None else row.get('industries', [])
        if isinstance(industries_raw, list):
            industries_str = ", ".join(industries_raw) if industries_raw else "None"
        else:
            industries_str = str(industries_raw) if industries_raw else "None"
        
        # Format vehicle info (Year, Make & Model)
        vehicle_info = f"{row.get('year', '')} {row.get('make', '')} {row.get('model', '')}".strip()
        
        # Format enrollment date from ISO to MM/DD/YYYY
        submission_date = row.get('submission_date', '')
        date_enrolled = 'N/A'
        if submission_date:
            try:
                dt = datetime.fromisoformat(submission_date)
                date_enrolled = dt.strftime("%m/%d/%Y")
            except Exception:
                date_enrolled = submission_date
        
        # Format registration expiration date
        reg_exp = row.get('registration_exp', '')
        if reg_exp:
            try:
                dt = datetime.fromisoformat(reg_exp)
                reg_exp = dt.strftime("%m/%d/%Y")
            except Exception:
                pass
        else:
            reg_exp = 'N/A'
        
        # Format insurance expiration date
        ins_exp = row.get('insurance_exp', '')
        if ins_exp:
            try:
                dt = datetime.fromisoformat(ins_exp)
                ins_exp = dt.strftime("%m/%d/%Y")
            except Exception:
                pass
        else:
            ins_exp = 'N/A'
        
        # Approved status
        approved_status = "Yes" if row.get('approved', 0) == 1 else "No"
        
        display_rows.append({
            'Name': row.get('full_name', 'N/A'),
            'Tech ID': row.get('tech_id', 'N/A'),
            'District': row.get('district', 'N/A'),
            'Referred By': row.get('referred_by') or row.get('referredBy') or 'N/A',
            'VIN': row.get('vin', 'N/A'),
            'Vehicle': vehicle_info,
            'Industry': industries_str,
            'Date Enrolled': date_enrolled,
            'Registration Exp. Date': reg_exp,
            'Insurance Exp. Date': ins_exp,
            'Approved': approved_status
        })
    
    # Display table with dataframe
    if display_rows:
        df = pd.DataFrame(display_rows)
        st.dataframe(df, width='stretch', hide_index=True)
        
        st.markdown("---")
        st.subheader("Actions")
        
        # -----------------------------
        # Action Buttons for Each Row
        # -----------------------------
        for row in page_rows:
            enrollment_id = row.get('id')
            row_name = f"{row.get('full_name', 'N/A')} (Tech ID: {row.get('tech_id', 'N/A')})"
            
            # Custom CSS for this enrollment card
            st.markdown(f"""
            <style>
            div[data-testid="stHorizontalBlock"] button {{
                border-radius: 8px;
                font-weight: 500;
                transition: all 0.3s ease;
            }}
            </style>
            """, unsafe_allow_html=True)
            
            with st.container():
                # Enhanced header with badge styling
                vehicle_info = f"{row.get('year', '')} {row.get('make', '')} {row.get('model', '')}".strip()
                st.markdown(f"""
                <div style="
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    padding: 15px 20px;
                    border-radius: 10px;
                    margin-bottom: 15px;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                ">
                    <h3 style="color: white; margin: 0; font-size: 18px;">
                        Enrollment #{enrollment_id} — {row_name}
                    </h3>
                    <p style="color: rgba(255,255,255,0.9); margin: 5px 0 0 0; font-size: 14px;">
                        🚗 {vehicle_info} | 📍 District {row.get('district', 'N/A')}
                    </p>
                </div>
                """, unsafe_allow_html=True)
                
                cols = st.columns([2.2, 3.2, 2.7, 2.2])
                
                # Select button
                with cols[0]:
                    is_selected = enrollment_id in st.session_state.selected_enrollment_ids
                    btn_label = "✅ Selected" if is_selected else "⭕ Select"
                    btn_type = "primary" if is_selected else "secondary"
                    if st.button(btn_label, key=f"select_{enrollment_id}", type=btn_type, width='stretch'):
                        if is_selected:
                            st.session_state.selected_enrollment_ids.discard(enrollment_id)
                        else:
                            st.session_state.selected_enrollment_ids.add(enrollment_id)
                        st.rerun()
                
                # View Photos button
                with cols[1]:
                    if st.button("🖼️ View Photos", key=f"view_photos_{enrollment_id}", width='stretch', type="secondary"):
                        st.session_state.open_photos_for_id = enrollment_id
                        st.rerun()
                
                # Approve button - Sends to dashboard
                with cols[2]:
                    # Check if already approved
                    is_approved = row.get('approved', 0) == 1
                    
                    if is_approved:
                        # Show approved badge instead of button
                        st.markdown(
                            '<div style="background: #10b981; color: white; padding: 8px 12px; '
                            'border-radius: 10px; text-align: center; font-weight: 600; font-size: 12px;">'
                            '✅ Approved</div>',
                            unsafe_allow_html=True
                        )
                    else:
                        # Show approve button (creates technician record only)
                        if st.button("✅ Approve", key=f"approve_{enrollment_id}", type="primary", width='stretch'):
                            from byov_app import post_to_dashboard_single_request

                            record = dict(row)

                            # Use the single-request external API to create technician + photos
                            single_result = post_to_dashboard_single_request(record, enrollment_id=enrollment_id)

                            # Handle errors
                            if single_result.get('error'):
                                st.error(f"❌ Technician creation error: {single_result.get('error')}")
                            else:
                                status_code = single_result.get('status_code', 0)
                                resp = single_result.get('response')
                                # Consider 201 or 200 as success; 207 as partial success
                                if status_code in (201,) or (200 <= status_code < 300 and status_code != 207):
                                    # Success — database.set_dashboard_sync_info already attempted in helper
                                    try:
                                        database.approve_enrollment(enrollment_id)
                                    except Exception:
                                        pass
                                    st.success(f"✅ Enrollment #{enrollment_id} approved and technician created on dashboard.")
                                    st.rerun()
                                elif status_code == 207:
                                    # Partial success — show details and still mark approved
                                    try:
                                        database.approve_enrollment(enrollment_id)
                                    except Exception:
                                        pass
                                    st.warning(f"⚠️ Enrollment #{enrollment_id} created, but some photos failed to attach.")
                                    if single_result.get('failed_photos'):
                                        with st.expander("Failed Photo Details"):
                                            st.json(single_result.get('failed_photos'))
                                    st.rerun()
                                else:
                                    # Non-successful HTTP response
                                    st.error(f"❌ Dashboard responded with status {status_code}: {resp}")
                
                # Delete button
                with cols[3]:
                    is_confirming = st.session_state.delete_confirm.get(enrollment_id, False)
                    btn_label = "⚠️ Confirm Delete" if is_confirming else "🗑️ Delete"
                    
                    if st.button(btn_label, key=f"delete_{enrollment_id}", type="secondary", width='stretch'):
                        if is_confirming:
                            # Second click - execute delete
                            try:
                                tech_id = row.get('tech_id', 'unknown')
                                
                                # Get documents
                                docs = database.get_documents_for_enrollment(enrollment_id)
                                
                                # Delete files
                                for doc in docs:
                                    file_path = doc.get('file_path')
                                    if file_path and os.path.exists(file_path):
                                        try:
                                            os.remove(file_path)
                                        except Exception:
                                            pass
                                
                                # Delete upload folder
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
                                
                                # Delete PDF
                                if os.path.exists('pdfs'):
                                    pdf_prefix = f"{tech_id}_"
                                    for pdf_file in os.listdir('pdfs'):
                                        if pdf_file.startswith(pdf_prefix) and pdf_file.endswith('.pdf'):
                                            pdf_path = os.path.join('pdfs', pdf_file)
                                            try:
                                                os.remove(pdf_path)
                                            except Exception:
                                                pass
                                
                                # Delete from database
                                database.delete_enrollment(enrollment_id)
                                
                                # Clear confirmation state
                                st.session_state.delete_confirm.pop(enrollment_id, None)
                                st.success(f"✅ Deleted enrollment {enrollment_id}")
                                st.rerun()
                                
                            except Exception as e:
                                st.error(f"Error deleting enrollment {enrollment_id}: {e}")
                        else:
                            # First click - set confirmation
                            st.session_state.delete_confirm[enrollment_id] = True
                            st.rerun()
                
                st.markdown("<br>", unsafe_allow_html=True)
    
    # -----------------------------
    # Photo Modal (Displayed at Bottom)
    # -----------------------------
    if st.session_state.open_photos_for_id:
        enrollment_id = st.session_state.open_photos_for_id

        docs = database.get_documents_for_enrollment(enrollment_id)

        vehicle = [d["file_path"] for d in docs if d["doc_type"] == "vehicle"]
        registration = [d["file_path"] for d in docs if d["doc_type"] == "registration"]
        insurance = [d["file_path"] for d in docs if d["doc_type"] == "insurance"]
        signature_pdf = [d["file_path"] for d in docs if d["doc_type"] == "signature"]

        st.markdown("---")
        st.markdown("### 📸 Photo & Document Viewer")
        
        # Close button at top
        col1, col2 = st.columns([6, 1])
        with col2:
            if st.button("✖ Close", key=f"close_modal_top_{enrollment_id}", type="primary"):
                st.session_state.open_photos_for_id = None
                st.rerun()

        tabs = st.tabs(["📄 Signed PDF", "🚗 Vehicle", "📋 Registration", "🛡️ Insurance"])
        
        # PDF Tab
        with tabs[0]:
            if signature_pdf and os.path.exists(signature_pdf[0]):
                with open(signature_pdf[0], 'rb') as f:
                    pdf_bytes = f.read()
                
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.info(f"📄 {os.path.basename(signature_pdf[0])}")
                with col2:
                        st.download_button(
                        label="⬇️ Download PDF",
                        data=pdf_bytes,
                        file_name=os.path.basename(signature_pdf[0]),
                        mime="application/pdf",
                        key=f"download_pdf_modal_{enrollment_id}",
                        width='stretch'
                    )
                
                # Display PDF using iframe
                import base64
                base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
                pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="800" type="application/pdf"></iframe>'
                st.markdown(pdf_display, unsafe_allow_html=True)
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
                                if os.path.exists(p):
                                    with col:
                                        st.image(p, width='stretch')
                                        st.caption(os.path.basename(p))
                                else:
                                    with col:
                                        st.error(f"Missing: {p}")
                else:
                    st.info(f"No {label.lower()} photos found.")

        # Close button at bottom
        st.markdown("---")
        col1, col2, col3 = st.columns([4, 2, 4])
        with col2:
            if st.button("✖ Close Photo Viewer", key=f"close_modal_bottom_{enrollment_id}", type="primary", width='stretch'):
                st.session_state.open_photos_for_id = None
                st.rerun()

# ------------------------------------------------------------
# Entry Point
# ------------------------------------------------------------
def page_admin_control_center():
    st.title("BYOV Admin Control Center")
    st.caption("Manage enrollments and view analytics")
    
    # Add custom CSS for enhanced button styling
    st.markdown("""
    <style>
    /* Enhanced button styling */
    div[data-testid="stButton"] button {
        font-size: 12px;
        font-weight: 600;
        border-radius: 10px;
        padding: 8px 12px;
        border: none;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        transition: all 0.3s ease;
        white-space: nowrap;
        overflow: visible;
        text-overflow: clip;
    }
    
    div[data-testid="stButton"] button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.15);
    }
    
    div[data-testid="stButton"] button:active {
        transform: translateY(0px);
    }
    
    /* Download button styling */
    div[data-testid="stDownloadButton"] button {
        font-size: 12px;
        font-weight: 600;
        border-radius: 10px;
        padding: 8px 12px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        transition: all 0.3s ease;
        white-space: nowrap;
        overflow: visible;
        text-overflow: clip;
    }
    
    div[data-testid="stDownloadButton"] button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.15);
    }
    
    /* Card container styling */
    div[data-testid="stHorizontalBlock"] {
        gap: 10px;
    }
    
    /* Table styling */
    div[data-testid="stDataFrame"] {
        border-radius: 10px;
        overflow: hidden;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }
    </style>
    """, unsafe_allow_html=True)

    # Load data once for all tabs
    enrollments = _get_all_enrollments()

    tabs = st.tabs(["Overview", "Enrollments"])

    with tabs[0]:
        _overview_tab(enrollments)
    with tabs[1]:
        _enrollments_tab(enrollments)

    st.markdown("---")
    st.caption("Select Approve when all information has been successfully validated for enrollment to push to dashboard.")


if __name__ == '__main__':
    page_admin_control_center()
