import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# 1. Read the parameters from the URL
query_params = st.query_params

# 2. Check if the URL contains ?admin=secretkey
if query_params.get("admin") == "Hellfire":
    
    # 3. Indent all your admin code here
    st.header("Admin: Add new set to fleet")
    # Your admin logic here

# --- DATABASE SETUP ---
DB_FILE = "inventory.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Create table if it doesn't exist, but do NOT insert any rows
    c.execute('''CREATE TABLE IF NOT EXISTS sets 
                 (id TEXT PRIMARY KEY, status TEXT, location TEXT, assignee TEXT, last_updated TEXT)''')
    conn.commit()
    conn.close()

def get_data():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM sets", conn)
    conn.close()
    return df

def update_set(set_id, status, location, assignee):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE sets SET status=?, location=?, assignee=?, last_updated=? WHERE id=?",
              (status, location, assignee, datetime.now().isoformat(), set_id))
    conn.commit()
    conn.close()

# --- APP UI ---
st.set_page_config(page_title="Set Tracker", layout="wide")
init_db()

st.title("📦 Logistics Control: Set Tracking")
st.markdown("---")

df = get_data()

# Sidebar - Fleet Health
st.sidebar.header("Fleet Metrics")
if not df.empty:
    st.sidebar.metric("Available", len(df[df['status'] == 'Available']))
    st.sidebar.metric("Deployed", len(df[df['status'] == 'Deployed']))
    st.sidebar.metric("Maintenance", len(df[df['status'] == 'Maintenance']))
else:
    st.sidebar.info("Inventory empty.")

# Main Tabs
tab1, tab2, tab3 = st.tabs(["Dashboard", "Check Out", "Check In / Maintenance"])

with tab1:
    st.subheader("Current Fleet Status")
    if df.empty:
        st.info("No hardware registered. Use the Admin section below to add sets.")
    else:
        # UPDATED: Search now includes Assignee
        search = st.text_input("Search by Set ID, Location, or Assignee")
        if search:
            display_df = df[
                df['id'].str.contains(search, case=False, na=False) | 
                df['location'].str.contains(search, case=False, na=False) |
                df['assignee'].str.contains(search, case=False, na=False)
            ]
        else:
            display_df = df
        st.dataframe(display_df, use_container_width=True, hide_index=True)

with tab2:
    st.subheader("Deploy Equipment")
    if not df.empty:
        available = df[df['status'] == 'Available']['id'].tolist()
        if not available:
            st.warning("No sets currently available.")
        else:
            with st.form("checkout_form"):
                selected_set = st.selectbox("Select Set ID", available)
                dest = st.text_input("Destination Location")
                user = st.text_input("Assignee")
                submit = st.form_submit_button("Confirm Deployment")
                
                if submit:
                    if dest and user:
                        update_set(selected_set, "Deployed", dest, user)
                        st.success(f"{selected_set} deployed to {dest}")
                        st.rerun()
                    else:
                        st.error("Please fill in all fields.")
    else:
        st.info("Add hardware first.")

with tab3:
    st.subheader("Return or Flag Equipment")
    if not df.empty:
        deployed = df[df['status'] != 'Available']['id'].tolist()
        if not deployed:
            st.info("All sets are currently at Base.")
        else:
            with st.form("return_form"):
                selected_return = st.selectbox("Select Set ID", deployed)
                action = st.radio("Action", ["Return to Base (Available)", "Flag for Maintenance (T3/Hardware Issue)"])
                submit_return = st.form_submit_button("Update Status")
                
                if submit_return:
                    new_status = "Available" if "Return" in action else "Maintenance"
                    update_set(selected_return, new_status, "Base", "None")
                    st.success(f"{selected_return} updated to {new_status}")
                    st.rerun()
    else:
        st.info("Add hardware first.")

# Admin Section - Add New Hardware
st.markdown("---")
with st.expander("Admin: Add New Set to Fleet"):
    new_id = st.text_input("New Set ID (e.g., Pumice-V2.1-01)")
    if st.button("Add to Inventory"):
        if new_id:
            if new_id not in df['id'].values:
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("INSERT INTO sets VALUES (?, 'Available', 'Base', 'None', ?)", (new_id, datetime.now().isoformat()))
                conn.commit()
                conn.close()
                st.success(f"Added {new_id} to fleet.")
                st.rerun()
            else:
                st.error("Set ID already exists.")
        else:
            st.error("Please enter an ID.")
