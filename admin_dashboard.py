import os
import streamlit as st
from datetime import datetime, timedelta

import database
from notifications import send_email_notification


def load_rules():
    return database.get_notification_rules()


def save_rule(rule):
    # rule: dict with keys 'rule_name','trigger','recipients'(list),'days_before','enabled'
    database.add_notification_rule(rule)


def page_admin_control_center():
    st.title("BYOV Admin Control Center")
    st.caption("Manage enrollments and notification rules")

    import pandas as pd

    records = database.load_enrollments()
    if not records:
        st.info("No enrollments yet.")
        return

    df = pd.DataFrame(records)
    # show simple table
    st.subheader("Enrollments")
    st.dataframe(df[['submission_date','full_name','tech_id','district','state','referred_by']].sort_values(by='submission_date', ascending=False))

    # Selected record index used by rule-run actions below
    selected_idx = st.number_input("Select record index to act on (0-based)", min_value=0, max_value=max(0, len(records)-1), value=0)

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
                'rule_name': rule_name,
                'trigger': trigger,
                'recipients': [r.strip() for r in recipients.split(',') if r.strip()],
                'days_before': int(days_before),
                'enabled': bool(enabled)
            }
            try:
                database.add_notification_rule(rule)
                st.success("Rule saved")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to save rule: {e}")

    # Show existing rules
    if not rules:
        st.info("No notification rules configured yet.")
    else:
        st.markdown("#### Existing Rules")
        for rule in rules:
            rid = rule.get('id')
            cols = st.columns([3, 2, 2, 1, 1])
            with cols[0]:
                st.markdown(f"**{rule.get('rule_name')}** — {rule.get('trigger')}")
                st.caption(', '.join(rule.get('recipients', [])))
            with cols[1]:
                st.write(f"Days before: {rule.get('days_before') or '-'}")
            with cols[2]:
                st.write("Enabled" if rule.get('enabled') else "Disabled")
            with cols[3]:
                if st.button("Run for Selected", key=f"run_{rid}"):
                    # Run rule for selected record only
                    try:
                        rec = records[selected_idx]
                        enrollment_id = rec.get('id')
                        sent = database.get_sent_notifications(enrollment_id)
                        sent_rule_ids = {s.get('rule_id') for s in sent}
                        if rid in sent_rule_ids:
                            st.info("Rule already sent for this enrollment")
                        else:
                            ok = send_email_notification(rec, recipients=rule.get('recipients'), subject=rule.get('rule_name'))
                            if ok:
                                database.log_notification_sent(enrollment_id, rid)
                                st.success("Notification sent and logged")
                            else:
                                st.warning("Notification attempted but may have failed")
                    except Exception as e:
                        st.error(f"Error running rule: {e}")
            with cols[4]:
                # Enable/disable toggle
                if st.button("Toggle", key=f"toggle_{rid}"):
                    try:
                        new_enabled = 0 if rule.get('enabled') else 1
                        database.update_notification_rule(rid, {'enabled': new_enabled})
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to toggle rule: {e}")
                if st.button("Delete", key=f"delrule_{rid}"):
                    try:
                        database.delete_notification_rule(rid)
                        st.success("Rule deleted")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to delete rule: {e}")

    st.markdown("---")
    st.subheader("Manual Actions")
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
