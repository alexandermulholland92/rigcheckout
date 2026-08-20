import streamlit as st, sqlite3, pandas as pd, traceback
from datetime import datetime

# --- CONFIG & STATE ---
if "sidebar_state" not in st.session_state: st.session_state.sidebar_state = "collapsed"
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
def db_op(q, p=(), fetch=None):
    with sqlite3.connect(DB_NAME, timeout=20) as conn:
        if fetch == "df": return pd.read_sql_query(q, conn, params=p)
        cur = conn.cursor()
        cur.execute(q, p)
        conn.commit()
        return cur.fetchall() if fetch == "all" else cur.lastrowid

try:
    db_op("CREATE TABLE IF NOT EXISTS fleet (id INTEGER PRIMARY KEY AUTOINCREMENT, rig_name TEXT UNIQUE, status TEXT DEFAULT 'Available')")
    existing = [c[1] for c in db_op("PRAGMA table_info(fleet)", fetch="all")]
    for col in [c for c in COLUMNS if c not in existing and c != "id"]:
        try: db_op(f'ALTER TABLE fleet ADD COLUMN "{col}" TEXT DEFAULT ""')
        except: pass 
    db_op("CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, rig_name TEXT, action TEXT, assigned_to TEXT, notes TEXT)")

    def log_action(rig, act, assign="", note=""):
        db_op("INSERT INTO audit_log (timestamp, rig_name, action, assigned_to, notes) VALUES (?, ?, ?, ?, ?)", (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), rig, act, assign, note))

    def fetch_fleet():
        valid = [c for c in COLUMNS if c in [col[1] for col in db_op("PRAGMA table_info(fleet)", fetch="all")]] or ["rig_name", "status"]
        df = db_op(f"SELECT {', '.join([f'\"{c}\"' for c in valid])} FROM fleet ORDER BY rig_name", fetch="df")
        for c in COLUMNS: 
            if c not in df: df[c] = ""
        return df

    def update_rig(rig, data):
        data["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db_op(f"UPDATE fleet SET {', '.join([f'\"{k}\"=?' for k in data])} WHERE rig_name=?", list(data.values()) + [rig])

    st.title("Rig Checkout List")

   # --- ADMIN ---
    st.sidebar.header("System Access")
    admin_pass = st.secrets.get("ADMIN_PASSWORD", "")
    is_admin = bool(admin_pass) and (st.sidebar.text_input("Admin Key", type="password") == admin_pass)
    st.session_state.sidebar_state = "expanded" if is_admin else "collapsed"
    
    if is_admin:
        st.sidebar.divider()
        st.sidebar.subheader("Admin Controls")
        
        with st.sidebar.expander("Add Single Rig"):
            if st.button("Add Rig") and (new_rig := st.text_input("New Rig Name").strip()):
                try:
                    db_op("INSERT INTO fleet (rig_name, status) VALUES (?, 'Available')", (new_rig,))
                    log_action(new_rig, "Rig Added to Database")
                    st.sidebar.success(f"Added {new_rig}"); safe_rerun()
                except: st.sidebar.error("Rig already exists.")
        
        with st.sidebar.expander("Delete Rig"):
            if all_rigs := [r[0] for r in db_op("SELECT rig_name FROM fleet ORDER BY rig_name", fetch="all")]:
                del_rig = st.selectbox("Select Rig to Delete", all_rigs)
                if st.button("Delete Rig"):
                    db_op("DELETE FROM fleet WHERE rig_name=?", (del_rig,))
                    log_action(del_rig, "Rig Deleted from Database")
                    st.sidebar.success(f"Deleted {del_rig}"); safe_rerun()
            else: st.sidebar.info("No rigs in database.")
        
        with st.sidebar.expander("Bulk Import CSV"):
            if (up := st.file_uploader("Upload CSV Sheet", type=["csv"])) and st.button("Process Import"):
                df_in = pd.read_csv(up).loc[:, lambda df: ~df.columns.duplicated()]
                r_col = 'Rig Name' if 'Rig Name' in df_in.columns else df_in.columns[0]
                
                csv_map = {"assigned_to": 'Column 1', "location": 'Off-Site Location Name', "address": 'Off-Stie Location Address', "shift_lead": "Off-Site Coordinating Shift Lead's Name", "lead_number": "Off-Site Coordinating Shift Lead's Number", "estimated_return": "Estimated Return", "wifi_configured": 'Is your rig configured to the off-site Wi-Fi?', "clothing_shoes": 'Do you have appropriate clothing and shoes?', "batteries_charged": '2 batteries (including in rig)- fully charged?', "hotspot_connect": 'Are you able to connect on hotspot?', "test_recording": 'Have you run a test recording on hotspot  (30 seconds)?', "servsafe_card": "Do you have a ServSafe food handler's card?", "sexual_harassment_training": 'Have you completed sexual harassment training?', "workplace_violence_training": 'Have you completed workplace violence training?', "damage_notes": 'Is there any damage to the rig and if so what is it?', "home_wifi": 'Do you have reliable WiFi/Ethernet at home?', "overnight_charge": 'Can you plug in your rig to charge and upload overnight?'}

                added = 0
                for _, row in df_in.iterrows():
                    if not (r_name := str(row.get(r_col, '')).strip()) or r_name.lower() == 'nan': continue
                    payload = {"status": "Available"}
                    payload.update({db_k: str(row.get(csv_k, "")).strip() if pd.notna(row.get(csv_k, "")) else "" for db_k, csv_k in csv_map.items()})
                    
                    cols = ["rig_name"] + list(payload.keys())
                    db_op(f"INSERT OR REPLACE INTO fleet ({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})", [r_name] + list(payload.values()))
                    added += 1
                
                log_action("Bulk Import", f"CSV processed, {added} rigs imported")
                st.sidebar.success(f"Successfully imported {added} rigs."); safe_rerun()

        with st.sidebar.expander("Export CSV"):
            if not (fleet_df := fetch_fleet()).empty:
                st.download_button("Download Full Fleet CSV", fleet_df.rename(columns=COLUMNS).to_csv(index=False).encode('utf-8'), "fleet_export.csv", "text/csv")
            else: st.sidebar.info("Database empty.")

    # --- MAIN TABS ---
    tabs = st.tabs(["Check Out", "Dashboard", "Return", "Needs Servicing"] + (["History Log"] if is_admin else []))

    with tabs[0]:
        st.subheader("Deploy Hardware")
        if avail := [r[0] for r in db_op("SELECT rig_name FROM fleet WHERE status='Available' ORDER BY rig_name", fetch="all")]:
            with st.form("checkout_form"):
                st.caption("Please fill out all required text fields and checklist items to deploy a rig.")
                sel_rig = st.selectbox("Select Rig", [""] + avail)
                
                c1, c2 = st.columns(2)
                t_flds = [("assigned_to", "Assignee Name", c1), ("location", "Off-Site Location Name", c1), ("address", "Off-Site Location Address", c1), ("shift_lead", "Shift Lead's Name", c2), ("lead_number", "Shift Lead's Phone Number", c2)]
                req_t = {k: (lbl, col.text_input(lbl)) for k, lbl, col in t_flds}
                    
                st.write("---"); st.caption("Safety & Technical Checklist (Required)")
                cols = st.columns(3)
                d_flds = [("wifi_configured", "Configured to off-site Wi-Fi?", 0), ("clothing_shoes", "Appropriate clothing/shoes?", 1), ("batteries_charged", "2 batteries fully charged?", 2), ("hotspot_connect", "Able to connect on hotspot?", 0), ("test_recording", "Run test recording (30s)?", 1), ("servsafe_card", "ServSafe food handler's card?", 2), ("sexual_harassment_training", "Completed sexual harassment training?", 0), ("workplace_violence_training", "Completed workplace violence training?", 1)]
                req_d = {k: (lbl, cols[idx].selectbox(lbl, ["", "Yes", "No"])) for k, lbl, idx in d_flds}

                st.write("---"); st.caption("Additional Details & Timing (Optional)")
                c_opt1, c_opt2 = st.columns(2)
                h_wifi = c_opt1.selectbox("Reliable WiFi/Ethernet at home?", ["", "Yes", "No"])
                o_charge = c_opt2.selectbox("Can charge/upload overnight?", ["", "Yes", "No"])
                
                cd, ct = st.columns(2)
                est_d, est_t = cd.date_input("Estimated Return Date", value=None), ct.time_input("Estimated Return Time", value=None)
                
                if st.form_submit_button("Check Out"):
                    miss_t, miss_d = [n for n, v in req_t.values() if not v.strip()], [n for n, v in req_d.values() if v == ""]
                    
                    if not sel_rig: st.error("Submission Failed: Please select a rig to deploy.")
                    elif miss_t: st.error(f"Submission Failed: The following text fields are required: {', '.join(miss_t)}")
                    elif miss_d: st.error(f"Submission Failed: Please select an option for the following checklist questions: {', '.join(miss_d)}")
                    else:
                        fmt_ret = f"{est_d.strftime('%Y-%m-%d')} at {est_t.strftime('%I:%M %p')}" if est_d and est_t else (est_d.strftime('%Y-%m-%d') if est_d else (est_t.strftime('%I:%M %p') if est_t else ""))
                        payload = {"status": "Deployed", "estimated_return": fmt_ret, "home_wifi": h_wifi, "overnight_charge": o_charge, **{k: v[1] for d in (req_t, req_d) for k, v in d.items()}}
                        
                        log_msg = (f"Location: {payload['location']} | Address: {payload['address']} | Lead: {payload['shift_lead']} ({payload['lead_number']}) | Est. Return: {fmt_ret or 'N/A'}\n"
                                   f"Checklist Answers: Wi-Fi ({payload['wifi_configured']}), Gear ({payload['clothing_shoes']}), Batteries ({payload['batteries_charged']}), Hotspot ({payload['hotspot_connect']}), Test Rec ({payload['test_recording']}), ServSafe ({payload['servsafe_card']}), Harassment Trng ({payload['sexual_harassment_training']}), Violence Trng ({payload['workplace_violence_training']})\n"
                                   f"Optional Info: Home Wi-Fi ({h_wifi or 'N/A'}), Overnight Chg ({o_charge or 'N/A'})")
                        
                        update_rig(sel_rig, payload)
                        log_action(sel_rig, "Deployed", payload["assigned_to"], log_msg)
                        st.success(f"{sel_rig} deployed to {payload['assigned_to']}." + (f" (Expected Return: {fmt_ret})" if fmt_ret else "")); safe_rerun()
        else: st.info("No rigs currently available in the system. Use the Admin controls to add hardware or import your CSV list.")

    with tabs[1]:
        st.subheader("Fleet Status")
        if (df := fetch_fleet()).empty: st.info("Fleet is empty. Use the sidebar Admin controls to import your device list CSV.")
        else:
            disp = df.rename(columns=COLUMNS)
            if is_admin:
                st.info("Admin Mode Active: All fields and columns are visible and editable.")
                cfg = {"Status": st.column_config.SelectboxColumn("Status", options=["Available", "Deployed", "Needs Servicing"], required=True), **{c: st.column_config.SelectboxColumn(options=["Yes", "No", ""]) for c in ["Wi-Fi Configured", "Appropriate Gear", "Batteries Charged", "Hotspot Ready", "Test Recording Done", "ServSafe Card", "Harassment Training", "Violence Training", "Home WiFi", "Overnight Charge"]}}
                if not disp.equals(edited := st.data_editor(disp, use_container_width=True, hide_index=True, disabled=["Rig Name", "Last Updated"], column_config=cfg)):
                    for i, r in edited.rename(columns={v: k for k, v in COLUMNS.items()}).iterrows():
                        if not r.equals(df.iloc[i]):
                            update_rig(r['rig_name'], r.drop(["rig_name", "last_updated"]).to_dict())
                            log_action(r['rig_name'], f"Admin Table Edit -> Status: {r['status']}", r['assigned_to'])
                    st.success("Database updated successfully!"); safe_rerun()
            else: st.dataframe(disp[["Rig Name", "Status", "Assigned To", "Location", "Estimated Return", "Last Updated"]], use_container_width=True, hide_index=True)

    with tabs[2]:
        st.subheader("Return Hardware")
        if deployed := [r[0] for r in db_op("SELECT rig_name FROM fleet WHERE status='Deployed' ORDER BY rig_name", fetch="all")]:
            with st.form("return_form"):
                ret_rig = st.selectbox("Select Rig to Return", deployed)
                notes = st.text_area("Return Notes / Damage Report (Optional)")
                if st.form_submit_button("Return Rig"):
                    update_rig(ret_rig, {**{k: "" for k in COLUMNS if k not in ["rig_name", "last_updated"]}, "status": "Available", "damage_notes": notes})
                    log_action(ret_rig, "Returned", "", notes)
                    st.success(f"{ret_rig} has been returned and is now Available."); safe_rerun()
        else: st.info("No rigs are currently marked as deployed.")

    with tabs[3]:
        st.subheader("Mark Rig for Servicing")
        st.write("Use this section to flag an available rig that needs maintenance, or mark a serviced rig as available again.")
        if srv_rigs := [r[0] for r in db_op("SELECT rig_name FROM fleet WHERE status IN ('Available', 'Needs Servicing') ORDER BY rig_name", fetch="all")]:
            with st.form("service_form"):
                srv_rig = st.selectbox("Select Rig", [""] + srv_rigs)
                new_stat = st.selectbox("Update Status", ["Needs Servicing", "Available"])
                notes = st.text_area("Service / Damage Notes (Required)")
                if st.form_submit_button("Update Status"):
                    if not srv_rig: st.error("Submission Failed: Please select a rig.")
                    elif not notes.strip(): st.error("Submission Failed: 'Service / Damage Notes' is required.")
                    else:
                        update_rig(srv_rig, {"status": new_stat, "damage_notes": notes.strip()})
                        log_action(srv_rig, f"Status updated to {new_stat}", "", notes.strip())
                        st.success(f"{srv_rig} status successfully updated to {new_stat}."); safe_rerun()
        else: st.info("No available rigs to report.")

    if is_admin:
        with tabs[4]:
            st.subheader("Exchange History Log")
            if (log_df := db_op('SELECT timestamp as Timestamp, rig_name as "Rig Name", action as Action, assigned_to as "Assigned To", notes as Notes FROM audit_log ORDER BY id DESC', fetch="df")).empty: 
                st.info("No actions have been logged yet.")
            else:
                st.dataframe(log_df, use_container_width=True, hide_index=True)
                c1, c2 = st.columns([2, 1])
                c1.download_button("Download Log CSV", log_df.to_csv(index=False).encode('utf-8'), "audit_log.csv", "text/csv")
                if c2.button("Clear History Log", type="primary"): db_op("DELETE FROM audit_log"); st.success("History log cleared!"); safe_rerun()

except Exception: st.error("An error occurred while running the app:"); st.code(traceback.format_exc())
