import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# --- CONFIGURATION ---
st.set_page_config(page_title="Rig Checkout System", layout="wide")
DB_NAME = "inventory.db"

# Define the full schema based on the CSV headers
COLUMNS = {
    "rig_name": "Rig Name",
    "status": "Status",
    "assigned_to": "Assigned To",
    "location": "Location",
    "last_updated": "Last Updated",
    "address": "Location Address",
    "shift_lead": "Shift Lead",
    "lead_number": "Lead Number",
    "wifi_configured": "Wi-Fi Configured",
    "clothing_shoes": "Appropriate Gear",
    "batteries_charged": "Batteries Charged",
    "hotspot_connect": "Hotspot Ready",
    "test_recording": "Test Recording Done",
    "servsafe_card": "ServSafe Card"
}

def init_db():
    """Initialize the SQLite database and create the table if it doesn't exist."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS rigs (
            rig_name TEXT PRIMARY KEY,
            status TEXT,
            assigned_to TEXT,
            location TEXT,
            last_updated TEXT,
            address TEXT,
            shift_lead TEXT,
            lead_number TEXT,
            wifi_configured BOOLEAN,
            clothing_shoes BOOLEAN,
            batteries_charged BOOLEAN,
            hotspot_connect BOOLEAN,
            test_recording BOOLEAN,
            servsafe_card BOOLEAN
        )
    ''')
    
    # Seed initial data if the table is empty
    c.execute("SELECT COUNT(*) FROM rigs")
    if c.fetchone()[0] == 0:
        default_rigs = [f"Pumice V2.1 - Rig {i}" for i in range(1, 11)]
        for rig in default_rigs:
            c.execute("INSERT INTO rigs (rig_name, status) VALUES (?, 'Available')", (rig,))
            
    conn.commit()
    conn.close()

def get_data():
    """Retrieve all rig data from the database."""
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM rigs", conn)
    conn.close()
    return df

def update_rig(rig_name, data):
    """Update a specific rig's record in the database."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    set_clause = ", ".join([f"{k} = ?" for k in data.keys()])
    values = list(data.values())
    values.append(rig_name)
    
    c.execute(f"UPDATE rigs SET {set_clause} WHERE rig_name = ?", values)
    conn.commit()
    conn.close()

def main():
    init_db()
    
    st.title("Pumice V2.1 Rig Checkout System")
    st.markdown("Automated checkout and tracking for field operations.")
    
    menu = ["Dashboard", "Checkout Rig", "Check-in Rig"]
    choice = st.sidebar.selectbox("Navigation", menu)
    
    df = get_data()
    
    if choice == "Dashboard":
        st.subheader("Current Rig Status")
        
        # Display metrics
        total_rigs = len(df)
        checked_out = len(df[df['status'] == 'Checked Out'])
        available = total_rigs - checked_out
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Rigs", total_rigs)
        col2.metric("Available", available)
        col3.metric("Deployed", checked_out)
        
        st.divider()
        
        # Display dataframe
        display_df = df.rename(columns=COLUMNS)
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        
    elif choice == "Checkout Rig":
        st.subheader("Deploy a Rig")
        available_rigs = df[df['status'] != 'Checked Out']['rig_name'].tolist()
        
        if not available_rigs:
            st.warning("No rigs are currently available for checkout.")
            return
            
        with st.form("checkout_form"):
            rig_name = st.selectbox("Select Rig", available_rigs)
            
            st.write("### Assignment Details")
            col1, col2 = st.columns(2)
            with col1:
                assigned_to = st.text_input("Assigned To (Data Collector)")
                location = st.text_input("Location (e.g., Sports, Agriculture, Auto)")
                address = st.text_input("Specific Address")
            with col2:
                shift_lead = st.text_input("Shift Lead")
                lead_number = st.text_input("Lead Contact Number")
            
            st.write("### Pre-Deployment Checklist")
            st.caption("All items must be verified before deployment.")
            
            chk_col1, chk_col2 = st.columns(2)
            with chk_col1:
                wifi_configured = st.checkbox("Wi-Fi Configured")
                clothing_shoes = st.checkbox("Appropriate Gear Verified")
                batteries_charged = st.checkbox("Batteries Fully Charged")
            with chk_col2:
                hotspot_connect = st.checkbox("Hotspot Ready & Connected")
                test_recording = st.checkbox("Test Recording Successful")
                servsafe_card = st.checkbox("ServSafe Card (If applicable)")
                
            submit = st.form_submit_button("Complete Checkout")
            
            if submit:
                if not assigned_to or not location:
                    st.error("Error: 'Assigned To' and 'Location' are required fields.")
                else:
                    update_data = {
                        "status": "Checked Out",
                        "assigned_to": assigned_to,
                        "location": location,
                        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "address": address,
                        "shift_lead": shift_lead,
                        "lead_number": lead_number,
                        "wifi_configured": wifi_configured,
                        "clothing_shoes": clothing_shoes,
                        "batteries_charged": batteries_charged,
                        "hotspot_connect": hotspot_connect,
                        "test_recording": test_recording,
                        "servsafe_card": servsafe_card
                    }
                    update_rig(rig_name, update_data)
                    st.success(f"{rig_name} successfully checked out to {assigned_to}!")
                    st.rerun()
                    
    elif choice == "Check-in Rig":
        st.subheader("Return a Rig")
        checked_out_rigs = df[df['status'] == 'Checked Out']['rig_name'].tolist()
        
        if not checked_out_rigs:
            st.info("All rigs are currently in the lab.")
            return
            
        with st.form("checkin_form"):
            rig_name = st.selectbox("Select Rig to Return", checked_out_rigs)
            
            st.write("### Post-Deployment Verification")
            data_uploaded = st.checkbox("RoboCaps Data Uploaded & Verified")
            hardware_intact = st.checkbox("Hardware Inspected & Intact")
            
            submit = st.form_submit_button("Complete Check-in")
            
            if submit:
                if not (data_uploaded and hardware_intact):
                    st.warning("Please verify data upload and hardware integrity before checking in.")
                else:
                    # Reset all fields to default for the next user
                    update_data = {
                        "status": "Available",
                        "assigned_to": "",
                        "location": "",
                        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "address": "",
                        "shift_lead": "",
                        "lead_number": "",
                        "wifi_configured": False,
                        "clothing_shoes": False,
                        "batteries_charged": False,
                        "hotspot_connect": False,
                        "test_recording": False,
                        "servsafe_card": False
                    }
                    update_rig(rig_name, update_data)
                    st.success(f"{rig_name} successfully checked in and is now available!")
                    st.rerun()

if __name__ == "__main__":
    main()
