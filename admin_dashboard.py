import os
import streamlit as st
from datetime import datetime
import database
from notifications import send_email_notification

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
def _overview_tab(enrollments, rules, sent):
    st.subheader("Overview")

    total_enrollments = len(enrollments)
    active_rules = sum(1 for r in rules if r.get('enabled'))
    total_notifications = len(sent)
    storage_mode = "SQLite" if database.USE_SQLITE else "JSON Fallback"



    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Enrollments", total_enrollments)
    c2.metric("Active Rules", active_rules)
    c3.metric("Emails Logged", total_notifications)
    c4.metric("Storage Mode", storage_mode)

    if not database.USE_SQLITE:
        st.warning("Running in JSON fallback storage mode. Some features may be limited.")

    # Recent activity (last 5 notifications)
    if sent:
        st.markdown("### Recent Notifications")
        recent = sent[:5]
        rule_lookup = {r.get('id'): r.get('rule_name') for r in rules}
        for n in recent:
            rid = n.get('rule_id')
            rname = rule_lookup.get(rid, f"Rule {rid}")
            st.write(f"• {n.get('sent_at','')} — {rname} (Enrollment #{n.get('enrollment_id')})")
    else:
        st.info("No notifications have been sent yet.")


def _enrollments_tab(enrollments):
    from st_aggrid import AgGrid, GridOptionsBuilder
    import pandas as pd
    from datetime import datetime

    st.subheader("Enrollments")

    if not enrollments:
        st.info("No enrollments yet.")
        return

    # -----------------------------
    # State (search, pagination, etc.)
    # -----------------------------
    st.session_state.setdefault('ecc_search', '')
    st.session_state.setdefault('ecc_page', 0)
    st.session_state.setdefault('ecc_page_size', 10)
    st.session_state.setdefault('ecc_view_id', None)
    st.session_state.setdefault('ecc_edit_id', None)
    st.session_state.setdefault('ecc_delete_id', None)

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
        
        hay = ' '.join([str(r.get(k, '')).lower() for k in ('full_name', 'tech_id', 'vin')])
        if q.lower() in hay:
            filtered.append(r)

    # -----------------------------
    # Pagin1FTLR4FEXAPA20178ation
    # -----------------------------
    total = len(filtered)
    page_size = st.session_state.ecc_page_size
    page = st.session_state.ecc_page
    max_page = max(0, (total - 1) // page_size)

    cnav1, cnav2, cnav3 = st.columns([1, 1, 4])
    with cnav1:
        if st.button("◀ Prev", disabled=page <= 0):
            st.session_state.ecc_page = max(0, page - 1)
            st.rerun()
    with cnav2:
        if st.button("Next ▶", disabled=page >= max_page):
            st.session_state.ecc_page = min(max_page, page + 1)
            st.rerun()
    with cnav3:
        st.write(f"Page {page+1} of {max_page+1} — {total} records")

    start = page * page_size
    end = start + page_size
    page_rows = filtered[start:end]

    # -----------------------------
    # AG-Grid Table
    # -----------------------------
    df = pd.DataFrame(page_rows)

    # Remove unwanted columns
    for col in ["id", "comment", "template_used"]:
        if col in df.columns:
            df.drop(columns=[col], inplace=True)

    # Format submission date
    if "submission_date" in df.columns:
        df["submission_date"] = df["submission_date"].apply(
            lambda d: datetime.fromisoformat(d).strftime("%m/%d/%Y") if d else ""
        )

    # Build grid
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(
        resizable=True,
        filter=True,
        sortable=True,
    )

    # Match pagination in Streamlit with pagination inside AG-Grid
    gb.configure_pagination(
        paginationAutoPageSize=False,
        paginationPageSize=page_size,
    )

    grid = AgGrid(
        df,
        gridOptions=gb.build(),
        theme="alpine",
        fit_columns_on_grid_load=True,
        allow_unsafe_jscode=True,
    )

    # -----------------------------
    # Enrollment selector (unchanged)
    # -----------------------------
    st.markdown("---")
    options = [f"#{e.get('id')} — {e.get('full_name')} ({e.get('tech_id')})" for e in enrollments]
    selected_label = st.selectbox("Select enrollment for rule actions", options) if options else None

    if selected_label:
        try:
            selected_id = int(selected_label.split('—')[0].strip('# ').strip())
            st.session_state.selected_enrollment_id = selected_id
        except Exception:
            st.session_state.selected_enrollment_id = None


def _rules_tab(enrollments, rules):
    # Toggle for submission email notification
    st.markdown("---")
    st.session_state.setdefault('submission_email_enabled', True)
    submission_email_enabled = st.toggle(
        "Enable Submission Email Notification",
        value=st.session_state['submission_email_enabled'],
        key="submission_email_enabled"
    )
    st.session_state['submission_email_enabled'] = submission_email_enabled

    st.subheader("Notification Rules")

    # Create new rule
    with st.form("create_rule"):
        st.write("Create a new rule")
        rule_name = st.text_input("Rule Name")
        trigger = st.selectbox("Trigger", ["On Submission", "On Expiration", "Manual"])
        recipients_raw = st.text_area("Recipients (comma-separated emails)")
        days_before = st.number_input("Days before expiration (if Expiration trigger)", min_value=1, max_value=365, value=7)
        enabled = st.checkbox("Enabled", value=True)
        submitted = st.form_submit_button("Add Rule")
        if submitted:
            if not rule_name:
                st.error("Rule name is required")
            else:
                rule = {
                    'rule_name': rule_name,
                    'trigger': trigger if trigger != 'On Expiration' else 'On Expiration (days before)',
                    'recipients': [r.strip() for r in recipients_raw.split(',') if r.strip()],
                    'days_before': int(days_before) if 'Expiration' in trigger else None,
                    'enabled': enabled
                }
                try:
                    database.add_notification_rule(rule)
                    st.success("Rule added")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to add rule: {e}")

    if not rules:
        st.info("No rules configured yet.")
        return

    st.markdown("### Existing Rules")
    rule_lookup = {r.get('id'): r for r in rules}

    for rule in rules:
        rid = rule.get('id')
        with st.expander(f"{rule.get('rule_name')} — {rule.get('trigger')}", expanded=False):
            cols = st.columns([2,2,2,1,1,1])
            with cols[0]:
                st.write("Recipients:")
                st.caption(', '.join(rule.get('recipients', [])) or 'None')
            with cols[1]:
                st.write("Days Before:")
                st.caption(rule.get('days_before') or '—')
            with cols[2]:
                st.write("Status:")
                st.caption("Enabled" if rule.get('enabled') else "Disabled")
            with cols[3]:
                if st.button("Toggle", key=f"toggle_{rid}"):
                    try:
                        database.update_notification_rule(rid, {'enabled': 0 if rule.get('enabled') else 1})
                        st.rerun()
                    except Exception as e:
                        st.error(f"Toggle failed: {e}")
            with cols[4]:
                if st.button("Delete", key=f"delete_{rid}"):
                    try:
                        database.delete_notification_rule(rid)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Delete failed: {e}")
            with cols[5]:
                # Run rule for selected enrollment
                if st.button("Run", key=f"run_{rid}"):
                    eid = st.session_state.get('selected_enrollment_id')
                    if not eid:
                        st.warning("Select an enrollment in the Enrollments tab first.")
                    else:
                        # Find enrollment
                        target = None
                        for e in enrollments:
                            if int(e.get('id')) == int(eid):
                                target = e
                                break
                        if not target:
                            st.error("Enrollment not found.")
                        else:
                            try:
                                # Prevent duplicates
                                sent = database.get_sent_notifications(eid)
                                sent_ids = {s.get('rule_id') for s in sent}
                                if rid in sent_ids:
                                    st.info("Already sent for this enrollment.")
                                else:
                                    ok = send_email_notification(target, recipients=rule.get('recipients'), subject=rule.get('rule_name'))
                                    if ok:
                                        database.log_notification_sent(eid, rid)
                                        st.success("Notification sent & logged")
                                    else:
                                        st.warning("Send attempted but may have failed")
                            except Exception as e:
                                st.error(f"Run failed: {e}")

            st.markdown("---")
            st.write("Edit Rule")
            with st.form(key=f"edit_{rid}"):
                new_name = st.text_input("Name", value=rule.get('rule_name'))
                new_trigger = st.selectbox("Trigger", ["On Submission", "On Expiration (days before)", "Manual"], index=["On Submission", "On Expiration (days before)", "Manual"].index(rule.get('trigger')))
                new_recipients_raw = st.text_area("Recipients", value=','.join(rule.get('recipients', [])))
                new_days_before = st.number_input("Days Before", min_value=1, max_value=365, value=rule.get('days_before') or 7)
                new_enabled = st.checkbox("Enabled", value=bool(rule.get('enabled')))
                saved = st.form_submit_button("Save Changes")
                if saved:
                    try:
                        database.update_notification_rule(rid, {
                            'rule_name': new_name,
                            'trigger': new_trigger,
                            'recipients': [r.strip() for r in new_recipients_raw.split(',') if r.strip()],
                            'days_before': int(new_days_before) if 'Expiration' in new_trigger else None,
                            'enabled': 1 if new_enabled else 0
                        })
                        st.success("Updated")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Update failed: {e}")


def _notifications_tab(enrollments, rules, sent):
    st.subheader("Notifications Log")
    if not sent:
        st.info("No notifications logged yet.")
        return
    rule_lookup = {r.get('id'): r.get('rule_name') for r in rules}
    enroll_lookup = {e.get('id'): e for e in enrollments}

    # Simple table
    for n in sent:
        rname = rule_lookup.get(n.get('rule_id'), f"Rule {n.get('rule_id')}")
        enroll = enroll_lookup.get(n.get('enrollment_id'))
        tech = enroll.get('tech_id') if enroll else 'N/A'
        fname = enroll.get('full_name') if enroll else 'Unknown'
        st.write(f"• {n.get('sent_at','')} — {rname} → {fname} ({tech})")

    if st.button("Refresh Log"):
        st.rerun()


# ------------------------------------------------------------
# Entry Point
# ------------------------------------------------------------
def page_admin_control_center():
    st.title("BYOV Admin Control Center")
    st.caption("Operational oversight: enrollments, rules, notifications")

    # Load data once for all tabs
    enrollments = _get_all_enrollments()
    rules = database.get_notification_rules()
    sent = _get_all_sent_notifications()

    tabs = st.tabs(["Overview", "Enrollments", "Rules", "Notifications Log"])

    with tabs[0]:
        _overview_tab(enrollments, rules, sent)
    with tabs[1]:
        _enrollments_tab(enrollments)
    with tabs[2]:
        _rules_tab(enrollments, rules)
    with tabs[3]:
        _notifications_tab(enrollments, rules, sent)

    st.markdown("---")
    st.caption("Select an enrollment in the Enrollments tab before running a rule.")


if __name__ == '__main__':
    page_admin_control_center()
