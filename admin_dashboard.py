import os
import json
import streamlit as st
from datetime import datetime, timedelta

from data_store import load_enrollments, save_enrollments
from notifications import send_email_notification

CONFIG_FILE = "notification_rules.json"


def load_rules():
    if not st.session_state.get('notification_rules'):
        if os.path.exists(CONFIG_FILE):
            try:
                import json
                with open(CONFIG_FILE, 'r') as f:
                    st.session_state.notification_rules = json.load(f)
            except Exception:
                st.session_state.notification_rules = {}
        else:
            st.session_state.notification_rules = {}
    return st.session_state.notification_rules


def save_rules(rules):
    import json
    with open(CONFIG_FILE, 'w') as f:
        json.dump(rules, f, indent=2)


def page_admin_control_center():
    st.title("BYOV Admin Control Center")
    st.caption("Manage enrollments and notification rules")

    import pandas as pd

    records = load_enrollments()
    if not records:
        st.info("No enrollments yet.")
        return

    df = pd.DataFrame(records)
    # show simple table
    st.subheader("Enrollments")
    st.dataframe(df[['submission_date','full_name','tech_id','district','state','referred_by']].sort_values(by='submission_date', ascending=False))

    st.subheader("Notification Rules")

    rules = load_rules()
    # Simple UI: create a new rule
    with st.form("new_rule"):
        st.write("Create a new notification rule")
        rule_name = st.text_input("Rule name")
        trigger = st.selectbox("Trigger", ["On Submission", "On Expiration (days before)", "Manual"])
        recipients = st.text_area("Recipients (comma-separated emails)")
        days_before = st.number_input("Days before expiration (if applicable)", min_value=1, max_value=365, value=7)
        enabled = st.checkbox("Enabled", value=True)
        submit = st.form_submit_button("Save rule")
        if submit:
            rule = {
                'name': rule_name,
                'trigger': trigger,
                'recipients': [r.strip() for r in recipients.split(',') if r.strip()],
                'days_before': int(days_before),
                'enabled': bool(enabled)
            }
            rules.setdefault('rules', []).append(rule)
            save_rules(rules)
            st.success("Rule saved")

    # Show existing rules
    st.write(rules.get('rules', []))

    st.markdown("---")
    st.subheader("Manual Actions")
    selected_idx = st.number_input("Select record index to act on (0-based)", min_value=0, max_value=max(0, len(records)-1), value=0)
    if st.button("Send Test Notification for Selected Record"):
        record = records[selected_idx]
        # temporarily override secrets recipient for testing
        ok = send_email_notification(record)
        if ok:
            st.success("Notification sent (or attempted). Check logs/secrets for details.")
        else:
            st.warning("Notification not sent — check email secrets.")


if __name__ == '__main__':
    page_admin_control_center()
