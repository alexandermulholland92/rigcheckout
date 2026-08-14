import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

DB_NAME = "inventory.db"

# ==========================================
# 1. DATABASE ORCHESTRATION
# ==========================================
def init_db():
    """Initializes the schema and runs migrations if columns are missing."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. Ensure base table exists
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fleet (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rig_name TEXT UNIQUE,
            status TEXT
        )
    ''')
    
    # 2. Inspect existing columns
    cursor.execute("PRAGMA table_info(fleet)")
    existing_columns = [col[1] for col in cursor.fetchall()]
    
    # 3. Migrate missing columns
    if "assigned_to" not in existing_columns:
        cursor.execute("ALTER TABLE fleet ADD COLUMN assigned_to TEXT DEFAULT ''")
    if "last_updated" not in existing_columns:
        cursor.execute("ALTER TABLE fleet ADD COLUMN last_updated TEXT DEFAULT ''")
        
    conn.commit()
    conn.close()

def fetch_fleet():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT rig_name, status, assigned_to, last_updated FROM fleet", conn)
    conn.close()
    return df

def get_rigs_by_status(status):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT rig_name FROM fleet WHERE status=?", (status,))
    rigs = [row[0] for row in cursor.fetchall()]
    conn.close()
    return rigs

def update_rig_state(rig_name, status, assignee):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('''
        UPDATE fleet 
        SET status=?, assigned_to=?, last_updated=? 
        WHERE rig_name=?
    ''', (status, assignee, timestamp, rig_name))
    conn.commit()
    conn.close()

# Execute schema check on startup
init_db()

# ==========================================
# 2. OPERATIONAL INTERFACE
# ==========================================
st.title("Pumice Hardware Telemetry")

tab_dash, tab_checkout, tab_return = st.tabs(["Dashboard", "Check Out", "Return"])

with tab_dash:
    st.subheader("Fleet Status")
    fleet_data = fetch_fleet()
    if fleet_data.empty:
        st.info("Fleet uninitialized. Provision hardware via the Admin portal.")
    else:
        st.dataframe(fleet_data, use_container_width=True, hide_index=True)

with tab_checkout:
    st.subheader("Deploy Hardware")
    available_rigs = get_rigs_by_status("Available")
    
    if available_rigs:
        with st.form("checkout_form"):
            selected_rig = st.selectbox("Select Rig", available_rigs)
            assignee = st.text_input("Assignee Name (e.g., Roshaun, Daniel)")
            
            if st.form_submit_button("Check Out"):
                if assignee.strip():
                    update_rig_state(selected_rig, "Deployed", assignee.strip())
                    st.success(f"Rig '{selected_rig}' deployed to {assignee}.")
                    st.rerun()
                else:
                    st.warning("Assignee name is required.")
    else:
        st.info("No hardware currently available for deployment.")

with tab_return:
    st.subheader("Return Hardware")
    deployed_rigs = get_rigs_by_status("Deployed")
    
    if deployed_rigs:
        with st.form("return_form"):
            return_rig = st.selectbox("Select Rig", deployed_rigs)
            new_condition = st.selectbox("Return Condition", ["Available", "In Maintenance"])
            
            if st.form_submit_button("Process Return"):
                update_rig_state(return_rig, new_condition, "")
                st.success(f"Rig '{return_rig}' returned. Status updated to {new_condition}.")
                st.rerun()
    else:
        st.info("No hardware currently deployed.")

# ==========================================
# 3. GATED ADMIN MODULE
# ==========================================
st.sidebar.header("System Access")
admin_password = st.sidebar.text_input("Admin Key", type="password")

if admin_password == "Hellfire":
    st.sidebar.divider()
    st.sidebar.subheader("Provision New Hardware")
    
    with st.sidebar.form("add_rig_form", clear_on_submit=True):
        new_rig_name = st.text_input("Rig ID (e.g., Pumice-01)")
        new_status = st.selectbox("Initial Status", ["Available", "In Maintenance", "Deployed"])
        
        if st.form_submit_button("Add to Fleet"):
            if new_rig_name.strip():
                try:
                    conn = sqlite3.connect(DB_NAME)
                    cursor = conn.cursor()
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    cursor.execute(
                        "INSERT INTO fleet (rig_name, status, assigned_to, last_updated) VALUES (?, ?, ?, ?)", 
                        (new_rig_name.strip(), new_status, "", timestamp)
                    )
                    conn.commit()
                    st.sidebar.success(f"Rig '{new_rig_name}' provisioned.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.sidebar.error("Execution halted: Rig ID already exists.")
                finally:
                    conn.close()
            else:
                st.sidebar.warning("Rig ID is required.")
