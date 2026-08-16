My apologies! To make absolutely sure nothing gets lost in translation or cut off, here is the entire, complete script in one single block. You can copy and paste this directly into your Python file, replacing everything you currently have.

It includes the database setup, the admin sidebar, the checkout tab, the dashboard (with your CORE_VIEW_COLS filter applied!), and the return tab.

import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

--- CONFIGURATION ---
st.set_page_config(page_title="Rig Checkout System", layout="wide")
DB_NAME = "inventory.db"

COLUMNS = {
    "rig_name": "Rig Name",
    "status": "Status",
    "assigned_to": "Assigned To",
    "last_updated": "Last Updated",
    "location": "Location",
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

Columns to show by default in the dashboard
CORE_VIEW_COLS = [
    "Rig Name", "Status", "Assigned To", "Location", 
    "Last Updated", "Shift Lead", "Damage Notes"
]

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

--- ADMIN AUTHENTICATION ---
st.sidebar.header("System Access")
admin_key = st.sidebar.text_input("Admin Key", type="password")
is_admin = (admin_key == "Hellfire")

if is_admin:
    st.sidebar.divider()
    st.sidebar.subheader("Admin Controls")

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

    with st.sidebar.expander("Delete Rig"):
        conn = sqlite3.connect(DB_NAME)
        all_rigs = [r[0] for r in conn.execute("SELECT rig_name FROM fleet ORDER BY rig_name").fetchall()]
        conn.close()
        
        if all_rigs:
            del_rig = st.selectbox("Select Rig to Delete", all_rigs)
            if st.button("Delete Rig"):
                conn = sqlite3.connect(DB_NAME)
                conn.execute("DELETE FROM fleet WHERE rig_name=?", (del_rig,))
                conn.commit()
                conn.close()
                st.sidebar.success(f"Deleted {del_rig}")
                st.rerun()
        else:
            st.sidebar.info("No rigs in database.")
    
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

--- MAIN TABS ---
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
                assignee = st.text_input("Assignee Name")
                loc = st.text_input("Off-Site Location Name")
                addr = st.text_input("Off-Site Location Address")
            with col2:
                lead = st.text_input("Shift Lead's Name")
                lead_num = st.text_input("Shift Lead's Number")
                
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
            damage = c2.selectbox("Is there any damage to the rig?", ["No", "Yes"])
            
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
                st.success(f"Rig {selected_rig} deployed successfully!")
                st.rerun()
    else:
        st.info("No rigs are currently available. Please return a rig or add a new one.")

with tab_dash:
    st.subheader("Fleet Dashboard")
    
    df = fetch_fleet()
    df_display = df.rename(columns=COLUMNS)
    
    show_all = st.checkbox("Show full checklist details", value=False)
    
Build column config to hide unwanted columns
    col_config = {"id": None} 
    
    if not show_all:
        for col in df_display.columns:
            if col not in CORE_VIEW_COLS and col != "id":
                col_config[col] = None

    if is_admin:
        st.caption("Admin Mode: You can edit records directly in the table below and save.")
        edited_df = st.data_editor(
            df_display,
            use_container_width=True,
            hide_index=True,
            column_config=col_config,
            key="admin_grid"
        )
        
        if st.button("Save Grid Changes"):
            rev_cols = {v: k for k, v in COLUMNS.items()}
            
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            
            for index, row in edited_df.iterrows():
                rig_name = row["Rig Name"]
                update_data = {rev_cols[col]: str(row[col]) for col in edited_df.columns if col in rev_cols and col != "Rig Name"}
                update_data["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                placeholders = ", ".join([f"{k}=?" for k in update_data.keys()])
                values = list(update_data.values())
                values.append(rig_name)
                
                cursor.execute(f"UPDATE fleet SET {placeholders} WHERE rig_name=?", values)
                
            conn.commit()
            conn.close()
            st.success("Database updated successfully!")
            st.rerun()
    else:
        # Standard view for non-admins
        st.dataframe(
            df_display,
            use_container_width=True,
            hide_index=True,
            column_config=col_config
        )

with tab_return:
    st.subheader("Return Hardware")
    conn = sqlite3.connect(DB_NAME)
    deployed_rigs = [r[0] for r in conn.execute("SELECT rig_name FROM fleet WHERE status='Deployed'").fetchall()]
    conn.close()
    
    if deployed_rigs:
        with st.form("return_form"):
            return_rig = st.selectbox("Select Rig to Return", deployed_rigs)
            new_damage = st.text_area("Log any new damage (Leave blank if none)")
            
            if st.form_submit_button("Process Return"):
                # Fetch existing damage notes so we don't overwrite them if there are new ones
                conn = sqlite3.connect(DB_NAME)
                existing_damage = conn.execute("SELECT damage_notes FROM fleet WHERE rig_name=?", (return_rig,)).fetchone()[0]
                conn.close()
                
                combined_damage = existing_damage
                if new_damage.strip():
                    date_str = datetime.now().strftime("%Y-%m-%d")
                    combined_damage = f"{existing_damage} | [{date_str}] {new_damage.strip()}" if existing_damage else f"[{date_str}] {new_damage.strip()}"

                # Clear out all checkout data but keep the rig name, status, and damage notes
                reset_payload = {k: "" for k in COLUMNS.keys() if k not in ["rig_name", "status", "damage_notes"]}
                reset_payload["status"] = "Available"
                reset_payload["damage_notes"] = combined_damage
                
                update_rig_state(return_rig, reset_payload)
                st.success(f"Rig {return_rig} has been returned and is now Available.")
                st.rerun()
    else:
        st.info("All rigs are currently available. No rigs to return.")
