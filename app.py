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
    "servsafe_card": "ServSafe Card",
    "sexual_harassment_training": "Harassment Training",
    "workplace_violence_training": "Violence Training",
    "damage_notes": "Damage Notes",
    "home_wifi": "Home WiFi",
    "overnight_charge": "Overnight Charge"
}

# --- DATABASE FUNCTIONS ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fleet (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rig_name TEXT UNIQUE,
            status TEXT DEFAULT 'Available'
        )
    ''')
    
    # Dynamically add missing columns
    cursor.execute("PRAGMA table_info(fleet)")
    existing = [col[1] for col in cursor.fetchall()]
    
    for col_id in COLUMNS.keys():
        if col_id not in existing and col_id != "id":
            cursor.execute(f"ALTER TABLE fleet ADD COLUMN {col_id} TEXT DEFAULT ''")
            
    conn.commit()
    conn.close()

def fetch_fleet():
    conn = sqlite3.connect(DB_NAME)
    query = f"SELECT {', '.join(COLUMNS.keys())} FROM fleet"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def update_rig_state(rig_name, data_dict):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    data_dict["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    placeholders = ", ".join([f"{k}=?" for k in data_dict.keys()])
    values = list(data_dict.values())
    values.append(rig_name)
    
    cursor.execute(f"UPDATE fleet SET {placeholders} WHERE rig_name=?", values)
    conn.commit()
    conn.close()

# Initialize the database on startup
init_db()

# --- MAIN UI ---
st.title("Rig Checkout List")

# --- ADMIN AUTHENTICATION (SIDEBAR) ---
st.sidebar.header("System Access")
admin_key = st.sidebar.text_input("Admin Key", type="password")
is_admin = (admin_key == "Hellfire")

if is_admin:
    st.sidebar.divider()
    st.sidebar.subheader("Admin Controls")
    
    # 1. Add Single Rig
    with st.sidebar.expander("Add Single Rig"):
        new_rig = st.text_input("New Rig Name")
        if st.button("Add Rig"):
            if new_rig.strip():
                try:
                    conn = sqlite3.connect(DB_NAME)
                    conn.execute("INSERT INTO fleet (rig_name) VALUES (?)", (new_rig.strip(),))
                    conn.commit()
                    conn.close()
                    st.sidebar.success(f"Added {new_rig.strip()}")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.sidebar.error("Rig already exists.")
            else:
                st.sidebar.warning("Please enter a rig name.")

    # 2. Delete Rig
    with st.sidebar.expander("Delete Rig"):
        conn = sqlite3.connect(DB_NAME)
        all_rigs = [r[0] for r in conn.execute("SELECT rig_name FROM fleet ORDER BY rig_name").fetchall()]
        conn.close()
        
        if all_rigs:
            rig_to_delete = st.selectbox("Select Rig to Delete", all_rigs)
            if st.button("Delete Rig"):
                conn = sqlite3.connect(DB_NAME)
                conn.execute("DELETE FROM fleet WHERE rig_name=?", (rig_to_delete,))
                conn.commit()
                conn.close()
                st.sidebar.success(f"Deleted {rig_to_delete}")
                st.rerun()
        else:
            st.sidebar.info("No rigs in database.")

# --- DASHBOARD & CHECKOUT SYSTEM ---
df = fetch_fleet()

if df.empty:
    st.info("The fleet is currently empty. Please use the Admin panel to add rigs.")
else:
    # Display current fleet status
    st.subheader("Current Fleet Status")
    
    # Display a clean dataframe using the display names
    display_df = df.rename(columns=COLUMNS)
    st.dataframe(display_df, use_container_width=True, hide_index=True)
    
    st.divider()
    
    # Rig Checkout / Update Form
    st.subheader("Update / Checkout Rig")
    
    selected_rig = st.selectbox("Select Rig", df['rig_name'].tolist())
    
    # Get current data for the selected rig to pre-fill the form
    current_data = df[df['rig_name'] == selected_rig].iloc[0].to_dict()
    
    with st.form("checkout_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Basic Info**")
            new_status = st.selectbox("Status", ["Available", "Checked Out", "Maintenance", "Offline"], 
                                      index=["Available", "Checked Out", "Maintenance", "Offline"].index(current_data.get('status', 'Available') if current_data.get('status') in ["Available", "Checked Out", "Maintenance", "Offline"] else "Available"))
            assigned_to = st.text_input("Assigned To", value=current_data.get('assigned_to', ''))
            location = st.text_input("Location", value=current_data.get('location', ''))
            address = st.text_input("Location Address", value=current_data.get('address', ''))
            shift_lead = st.text_input("Shift Lead", value=current_data.get('shift_lead', ''))
            lead_number = st.text_input("Lead Number", value=current_data.get('lead_number', ''))
            damage_notes = st.text_area("Damage Notes", value=current_data.get('damage_notes', ''))

        with col2:
            st.markdown("**Checklist (Check if Yes/Complete)**")
            
            # Helper function to parse 'True'/'False' strings back to booleans for checkboxes
            def parse_bool(val):
                return str(val).lower() == 'true'

            wifi_configured = st.checkbox("Wi-Fi Configured", value=parse_bool(current_data.get('wifi_configured')))
            clothing_shoes = st.checkbox("Appropriate Gear", value=parse_bool(current_data.get('clothing_shoes')))
            batteries_charged = st.checkbox("Batteries Charged", value=parse_bool(current_data.get('batteries_charged')))
            hotspot_connect = st.checkbox("Hotspot Ready", value=parse_bool(current_data.get('hotspot_connect')))
            test_recording = st.checkbox("Test Recording Done", value=parse_bool(current_data.get('test_recording')))
            servsafe_card = st.checkbox("ServSafe Card", value=parse_bool(current_data.get('servsafe_card')))
            sexual_harassment_training = st.checkbox("Harassment Training", value=parse_bool(current_data.get('sexual_harassment_training')))
            workplace_violence_training = st.checkbox("Violence Training", value=parse_bool(current_data.get('workplace_violence_training')))
            home_wifi = st.checkbox("Home WiFi", value=parse_bool(current_data.get('home_wifi')))
            overnight_charge = st.checkbox("Overnight Charge", value=parse_bool(current_data.get('overnight_charge')))

        submit_button = st.form_submit_button("Update Rig Status")
        
        if submit_button:
            # Package the data for the database update
            update_data = {
                "status": new_status,
                "assigned_to": assigned_to,
                "location": location,
                "address": address,
                "shift_lead": shift_lead,
                "lead_number": lead_number,
                "damage_notes": damage_notes,
                "wifi_configured": str(wifi_configured),
                "clothing_shoes": str(clothing_shoes),
                "batteries_charged": str(batteries_charged),
                "hotspot_connect": str(hotspot_connect),
                "test_recording": str(test_recording),
                "servsafe_card": str(servsafe_card),
                "sexual_harassment_training": str(sexual_harassment_training),
                "workplace_violence_training": str(workplace_violence_training),
                "home_wifi": str(home_wifi),
                "overnight_charge": str(overnight_charge)
            }
            
            update_rig_state(selected_rig, update_data)
            st.success(f"Successfully updated {selected_rig}!")
            st.rerun()
