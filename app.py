import os
import io
from datetime import date, timedelta
import requests
import pandas as pd
import streamlit as st

# Configure page & favicons
st.set_page_config(
    page_title="Attendance Notice", 
    page_icon="📋", 
    layout="centered"
)

st.markdown("""
    <style>
    .block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 680px; }
    </style>
""", unsafe_allow_html=True)

# Fetch Slack Webhook URL
SLACK_WEBHOOK_URL = st.secrets.get("SLACK_WEBHOOK_URL", os.environ.get("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"))

TYPE_CONFIGS = {
    "Call Out (Full Day)": {"emoji": "🚨"},
    "Call Out AM": {"emoji": "🌅"},
    "Call Out PM": {"emoji": "🌇"},
    "Late": {"emoji": "⏳"},
    "Leave Early": {"emoji": "🏃"}
}

def notify_slack(name, start_d, end_d, status, time_info, reason):
    """Pushes a formatted attendance notice to Slack."""
    if start_d == end_d:
        d_str = start_d.strftime("%A, %b %d, %Y")
    else:
        d_str = f"{start_d.strftime('%a, %b %d')} ➔ {end_d.strftime('%a, %b %d, %Y')}"
        
    emoji = TYPE_CONFIGS.get(status, {}).get("emoji", "📌")
    
    schedule_line = f"• *{d_str}*: {emoji} {status}"
    if time_info:
        schedule_line += f" _({time_info})_"
        
    color = "#FF3B30" if "Call Out" in status else "#FF9500"

    payload = {
        "attachments": [
            {
                "color": color,
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"📋 *Attendance Schedule Update*\n*Name:* {name}\n\n*Schedule Details:*\n{schedule_line}\n\n*Context:* {reason}"
                        }
                    }
                ]
            }
        ]
    }
    
    try:
        response = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=5)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        st.error(f"Slack webhook failed: {e}")
        return False

# Initialize session state variables
if "form_key" not in st.session_state:
    st.session_state.form_key = 0
if "last_submission" not in st.session_state:
    st.session_state.last_submission = None
if "history" not in st.session_state:
    st.session_state.history = pd.DataFrame(columns=[
        "Name", "Start Date", "End Date", "Status", "Time Details", "Reason"
    ])

fk = st.session_state.form_key

# --- App Header ---
st.title("📋 Attendance System")
st.caption("Submit notices directly to Slack & manage attendance logs.")

# --- Tab Layout ---
tab_submit, tab_history = st.tabs(["📋 Submit Notice", "📜 History & CSV Import"])

# ================= TAB 1: UNIFIED SUBMISSION FORM =================
with tab_submit:
    if st.session_state.last_submission:
        st.success(f"🎉 **Notice Submitted Successfully!**\n\nNotification sent to Slack for **{st.session_state.last_submission}**.")
        st.balloons()
        if st.button("Dismiss Confirmation", type="secondary"):
            st.session_state.last_submission = None
            st.rerun()

    worker_name = st.text_input("Team Member Name", placeholder="e.g. John Doe", key=f"name_{fk}")

    options = ["Call Out (Full Day)", "Call Out AM", "Call Out PM", "Late", "Leave Early"]
    selected_status = st.selectbox("Status / Action", options, key=f"status_{fk}")

    col_start, col_end = st.columns(2)
    with col_start:
        start_date = st.date_input("Start Date", value=None, key=f"start_{fk}")
    with col_end:
        end_date = st.date_input("End Date (Optional)", value=None, help="Leave blank for a single day.", key=f"end_{fk}")

    time_info = st.text_input(
        "Time Details (Optional for Full Day)", 
        placeholder="e.g., Arriving at 10:30 AM / Leaving at 2 PM", 
        key=f"time_{fk}"
    )

    reason = st.text_area("Reason / Context", placeholder="Brief explanation for your shift adjustment...", key=f"reason_{fk}")

    if st.button("Submit Notification", type="primary", use_container_width=True):
        actual_end = end_date if end_date else start_date
        
        # Validation
        if not worker_name.strip():
            st.error("Please enter your name.")
        elif not start_date:
            st.error("Please select a Start Date.")
        elif actual_end < start_date:
            st.error("End Date cannot be before the Start Date.")
        elif selected_status in ["Late", "Leave Early"] and not time_info.strip():
            st.error(f"Please provide Time Details for '{selected_status}'.")
        elif not reason.strip():
            st.error("Please provide a Reason / Context.")
        else:
            # Send Slack webhook
            if notify_slack(worker_name.strip(), start_date, actual_end, selected_status, time_info.strip(), reason.strip()):
                # Append to history DataFrame
                new_entry = pd.DataFrame([{
                    "Name": worker_name.strip(),
                    "Start Date": str(start_date),
                    "End Date": str(actual_end),
                    "Status": selected_status,
                    "Time Details": time_info.strip(),
                    "Reason": reason.strip()
                }])
                st.session_state.history = pd.concat([st.session_state.history, new_entry], ignore_index=True)
                
                st.session_state.last_submission = worker_name.strip()
                st.session_state.form_key += 1
                st.rerun()

# ================= TAB 2: HISTORY & CSV IMPORT =================
with tab_history:
    st.subheader("Import History from CSV")
    st.caption("Upload a CSV file containing past entries to append them to your log.")
    
    uploaded_file = st.file_uploader("Upload CSV", type=["csv"])
    
    if uploaded_file is not None:
        try:
            imported_df = pd.read_csv(uploaded_file)
            required_cols = ["Name", "Start Date", "End Date", "Status", "Time Details", "Reason"]
            
            # Check for required headers
            missing_cols = [col for col in required_cols if col not in imported_df.columns]
            
            if missing_cols:
                st.error(f"Missing required columns in CSV: {', '.join(missing_cols)}")
                st.info(f"Required headers: `{', '.join(required_cols)}`")
            else:
                if st.button("📥 Import into History Log", type="primary"):
                    st.session_state.history = pd.concat(
                        [st.session_state.history, imported_df[required_cols]], 
                        ignore_index=True
                    ).fillna("")
                    st.success(f"Successfully imported {len(imported_df)} record(s)!")
                    st.rerun()
        except Exception as e:
            st.error(f"Error processing CSV file: {e}")

    st.markdown("---")
    st.subheader("Attendance History Log")
    
    if not st.session_state.history.empty:
        st.dataframe(st.session_state.history, use_container_width=True)
        
        col_dl, col_clr = st.columns([2, 1])
        with col_dl:
            csv_buffer = io.StringIO()
            st.session_state.history.to_csv(csv_buffer, index=False)
            st.download_button(
                label="💾 Download Log as CSV",
                data=csv_buffer.getvalue(),
                file_name="attendance_history.csv",
                mime="text/csv",
                use_container_width=True
            )
        with col_clr:
            if st.button("🗑️ Clear Log", type="secondary", use_container_width=True):
                st.session_state.history = pd.DataFrame(columns=[
                    "Name", "Start Date", "End Date", "Status", "Time Details", "Reason"
                ])
                st.rerun()
    else:
        st.info("No history records yet. Submit a notice or import a CSV above.")
