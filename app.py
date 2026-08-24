import os
import io
from datetime import date
import pandas as pd
import streamlit as st

# --- Page Setup ---
st.set_page_config(
    page_title="Rig Checkout System", 
    page_icon="🚜", 
    layout="centered"
)

st.markdown("""
    <style>
    .block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 720px; }
    </style>
""", unsafe_allow_html=True)

# Standardized columns expected by the system
REQUIRED_COLUMNS = [
    "Inspector Name", 
    "Rig ID", 
    "Checkout Date", 
    "Rig Status", 
    "Hours / Mileage", 
    "Notes / Remarks"
]

# Case-insensitive mapping for external audit logs (e.g., audit_log.csv)
COLUMN_MAPPING = {
    "timestamp": "Checkout Date",
    "date": "Checkout Date",
    "rig name": "Rig ID",
    "rig": "Rig ID",
    "assigned to": "Inspector Name",
    "operator": "Inspector Name",
    "user": "Inspector Name",
    "action": "Rig Status",
    "status": "Rig Status",
    "notes": "Notes / Remarks",
    "remarks": "Notes / Remarks"
}

# --- Initialize Session State ---
if "form_key" not in st.session_state:
    st.session_state.form_key = 0
if "last_submission" not in st.session_state:
    st.session_state.last_submission = None
if "history" not in st.session_state:
    st.session_state.history = pd.DataFrame(columns=REQUIRED_COLUMNS)

fk = st.session_state.form_key

# --- Header ---
st.title("🚜 Rig Checkout System")
st.caption("Perform equipment checkouts, track inspection logs, and import history.")

# --- Tab Navigation ---
tab_checkout, tab_history = st.tabs(["📋 Rig Checkout Form", "📜 History & CSV Import"])

# ================= TAB 1: CHECKOUT FORM =================
with tab_checkout:
    if st.session_state.last_submission:
        st.success(f"🎉 **Checkout Logged Successfully!**\n\nRig **{st.session_state.last_submission['rig']}** logged by **{st.session_state.last_submission['name']}**.")
        st.balloons()
        if st.button("Dismiss Confirmation", type="secondary"):
            st.session_state.last_submission = None
            st.rerun()

    st.subheader("Equipment Checkout Inspection")

    inspector_name = st.text_input("Inspector / Operator Name", placeholder="e.g. Alex Smith", key=f"inspector_{fk}")
    
    col_rig, col_date = st.columns(2)
    with col_rig:
        rig_id = st.text_input("Rig / Equipment ID", placeholder="e.g. RIG-104", key=f"rig_{fk}")
    with col_date:
        checkout_date = st.date_input("Checkout Date", value=date.today(), key=f"date_{fk}")

    col_status, col_hours = st.columns(2)
    with col_status:
        status_options = ["Pass / Ready for Service", "Needs Minor Maintenance", "Out of Service / Grounded", "Deployed", "Returned"]
        rig_status = st.selectbox("Rig Status", status_options, key=f"status_{fk}")
    with col_hours:
        hours_mileage = st.number_input("Current Hours / Mileage", min_value=0, step=1, key=f"hours_{fk}")

    notes = st.text_area("Inspection Notes / Fluid Levels / Issues", placeholder="Detail any issues, fluid top-offs, or observations...", key=f"notes_{fk}")

    if st.button("Submit Checkout Inspection", type="primary", use_container_width=True):
        if not inspector_name.strip():
            st.error("Please enter the Inspector / Operator Name.")
        elif not rig_id.strip():
            st.error("Please enter the Rig / Equipment ID.")
        else:
            new_entry = pd.DataFrame([{
                "Inspector Name": inspector_name.strip(),
                "Rig ID": rig_id.strip().upper(),
                "Checkout Date": str(checkout_date),
                "Rig Status": rig_status,
                "Hours / Mileage": hours_mileage,
                "Notes / Remarks": notes.strip()
            }])
            
            st.session_state.history = pd.concat([st.session_state.history, new_entry], ignore_index=True)
            
            st.session_state.last_submission = {
                "name": inspector_name.strip(),
                "rig": rig_id.strip().upper()
            }
            st.session_state.form_key += 1
            st.rerun()

# ================= TAB 2: HISTORY & CSV IMPORT =================
with tab_history:
    st.subheader("📥 Import Checkout History from CSV")
    st.caption("Upload an existing CSV file (such as audit_log.csv) to append past records.")
    
    uploaded_file = st.file_uploader("Upload CSV File", type=["csv"])
    
    if uploaded_file is not None:
        try:
            imported_df = pd.read_csv(uploaded_file)
            
            # Map headers dynamically (e.g. 'Timestamp' -> 'Checkout Date', 'Rig Name' -> 'Rig ID')
            rename_dict = {}
            for col in imported_df.columns:
                cleaned_col = str(col).strip().lower()
                if cleaned_col in COLUMN_MAPPING:
                    rename_dict[col] = COLUMN_MAPPING[cleaned_col]
            
            df_mapped = imported_df.rename(columns=rename_dict)
            
            # Fill missing columns (such as Hours / Mileage if absent) with N/A
            for col in REQUIRED_COLUMNS:
                if col not in df_mapped.columns:
                    df_mapped[col] = "N/A"
            
            df_final = df_mapped[REQUIRED_COLUMNS].fillna("N/A")
            
            st.markdown("**Preview of Auto-Mapped Import Data:**")
            st.dataframe(df_final.head(), use_container_width=True)
            
            if st.button("📥 Append CSV to History Log", type="primary"):
                st.session_state.history = pd.concat(
                    [st.session_state.history, df_final], 
                    ignore_index=True
                ).fillna("N/A")
                st.success(f"Successfully imported {len(df_final)} record(s) from CSV!")
                st.rerun()
                
        except Exception as e:
            st.error(f"Error parsing CSV file: {e}")

    st.markdown("---")
    st.subheader("📜 Active Rig Checkout Log")
    
    if not st.session_state.history.empty:
        st.dataframe(st.session_state.history, use_container_width=True)
        
        col_dl, col_clr = st.columns([2, 1])
        with col_dl:
            csv_buffer = io.StringIO()
            st.session_state.history.to_csv(csv_buffer, index=False)
            st.download_button(
                label="💾 Download History as CSV",
                data=csv_buffer.getvalue(),
                file_name="rig_checkout_history.csv",
                mime="text/csv",
                use_container_width=True
            )
        with col_clr:
            if st.button("🗑️ Clear All History", type="secondary", use_container_width=True):
                st.session_state.history = pd.DataFrame(columns=REQUIRED_COLUMNS)
                st.rerun()
    else:
        st.info("No checkout logs recorded yet. Submit a form above or import a CSV file.")
