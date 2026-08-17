import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import io

# --- CONFIGURATION ---
# This sets the clean Title for your browser tab and link previews!
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

@st.cache_resource
def init_db():
    conn = sqlite3.connect(DB_NAME, timeout=10)
    cursor = conn.cursor()
    
    try:
        # Create main fleet table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fleet (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rig_name TEXT UNIQUE,
                status TEXT DEFAULT 'Available'
            )
        ''')
        
        # Ensure all columns exist in fleet table
        cursor.execute("PRAGMA table_info(fleet)")
        existing = [col[1] for col in cursor.fetchall()]
        
        for col_id in COLUMNS.keys():
            if col_id not in existing and col_id != "id":
                cursor.execute(f'ALTER TABLE fleet ADD COLUMN "{col_id}" TEXT DEFAULT ""')
                
        # Create History / Audit Log table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                rig_name TEXT,
                action TEXT,
                assigned_to TEXT,
                notes TEXT
            )
        ''')
                
        conn.commit()
    except Exception as e:
        st.error(f"Database Error: {e}")
    finally:
        conn.close()

def log_action(rig_name, action, assigned_to="", notes=""):
    conn = sqlite3.connect(DB_NAME)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO audit_log (timestamp, rig_name, action, assigned_to, notes) VALUES (?, ?, ?, ?, ?)",
        (timestamp, rig_name, action, assigned_to, notes)
    )
    conn.commit()
    conn.close()

def fetch_fleet():
    conn = sqlite3.connect(DB_NAME)
    # Sorted alphabetically by rig name
    query = f"SELECT {', '.join(COLUMNS.keys())} FROM fleet ORDER BY rig_name"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def update_rig_state(rig_name, data_dict):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    data_dict["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    placeholders = ", ".join([f'"{k}"=?' for k in data_dict.keys()])
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
                    log_action(new_rig.strip(), "Rig Added to Database")
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
            del_rig = st.selectbox("Select Rig to Delete", all_rigs)
            if st.button("Delete Rig"):
                conn = sqlite3.connect(DB_NAME)
                conn.execute("DELETE FROM fleet WHERE rig_name=?", (del_rig,))
                conn.commit()
                conn.close()
                log_action(del_rig, "Rig Deleted from Database")
                st.sidebar.success(f"Deleted {del_rig}")
                st.rerun()
        else:
            st.sidebar.info("No rigs in database.")
    
# 3. Bulk Import CSV
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
            log_action("Bulk Import", f"CSV processed, {added_count} rigs updated/imported")
            st.sidebar.success(f"Successfully imported/updated {added_count} rigs.")
            st.rerun()

# 4. Export CSV
    with st.sidebar.expander("Export CSV"):
        fleet_df = fetch_fleet()
        export_df = fleet_df.rename(columns=COLUMNS)
        csv_buffer = io.StringIO()
        export_df.to_csv(csv_buffer, index=False)
        st.download_button(
            label="Download Full Fleet CSV",
            data=csv_buffer.getvalue(),
            file_name="fleet_export.csv",
            mime="text/csv"
        )

# --- MAIN TABS ---
tab_names = ["Check Out", "Dashboard", "Return", "Needs Servicing"]
if is_admin:
    tab_names.append("History Log")

tabs = st.tabs(tab_names)
tab_checkout, tab_dash, tab_return, tab_service = tabs[0], tabs[1], tabs[2], tabs[3]

with tab_checkout:
    st.subheader("Deploy Hardware")
    conn = sqlite3.connect(DB_NAME)
    available_rigs = [r[0] for r in conn.execute("SELECT rig_name FROM fleet WHERE status='Available' ORDER BY rig_name").fetchall()]
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
            st.caption("Safety & Technical Checklist (All Fields Required)")
            
            # Start dropdowns as blank values
            yn_options = ["", "Yes", "No"]
            damage_options = ["", "No", "Yes"]
            
            c1, c2, c3 = st.columns(3)
            wifi = c1.selectbox("Configured to off-site Wi-Fi?", yn_options)
            gear = c2.selectbox("Appropriate clothing/shoes?", yn_options)
            batt = c3.selectbox("2 batteries fully charged?", yn_options)
            
            hotspot = c1.selectbox("Able to connect on hotspot?", yn_options)
            test_rec = c2.selectbox("Run test recording (30s)?", yn_options)
            servsafe = c3.selectbox("ServSafe food handler's card?", yn_options)
            
            harass = c1.selectbox("Completed sexual harassment training?", yn_options)
            violence = c2.selectbox("Completed workplace violence training?", yn_options)
            home_wifi = c3.selectbox("Reliable WiFi/Ethernet at home?", yn_options)
            
            overnight = c1.selectbox("Can charge/upload overnight?", yn_options)
            damage = c2.selectbox("Is there any damage to the rig?", damage_options)
            
            if st.form_submit_button("Check Out"):
                
                # Validation mapping
                required_dropdowns = {
                    "Configured to off-site Wi-Fi": wifi,
                    "Appropriate clothing/shoes": gear,
                    "2 batteries fully charged": batt,
                    "Able to connect on hotspot": hotspot,
                    "Run test recording (30s)": test_rec,
                    "ServSafe food handler's card": servsafe,
                    "Completed sexual harassment training": harass,
                    "Completed workplace violence training": violence,
                    "Reliable WiFi/Ethernet at home": home_wifi,
                    "Can charge/upload overnight": overnight,
                    "Is there any damage to the rig": damage
                }
                
                missing_fields = [k for k, v in required_dropdowns.items() if v == ""]
                
                if not assignee.strip():
                    st.error("Submission Failed: 'Assignee Name' is required.")
                elif missing_fields:
                    st.error(f"Submission Failed: Please select an option for the following required questions: {', '.join(missing_fields)}")
                else:
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
                    
                    # Formatting the details for the audit log
                    log_details = (
                        f"Location: {loc} | Address: {addr} | Lead: {lead} ({lead_num})\n"
                        f"Checklist Answers: Wi-Fi ({wifi}), Gear ({gear}), Batteries ({batt}), Hotspot ({hotspot}), "
                        f"Test Rec ({test_rec}), ServSafe ({servsafe}), Harassment Trng ({harass}), Violence Trng ({violence}), "
                        f"Home Wi-Fi ({home_wifi}), Overnight Chg ({overnight}), Damage ({damage})"
                    )
                    
                    update_rig_state(selected_rig, payload)
                    log_action(selected_rig, "Deployed", assignee, log_details)
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
            st.info("Admin Mode Active: All fields and columns are visible and editable.")
            display_df = fleet_data.rename(columns=COLUMNS)
            
            editor_config = {
                "Status": st.column_config.SelectboxColumn(
                    "Status",
                    help="Select rig status",
                    options=["Available", "Deployed", "Needs Servicing"],
                    required=True
                )
            }
            
            checklist_cols = [
                "Wi-Fi Configured", "Appropriate Gear", "Batteries Charged", 
                "Hotspot Ready", "Test Recording Done", "ServSafe Card", 
                "Harassment Training", "Violence Training", "Home WiFi", 
                "Overnight Charge"
            ]
            for col in checklist_cols:
                editor_config[col] = st.column_config.SelectboxColumn(
                    options=["Yes", "No", ""]
                )

            edited_df = st.data_editor(
                display_df,
                use_container_width=True,
                hide_index=True,
                disabled=["Rig Name", "Last Updated"], 
                column_config=editor_config,
                key="fleet_data_editor"
            )
            
            if not display_df.equals(edited_df):
                rev_columns = {v: k for k, v in COLUMNS.items()}
                edited_db_df = edited_df.rename(columns=rev_columns)
                
                for i, row in edited_db_df.iterrows():
                    orig_row = fleet_data.iloc[i]
                    if not row.equals(orig_row):
                        update_payload = row.drop(["rig_name", "last_updated"]).to_dict()
                        update_rig_state(row['rig_name'], update_payload)
                        log_action(row['rig_name'], f"Admin Table Edit -> Status: {row['status']}", row['assigned_to'])
                        
                st.success("Database updated successfully!")
                st.rerun()
        else:
            # Standard User View
            display_df = fleet_data.rename(columns=COLUMNS)
            
            visible_columns = [
                "Rig Name", 
                "Status", 
                "Assigned To", 
                "Location",
                "Last Updated"
            ]
            
            display_df = display_df[visible_columns]
            
            st.dataframe(display_df, use_container_width=True, hide_index=True)

with tab_return:
    st.subheader("Return Hardware")
    conn = sqlite3.connect(DB_NAME)
    deployed_rigs = [r[0] for r in conn.execute("SELECT rig_name FROM fleet WHERE status='Deployed' ORDER BY rig_name").fetchall()]
    conn.close()
    
    if deployed_rigs:
        with st.form("return_form"):
            return_rig = st.selectbox("Select Rig to Return", deployed_rigs)
            return_notes = st.text_area("Return Notes / Damage Report (Optional)")
            
            if st.form_submit_button("Return Rig"):
                payload = {
                    "status": "Available",
                    "assigned_to": "",
                    "location": "",
                    "address": "",
                    "shift_lead": "",
                    "lead_number": "",
                    "damage_notes": return_notes,
                    "wifi_configured": "",
                    "clothing_shoes": "",
                    "batteries_charged": "",
                    "hotspot_connect": "",
                    "test_recording": "",
                    "servsafe_card": "",
                    "sexual_harassment_training": "",
                    "workplace_violence_training": "",
                    "home_wifi": "",
                    "overnight_charge": ""
                }
                update_rig_state(return_rig, payload)
                log_action(return_rig, "Returned", "", return_notes)
                st.success(f"{return_rig} has been returned and is now Available.")
                st.rerun()
    else:
        st.info("No rigs are currently deployed.")

with tab_service:
    st.subheader("Mark Rig for Servicing")
    st.write("Use this section to flag an available rig that needs maintenance, or mark a serviced rig as available again.")
    
    conn = sqlite3.connect(DB_NAME)
    serviceable_rigs = [r[0] for r in conn.execute("SELECT rig_name FROM fleet WHERE status IN ('Available', 'Needs Servicing') ORDER BY rig_name").fetchall()]
    conn.close()
    
    if serviceable_rigs:
        with st.form("service_form"):
            srv_rig = st.selectbox("Select Rig", serviceable_rigs)
            new_status = st.selectbox("Update Status", ["Needs Servicing", "Available"])
            srv_notes = st.text_area("Service / Damage Notes (Optional)")
            
            if st.form_submit_button("Update Status"):
                payload = {"status": new_status}
                if srv_notes.strip():
                    payload["damage_notes"] = srv_notes
                
                update_rig_state(srv_rig, payload)
                log_action(srv_rig, f"Status updated to {new_status}", "", srv_notes)
                st.success(f"{srv_rig} status successfully updated to {new_status}.")
                st.rerun()
    else:
        st.info("No available rigs to report. Rigs must be returned before they can be flagged for servicing.")

# Render the 5th tab only if admin is logged in
if is_admin:
    with tabs[4]:
        st.subheader("Exchange History Log")
        
        conn = sqlite3.connect(DB_NAME)
        log_df = pd.read_sql_query('''
            SELECT 
                timestamp as Timestamp, 
                rig_name as "Rig Name", 
                action as Action, 
                assigned_to as "Assigned To", 
                notes as Notes 
            FROM audit_log 
            ORDER BY id DESC
        ''', conn)
        conn.close()
        
        if log_df.empty:
            st.info("No actions have been logged yet.")
        else:
            st.dataframe(log_df, use_container_width=True, hide_index=True)
            
            # Export Log CSV Button
            csv_buffer = io.StringIO()
            log_df.to_csv(csv_buffer, index=False)
            st.download_button(
                label="Download Log CSV",
                data=csv_buffer.getvalue(),
                file_name="audit_log.csv",
                mime="text/csv"
            )
