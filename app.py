import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

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

init_db()

st.title("Rig Checkout List")

# --- ADMIN AUTHENTICATION ---
st.sidebar.header("System Access")
admin_key = st.sidebar.text_input("Admin Key", type="password")
is_admin = (admin_key == "Hellfire")

if is_admin:
    st.sidebar.divider()
    st.sidebar.subheader("Admin Controls")
    
    with st.sidebar.expander("Bulk Import CSV"):
        up = st.file_uploader("Upload CSV Sheet", type=["csv"])
        if up and st.button("Process Import"):
            df_in = pd.read_csv(up)
            df_in = df_in.loc[:, ~df_in.columns.duplicated()]
            
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            
            added_count = 0
            for _, row in df_in.iterrows():
                r_name = str(row.get('Rig Name', '')).strip()
                if not r_name or r_name.lower() == 'nan':
                    continue
                
                def get_val(col_name):
                    val = row.get(col_name, "")
                    return str(val).strip() if pd.notna(val) else ""

                try:
                    cursor.execute('''
                        INSERT OR REPLACE INTO fleet (
                            rig_name, status, assigned_to, location, address, shift_lead, lead_number,
                            wifi_configured, clothing_shoes, batteries_charged, hotspot_connect,
                            test_recording, servsafe_card, sexual_harassment_training,
                            workplace_violence_training, damage_notes, home_wifi, overnight_charge
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        r_name,
                        "Deployed",
                        get_val('Column 1'),
                        get_val('Off-Site Location Name'),
                        get_val('Off-Stie Location Address'),
                        get_val("Off-Site Coordinating Shift Lead's Name"),
                        get_val("Off-Site Coordinating Shift Lead's Number"),
                        get_val('Is your rig configured to the off-site Wi-Fi?'),
                        get_val('Do you have appropriate clothing and shoes?'),
                        get_val('2 batteries (including in rig)- fully charged?'),
                        get_val('Are you able to connect on hotspot?'),
                        get_val('Have you run a test recording on hotspot  (30 seconds)?'),
                        get_val("Do you have a ServSafe food handler's card?"),
                        get_val('Have you completed sexual harassment training?'),
                        get_val('Have you completed workplace violence training?'),
                        get_val('Is there any damage to the rig and if so what is it?'),
                        get_val('Do you have reliable WiFi/Ethernet at home?'),
                        get_val('Can you plug in your rig to charge and upload overnight?')
                    ))
                    added_count += 1
                except Exception as e:
                    st.sidebar.error(f"Error importing {r_name}: {e}")
                    continue
                    
            conn.commit()
            conn.close()
            st.sidebar.success(f"Successfully imported/updated {added_count} rigs.")
            st.rerun()

# --- MAIN TABS ---
tab_checkout, tab_dash, tab_return = st.tabs(["Check Out", "Dashboard", "Return"])

with tab_checkout:
    st.subheader("Deploy Hardware")
    conn = sqlite3.connect(DB_NAME)
    available_rigs = [r[0] for r in conn.execute("SELECT rig_name FROM fleet WHERE status='Available'").fetchall()]
    conn.close()
    
    if available_rigs:
        with st.form("checkout_form"):
            selected_rig = st.selectbox("Select Rig", available_rigs)
            
            col1, col2 = st.columns(2)
            with col1:
                assignee = st.text_input("Assignee Name (Column 1)")
                loc = st.text_input("Off-Site Location Name")
                addr = st.text_input("Off-Site Location Address")
                lead = st.text_input("Shift Lead's Name")
                lead_num = st.text_input("Shift Lead's Number")
            with col2:
                damage = st.text_area("Is there any damage to the rig?", value="No")
                
            st.write("---")
            st.caption("Safety & Technical Checklist")
            
            c1, c2, c3 = st.columns(3)
            wifi = c1.selectbox("Configured to off-site Wi-Fi?", ["Yes", "No"])
            gear = c2.selectbox("Appropriate clothing/shoes?", ["Yes", "No"])
            batt = c3.selectbox("2 batteries fully charged?", ["Yes", "No"])
            
            hotspot = c1.selectbox("Able to connect on hotspot?", ["Yes", "No"])
            test_rec = c2.selectbox("Run test recording (30s)?", ["Yes", "No"])
            servsafe = c3.selectbox("ServSafe food handler's card?", ["Yes", "No"])
            
            harass = c1.selectbox("Completed sexual harassment training?", ["Yes", "No"])
            violence = c2.selectbox("Completed workplace violence training?", ["Yes", "No"])
            home_wifi = c3.selectbox("Reliable WiFi/Ethernet at home?", ["Yes", "No"])
            
            overnight = c1.selectbox("Can charge/upload overnight?", ["Yes", "No"])
            
            if st.form_submit_button("Check Out"):
                payload = {
                    "status": "Deployed",
                    "assigned_to": assignee,
                    "location": loc,
                    "address": addr,
                    "shift_lead": lead,
                    "lead_number": lead_num,
                    "damage_notes": damage,
                    "wifi_configured": wifi,
                    "clothing_shoes": gear,
                    "batteries_charged": batt,
                    "hotspot_connect": hotspot,
                    "test_recording": test_rec,
                    "servsafe_card": servsafe,
                    "sexual_harassment_training": harass,
                    "workplace_violence_training": violence,
                    "home_wifi": home_wifi,
                    "overnight_charge": overnight
                }
                update_rig_state(selected_rig, payload)
                st.success(f"{selected_rig} deployed to {assignee}.")
                st.rerun()
    else:
        st.info("No rigs currently available.")

with tab_dash:
    st.subheader("Fleet Status")
    fleet_data = fetch_fleet()
    
    if fleet_data.empty:
        st.info("Fleet uninitialized. Provision hardware via the Admin portal.")
    else:
        if is_admin:
            st.info("Admin Mode Active: All fields are editable.")
            # Rename columns to human-readable format for the editor
            display_df = fleet_data.rename(columns=COLUMNS)
            
            # Show full dataframe editor
            edited_df = st.data_editor(
                display_df,
                use_container_width=True,
                hide_index=True,
                disabled=["Rig Name", "Last Updated"] # Prevent changing primary key and auto-timestamp
            )
            
            # Check if admin made changes
            if not display_df.equals(edited_df):
                # Map column names back to database schema
                rev_columns = {v: k for k, v in COLUMNS.items()}
                edited_db_df = edited_df.rename(columns=rev_columns)
                
                for i, row in edited_db_df.iterrows():
                    orig_row = fleet_data.iloc[i]
                    if not row.equals(orig_row):
                        # Extract only the changed data for the payload
                        update_payload = row.drop(["rig_name", "last_updated"]).to_dict()
                        update_rig_state(row['rig_name'], update_payload)
                        
                st.success("Database updated successfully!")
                st.rerun()
                
        else:
            # Standard User View
            core_cols = ["rig_name", "status", "assigned_to"]
            
            edited_df = st.data_editor(
                fleet_data[core_cols],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "rig_name": st.column_config.TextColumn("Rig Name", disabled=True),
                    "status": st.column_config.SelectboxColumn("Status", options=["Available", "Deployed", "In Maintenance", "Out of Service", "Servicing"], required=True),
                    "assigned_to": st.column_config.TextColumn("Assigned To", disabled=True),
                }
            )
            
            if not fleet_data[core_cols].equals(edited_df):
                changed_rows = edited_df[edited_df['status'] != fleet_data['status']]
                for _, row in changed_rows.iterrows():
                    update_payload = {"status": row['status']}
                    if row['status'] in ["Available", "In Maintenance", "Out of Service", "Servicing"]:
                        update_payload["assigned_to"] = ""
                    update_rig_state(row['rig_name'], update_payload)
                st.success("Status updated!")
                st.rerun()
            
            with st.expander("Expand Technical & Safety Details"):
                extra_cols = [c for c in fleet_data.columns if c not in core_cols]
                display_df = fleet_data[["rig_name"] + extra_cols].rename(columns=COLUMNS)
                st.dataframe(display_df, hide_index=True, use_container_width=True)

with tab_return:
    st.subheader("Return Hardware")
    conn = sqlite3.connect(DB_NAME)
    deployed = [r[0] for r in conn.execute("SELECT rig_name FROM fleet WHERE status='Deployed'").fetchall()]
    conn.close()
    
    if deployed:
        with st.form("return_form"):
            r_rig = st.selectbox("Select Rig", deployed)
            r_status = st.selectbox("Return Condition", ["Available", "In Maintenance", "Out of Service", "Servicing"])
            if st.form_submit_button("Process Return"):
                # Clear out all the checkout data when returning
                reset_data = {k: "" for k in COLUMNS.keys() if k not in ["rig_name", "status", "last_updated"]}
                reset_data["status"] = r_status
                update_rig_state(r_rig, reset_data)
                st.success(f"{r_rig} returned. Status updated to {r_status}.")
                st.rerun()
    else:
        st.info("No hardware currently deployed.")
```
