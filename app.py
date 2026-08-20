import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import io
import traceback

# --- CONFIG & STATE ---
if "sidebar_state" not in st.session_state:
    st.session_state.sidebar_state = "collapsed"

st.set_page_config(page_title="Rig Checkout System", layout="wide", initial_sidebar_state=st.session_state.sidebar_state)
DB_NAME = "inventory.db"

def safe_rerun():
    try: st.rerun()
    except:
        try: st.experimental_rerun()
        except: st.stop()

COLUMNS = {
    "rig_name": "Rig Name", "status": "Status", "assigned_to": "Assigned To", "location": "Location",
    "last_updated": "Last Updated", "address": "Location Address", "shift_lead": "Shift Lead",
    "lead_number": "Lead Number", "estimated_return": "Estimated Return", "wifi_configured": "Wi-Fi Configured",
    "clothing_shoes": "Appropriate Gear", "batteries_charged": "Batteries Charged", "hotspot_connect": "Hotspot Ready",
    "test_recording": "Test Recording Done", "servsafe_card": "ServSafe Card", "sexual_harassment_training": "Harassment Training",
    "workplace_violence_training": "Violence Training", "damage_notes": "Damage Notes", "home_wifi": "Home WiFi",
    "overnight_charge": "Overnight Charge"
}

# --- DB HELPER ---
def db_op(query, params=(), fetch=None):
    with sqlite3.connect(DB_NAME, timeout=20) as conn:
        if fetch == "df": return pd.read_sql_query(query, conn, params=params)
        cur = conn.cursor()
        cur.execute(query, params)
        conn.commit()
        return cur.fetchall() if fetch == "all" else cur.lastrowid

try:
    def init_db():
        db_op("CREATE TABLE IF NOT EXISTS fleet (id INTEGER PRIMARY KEY AUTOINCREMENT, rig_name TEXT UNIQUE, status TEXT DEFAULT 'Available')")
        existing = [c[1] for c in db_op("PRAGMA table_info(fleet)", fetch="all")]
        for col in COLUMNS:
            if col not in existing and col != "id":
                try: db_op(f'ALTER TABLE fleet ADD COLUMN "{col}" TEXT DEFAULT ""')
                except: pass 
        db_op("CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, rig_name TEXT, action TEXT, assigned_to TEXT, notes TEXT)")

    init_db()

    def log_action(rig_name, action, assigned_to="", notes=""):
        db_op("INSERT INTO audit_log (timestamp, rig_name, action, assigned_to, notes) VALUES (?, ?, ?, ?, ?)",
              (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), rig_name, action, assigned_to, notes))

    def fetch_fleet():
        valid = [c for c in COLUMNS if c in [col[1] for col in db_op("PRAGMA table_info(fleet)", fetch="all")]] or ["rig_name", "status"]
        df = db_op(f"SELECT {', '.join([f'\"{c}\"' for c in valid])} FROM fleet ORDER BY rig_name", fetch="df")
        for c in COLUMNS: 
            if c not in df: df[c] = ""
        return df

    def update_rig_state(rig_name, data):
        data["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db_op(f"UPDATE fleet SET {', '.join([f'\"{k}\"=?' for k in data])} WHERE rig_name=?", list(data.values()) + [rig_name])

    st.title("Rig Checkout List")

    # --- ADMIN ---
    st.sidebar.header("System Access")
    is_admin = (st.sidebar.text_input("Admin Key", type="password") == "Hellfire")
    st.session_state.sidebar_state = "expanded" if is_admin else "collapsed"

    if is_admin:
        st.sidebar.divider()
        st.sidebar.subheader("Admin Controls")
        
        with st.sidebar.expander("Add Single Rig"):
            new_rig = st.text_input("New Rig Name").strip()
            if st.button("Add Rig"):
                if new_rig:
                    try:
                        db_op("INSERT INTO fleet (rig_name, status) VALUES (?, 'Available')", (new_rig,))
                        log_action(new_rig, "Rig Added to Database")
                        st.sidebar.success(f"Added {new_rig}")
                        safe_rerun()
                    except: st.sidebar.error("Rig already exists.")
                else: st.sidebar.warning("Please enter a rig name.")

        with st.sidebar.expander("Delete Rig"):
            all_rigs = [r[0] for r in db_op("SELECT rig_name FROM fleet ORDER BY rig_name", fetch="all")]
            if all_rigs:
                del_rig = st.selectbox("Select Rig to Delete", all_rigs)
                if st.button("Delete Rig"):
                    db_op("DELETE FROM fleet WHERE rig_name=?", (del_rig,))
                    log_action(del_rig, "Rig Deleted from Database")
                    st.sidebar.success(f"Deleted {del_rig}")
                    safe_rerun()
            else: st.sidebar.info("No rigs in database.")
        
        with st.sidebar.expander("Bulk Import CSV"):
            up = st.file_uploader("Upload CSV Sheet", type=["csv"])
            if up and st.button("Process Import"):
                df_in = pd.read_csv(up).loc[:, lambda df: ~df.columns.duplicated()]
                r_col = 'Rig Name' if 'Rig Name' in df_in.columns else df_in.columns[0]
                
                csv_map = {
                    "assigned_to": 'Column 1', "location": 'Off-Site Location Name', "address": 'Off-Stie Location Address',
                    "shift_lead": "Off-Site Coordinating Shift Lead's Name", "lead_number": "Off-Site Coordinating Shift Lead's Number",
                    "estimated_return": "Estimated Return", "wifi_configured": 'Is your rig configured to the off-site Wi-Fi?',
                    "clothing_shoes": 'Do you have appropriate clothing and shoes?', "batteries_charged": '2 batteries (including in rig)- fully charged?',
                    "hotspot_connect": 'Are you able to connect on hotspot?', "test_recording": 'Have you run a test recording on hotspot  (30 seconds)?',
                    "servsafe_card": "Do you have a ServSafe food handler's card?", "sexual_harassment_training": 'Have you completed sexual harassment training?',
                    "workplace_violence_training": 'Have you completed workplace violence training?', "damage_notes": 'Is there any damage to the rig and if so what is it?',
                    "home_wifi": 'Do you have reliable WiFi/Ethernet at home?', "overnight_charge": 'Can you plug in your rig to charge and upload overnight?'
                }

                added = 0
                for _, row in df_in.iterrows():
                    r_name = str(row.get(r_col, '')).strip()
                    if not r_name or r_name.lower() == 'nan': continue
                    
                    payload = {"status": "Available"}
                    for db_k, csv_k in csv_map.items():
                        v = row.get(csv_k, "")
                        payload[db_k] = str(v).strip() if pd.notna(v) else ""
                    
                    cols = ["rig_name"] + list(payload.keys())
                    db_op(f"INSERT OR REPLACE INTO fleet ({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})", [r_name] + list(payload.values()))
                    added += 1
                
                log_action("Bulk Import", f"CSV processed, {added} rigs imported")
                st.sidebar.success(f"Successfully imported {added} rigs.")
                safe_rerun()

        with st.sidebar.expander("Export CSV"):
            fleet_df = fetch_fleet()
            if not fleet_df.empty:
                csv_buf = io.StringIO()
                fleet_df.rename(columns=COLUMNS).to_csv(csv_buf, index=False)
                st.download_button("Download Full Fleet CSV", csv_buf.getvalue(), "fleet_export.csv", "text/csv")
            else: st.sidebar.info("Database is empty. Nothing to export.")

    # --- MAIN TABS ---
    tabs = st.tabs(["Check Out", "Dashboard", "Return", "Needs Servicing"] + (["History Log"] if is_admin else []))

    with tabs[0]:
        st.subheader("Deploy Hardware")
        available_rigs = [r[0] for r in db_op("SELECT rig_name FROM fleet WHERE status='Available' ORDER BY rig_name", fetch="all")]
        
        if available_rigs:
            with st.form("checkout_form"):
                st.caption("Please fill out all required text fields and checklist items to deploy a rig.")
                selected_rig = st.selectbox("Select Rig", [""] + available_rigs)
                
                req_txt, req_dd = {}, {}
                c1, c2 = st.columns(2)
                req_txt["assigned_to"] = ("Assignee Name", c1.text_input("Assignee Name"))
                req_txt["location"] = ("Off-Site Location Name", c1.text_input("Off-Site Location Name"))
                req_txt["address"] = ("Off-Site Location Address", c1.text_input("Off-Site Location Address"))
                req_txt["shift_lead"] = ("Shift Lead's Name", c2.text_input("Shift Lead's Name"))
                req_txt["lead_number"] = ("Shift Lead's Number", c2.text_input("Shift Lead's Number"))
                    
                st.write("---")
                st.caption("Safety & Technical Checklist (Required)")
                c1, c2, c3 = st.columns(3)
                req_dd["wifi_configured"] = ("Configured to off-site Wi-Fi?", c1.selectbox("Configured to off-site Wi-Fi?", ["", "Yes", "No"]))
                req_dd["clothing_shoes"] = ("Appropriate clothing/shoes?", c2.selectbox("Appropriate clothing/shoes?", ["", "Yes", "No"]))
                req_dd["batteries_charged"] = ("2 batteries fully charged?", c3.selectbox("2 batteries fully charged?", ["", "Yes", "No"]))
                req_dd["hotspot_connect"] = ("Able to connect on hotspot?", c1.selectbox("Able to connect on hotspot?", ["", "Yes", "No"]))
                req_dd["test_recording"] = ("Run test recording (30s)?", c2.selectbox("Run test recording (30s)?", ["", "Yes", "No"]))
                req_dd["servsafe_card"] = ("ServSafe food handler's card?", c3.selectbox("ServSafe food handler's card?", ["", "Yes", "No"]))
                req_dd["sexual_harassment_training"] = ("Completed sexual harassment training?", c1.selectbox("Completed sexual harassment training?", ["", "Yes", "No"]))
                req_dd["workplace_violence_training"] = ("Completed workplace violence training?", c2.selectbox("Completed workplace violence training?", ["", "Yes", "No"]))

                st.write("---")
                st.caption("Additional Details & Timing (Optional)")
                c_opt1, c_opt2 = st.columns(2)
                home_wifi = c_opt1.selectbox("Reliable WiFi/Ethernet at home?", ["", "Yes", "No"])
                overnight = c_opt2.selectbox("Can charge/upload overnight?", ["", "Yes", "No"])
                
                col_date, col_time = st.columns(2)
                est_d, est_t = col_date.date_input("Estimated Return Date", value=None), col_time.time_input("Estimated Return Time", value=None)
                
                if st.form_submit_button("Check Out"):
                    miss_t = [name for name, val in req_txt.values() if not val.strip()]
                    miss_d = [name for name, val in req_dd.values() if val == ""]
                    
                    if not selected_rig: st.error("Submission Failed: Please select a rig to deploy.")
                    elif miss_t: st.error(f"Submission Failed: The following text fields are required: {', '.join(miss_t)}")
                    elif miss_d: st.error(f"Submission Failed: Please select an option for the following checklist questions: {', '.join(miss_d)}")
                    else:
                        fmt_ret = f"{est_d.strftime('%Y-%m-%d')} at {est_t.strftime('%I:%M %p')}" if est_d and est_t else (est_d.strftime('%Y-%m-%d') if est_d else (est_t.strftime('%I:%M %p') if est_t else ""))
                        
                        payload = {"status": "Deployed", "estimated_return": fmt_ret, "home_wifi": home_wifi, "overnight_charge": overnight}
                        payload.update({k: v[1] for k, v in req_txt.items()})
                        payload.update({k: v[1] for k, v in req_dd.items()})
                        
                        log_msg = (f"Location: {payload['location']} | Address: {payload['address']} | Lead: {payload['shift_lead']} ({payload['lead_number']}) | Est. Return: {fmt_ret or 'N/A'}\n"
                                   f"Checklist Answers: Wi-Fi ({payload['wifi_configured']}), Gear ({payload['clothing_shoes']}), Batteries ({payload['batteries_charged']}), Hotspot ({payload['hotspot_connect']}), "
                                   f"Test Rec ({payload['test_recording']}), ServSafe ({payload['servsafe_card']}), Harassment Trng ({payload['sexual_harassment_training']}), Violence Trng ({payload['workplace_violence_training']})\n"
                                   f"Optional Info: Home Wi-Fi ({home_wifi or 'N/A'}), Overnight Chg ({overnight or 'N/A'})")
                        
                        update_rig_state(selected_rig, payload)
                        log_action(selected_rig, "Deployed", payload["assigned_to"], log_msg)
                        st.success(f"{selected_rig} deployed to {payload['assigned_to']}." + (f" (Expected Return: {fmt_ret})" if fmt_ret else ""))
                        safe_rerun()
        else: st.info("No rigs currently available in the system. Use the Admin controls to add hardware or import your CSV list.")

    with tabs[1]:
        st.subheader("Fleet Status")
        df = fetch_fleet()
        if df.empty: st.info("Fleet is empty. Use the sidebar Admin controls to import your device list CSV.")
        else:
            disp_df = df.rename(columns=COLUMNS)
            if is_admin:
                st.info("Admin Mode Active: All fields and columns are visible and editable.")
                cfg = {"Status": st.column_config.SelectboxColumn("Status", options=["Available", "Deployed", "Needs Servicing"], required=True)}
                for col in ["Wi-Fi Configured", "Appropriate Gear", "Batteries Charged", "Hotspot Ready", "Test Recording Done", "ServSafe Card", "Harassment Training", "Violence Training", "Home WiFi", "Overnight Charge"]:
                    cfg[col] = st.column_config.SelectboxColumn(options=["Yes", "No", ""])
                
                edited = st.data_editor(disp_df, use_container_width=True, hide_index=True, disabled=["Rig Name", "Last Updated"], column_config=cfg)
                if not disp_df.equals(edited):
                    db_edited = edited.rename(columns={v: k for k, v in COLUMNS.items()})
                    for i, row in db_edited.iterrows():
                        if not row.equals(df.iloc[i]):
                            update_rig_state(row['rig_name'], row.drop(["rig_name", "last_updated"]).to_dict())
                            log_action(row['rig_name'], f"Admin Table Edit -> Status: {row['status']}", row['assigned_to'])
                    st.success("Database updated successfully!")
                    safe_rerun()
            else:
                st.dataframe(disp_df[["Rig Name", "Status", "Assigned To", "Location", "Estimated Return", "Last Updated"]], use_container_width=True, hide_index=True)

    with tabs[2]:
        st.subheader("Return Hardware")
        deployed = [r[0] for r in db_op("SELECT rig_name FROM fleet WHERE status='Deployed' ORDER BY rig_name", fetch="all")]
        if deployed:
            with st.form("return_form"):
                ret_rig = st.selectbox("Select Rig to Return", deployed)
                notes = st.text_area("Return Notes / Damage Report (Optional)")
                if st.form_submit_button("Return Rig"):
                    payload = {k: "" for k in COLUMNS if k not in ["rig_name", "last_updated"]}
                    payload.update({"status": "Available", "damage_notes": notes})
                    update_rig_state(ret_rig, payload)
                    log_action(ret_rig, "Returned", "", notes)
                    st.success(f"{ret_rig} has been returned and is now Available.")
                    safe_rerun()
        else: st.info("No rigs are currently marked as deployed.")

    with tabs[3]:
        st.subheader("Mark Rig for Servicing")
        st.write("Use this section to flag an available rig that needs maintenance, or mark a serviced rig as available again.")
        srv_rigs = [r[0] for r in db_op("SELECT rig_name FROM fleet WHERE status IN ('Available', 'Needs Servicing') ORDER BY rig_name", fetch="all")]
        if srv_rigs:
            with st.form("service_form"):
                srv_rig = st.selectbox("Select Rig", [""] + srv_rigs)
                new_stat = st.selectbox("Update Status", ["Needs Servicing", "Available"])
                notes = st.text_area("Service / Damage Notes (Required)")
                if st.form_submit_button("Update Status"):
                    if not srv_rig: st.error("Submission Failed: Please select a rig.")
                    elif not notes.strip(): st.error("Submission Failed: 'Service / Damage Notes' is required.")
                    else:
                        update_rig_state(srv_rig, {"status": new_stat, "damage_notes": notes.strip()})
                        log_action(srv_rig, f"Status updated to {new_stat}", "", notes.strip())
                        st.success(f"{srv_rig} status successfully updated to {new_stat}.")
                        safe_rerun()
        else: st.info("No available rigs to report.")

    if is_admin:
        with tabs[4]:
            st.subheader("Exchange History Log")
            log_df = db_op('SELECT timestamp as Timestamp, rig_name as "Rig Name", action as Action, assigned_to as "Assigned To", notes as Notes FROM audit_log ORDER BY id DESC', fetch="df")
            if log_df.empty: st.info("No actions have been logged yet.")
            else:
                st.dataframe(log_df, use_container_width=True, hide_index=True)
                c1, c2 = st.columns([2, 1])
                buf = io.StringIO()
                log_df.to_csv(buf, index=False)
                c1.download_button("Download Log CSV", buf.getvalue(), "audit_log.csv", "text/csv")
                if c2.button("Clear History Log", type="primary"):
                    db_op("DELETE FROM audit_log")
                    st.success("History log cleared!")
                    safe_rerun()

except Exception as e:
    st.error("An error occurred while running the app:")
    st.code(traceback.format_exc())
