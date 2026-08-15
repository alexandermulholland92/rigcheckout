Here is the updated, complete script. I have added the location column to the database, updated the dashboard to display it to the right of the "Assigned To" column, and added a "Location" input field in the Check Out tab.

You can copy and paste this entire block to replace your current script:

import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

DB_NAME = "inventory.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fleet (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rig_name TEXT UNIQUE,
            status TEXT
        )
    ''')
    
    cursor.execute("PRAGMA table_info(fleet)")
    existing_columns = [col[1] for col in cursor.fetchall()]
    
    if "assigned_to" not in existing_columns:
        cursor.execute("ALTER TABLE fleet ADD COLUMN assigned_to TEXT DEFAULT ''")
    if "location" not in existing_columns:
        cursor.execute("ALTER TABLE fleet ADD COLUMN location TEXT DEFAULT ''")
    if "last_updated" not in existing_columns:
        cursor.execute("ALTER TABLE fleet ADD COLUMN last_updated TEXT DEFAULT ''")
        
    conn.commit()
    conn.close()

def fetch_fleet():
    conn = sqlite3.connect(DB_NAME)
Added location to the right of assigned_to
    df = pd.read_sql_query("SELECT rig_name, status, assigned_to, location, last_updated FROM fleet", conn)
    conn.close()
    return df

def get_rigs_by_status(status):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT rig_name FROM fleet WHERE status=?", (status,))
    rigs = [row[0] for row in cursor.fetchall()]
    conn.close()
    return rigs

def update_rig_state(rig_name, status, assignee, location):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('''
        UPDATE fleet 
        SET status=?, assigned_to=?, location=?, last_updated=? 
        WHERE rig_name=?
    ''', (status, assignee, location, timestamp, rig_name))
    conn.commit()
    conn.close()

def delete_rig(rig_name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM fleet WHERE rig_name=?", (rig_name,))
    conn.commit()
    conn.close()

init_db()

st.title("Rig Checkout List")

tab_dash, tab_checkout, tab_return = st.tabs(["Dashboard", "Check Out", "Return"])

with tab_dash:
    st.subheader("Fleet Status")
    fleet_data = fetch_fleet()
    
    if fleet_data.empty:
        st.info("Fleet uninitialized. Provision hardware via the Admin portal.")
    else:
        edited_df = st.data_editor(
            fleet_data,
            use_container_width=True,
            hide_index=True,
            column_config={
                "rig_name": st.column_config.TextColumn("Rig Name", disabled=True),
                "status": st.column_config.SelectboxColumn(
                    "Status",
                    help="Click to change rig status",
                    options=["Available", "Deployed", "In Maintenance", "Out of Service", "Servicing"],
                    required=True,
                ),
                "assigned_to": st.column_config.TextColumn("Assigned To", disabled=True),
                "location": st.column_config.TextColumn("Location", disabled=True),
                "last_updated": st.column_config.TextColumn("Last Updated", disabled=True),
            }
        )
        
Detect if the status was changed in the UI and update the database
        if not fleet_data.equals(edited_df):
            changed_rows = edited_df[edited_df['status'] != fleet_data['status']]
            for _, row in changed_rows.iterrows():
                assignee = row['assigned_to']
                location = row['location']
                
Clear assignee and location if changing to a non-deployed state
                if row['status'] in ["Available", "In Maintenance", "Out of Service", "Servicing"]:
                    assignee = "" 
                    location = ""
                    
                update_rig_state(row['rig_name'], row['status'], assignee, location)
            
            st.success("Database updated successfully!")
            st.rerun()

with tab_checkout:
    st.subheader("Deploy Hardware")
    available_rigs = get_rigs_by_status("Available")
    
    if available_rigs:
        with st.form("checkout_form"):
            selected_rig = st.selectbox("Select Rig", available_rigs)
            assignee = st.text_input("Assignee Name (e.g., Roshaun, Daniel)")
            location = st.text_input("Location (e.g., Hotel, Farm, Menlo Park)")
            
            if st.form_submit_button("Check Out"):
                if assignee.strip() and location.strip():
                    update_rig_state(selected_rig, "Deployed", assignee.strip(), location.strip())
                    st.success(f"Rig '{selected_rig}' deployed to {assignee} at {location}.")
                    st.rerun()
                else:
                    st.warning("Both Assignee name and Location are required.")
    else:
        st.info("No hardware currently available for deployment.")

with tab_return:
    st.subheader("Return Hardware")
    deployed_rigs = get_rigs_by_status("Deployed")
    
    if deployed_rigs:
        with st.form("return_form"):
            return_rig = st.selectbox("Select Rig", deployed_rigs)
            new_condition = st.selectbox("Return Condition", ["Available", "In Maintenance", "Out of Service", "Servicing"])
            
            if st.form_submit_button("Process Return"):
Clear assignee and location upon return
                update_rig_state(return_rig, new_condition, "", "")
                st.success(f"Rig '{return_rig}' returned. Status updated to {new_condition}.")
                st.rerun()
    else:
        st.info("No hardware currently deployed.")

st.sidebar.header("System Access")
admin_password = st.sidebar.text_input("Admin Key", type="password")

if admin_password == "Hellfire":
    st.sidebar.divider()
    st.sidebar.subheader("Admin Controls")
    
    with st.sidebar.expander("Provision Single Rig"):
        with st.form("add_rig_form", clear_on_submit=True):
            new_rig_name = st.text_input("Rig ID (e.g., Pumice-01)")
            new_status = st.selectbox("Initial Status", ["Available", "In Maintenance", "Deployed", "Out of Service", "Servicing"])
            
            if st.form_submit_button("Add to Fleet"):
                if new_rig_name.strip():
                    try:
                        conn = sqlite3.connect(DB_NAME)
                        cursor = conn.cursor()
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        cursor.execute(
                            "INSERT INTO fleet (rig_name, status, assigned_to, location, last_updated) VALUES (?, ?, ?, ?, ?)", 
                            (new_rig_name.strip(), new_status, "", "", timestamp)
                        )
                        conn.commit()
                        st.success(f"Rig '{new_rig_name}' provisioned.")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Execution halted: Rig ID already exists.")
                    finally:
                        conn.close()
                else:
                    st.warning("Rig ID is required.")

    with st.sidebar.expander("Bulk Import (CSV)"):
        st.caption("Requires a 'rig_name' column. Optional 'status' and 'location' columns.")
        uploaded_file = st.file_uploader("Upload CSV", type=["csv"])
        
        if uploaded_file is not None:
            if st.button("Process Import"):
                try:
                    df_import = pd.read_csv(uploaded_file)
                    if 'rig_name' not in df_import.columns:
                        st.error("Validation failed: CSV must contain a 'rig_name' column.")
                    else:
                        conn = sqlite3.connect(DB_NAME)
                        cursor = conn.cursor()
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        added_count = 0
                        
                        for _, row in df_import.iterrows():
                            r_name = str(row['rig_name']).strip()
                            if not r_name or r_name.lower() == 'nan':
                                continue
                                
                            r_status = "Available"
                            if 'status' in df_import.columns and pd.notna(row['status']):
                                r_status = str(row['status']).strip()
                                
                            r_location = ""
                            if 'location' in df_import.columns and pd.notna(row['location']):
                                r_location = str(row['location']).strip()
                                
                            try:
                                cursor.execute(
                                    "INSERT INTO fleet (rig_name, status, assigned_to, location, last_updated) VALUES (?, ?, ?, ?, ?)", 
                                    (r_name, r_status, "", r_location, timestamp)
                                )
                                added_count += 1
                            except sqlite3.IntegrityError:
                                pass # Skip existing
                        
                        conn.commit()
                        conn.close()
                        st.success(f"Telemetry updated: {added_count} new rigs imported.")
                        st.rerun()
                except Exception as e:
                    st.error(f"Import failed: {e}")

    with st.sidebar.expander("Decommission Hardware"):
        current_fleet = fetch_fleet()
        if not current_fleet.empty:
            with st.form("delete_rig_form"):
                rig_to_delete = st.selectbox("Select Rig to Remove", current_fleet["rig_name"].tolist())
                
                if st.form_submit_button("Delete Rig"):
                    delete_rig(rig_to_delete)
                    st.success(f"Rig '{rig_to_delete}' decommissioned.")
                    st.rerun()
        else:
            st.info("Fleet is empty.")
