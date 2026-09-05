"""Rig Checkout System - Streamlit + Postgres tracker for off-site recording rigs."""

import traceback
from contextlib import contextmanager
from datetime import datetime

import pandas as pd
import psycopg2
import psycopg2.extras
import streamlit as st
from psycopg2.pool import ThreadedConnectionPool

YES_NO = ["", "Yes", "No"]
TS_FMT = "%Y-%m-%d %H:%M:%S"

# db column -> display label
COLUMNS = {
    "rig_name": "Rig Name", "status": "Status", "assigned_to": "Assigned To", "location": "Location",
    "last_updated": "Last Updated", "address": "Location Address", "shift_lead": "Shift Lead",
    "lead_number": "Lead Number", "estimated_return": "Estimated Return", "wifi_configured": "Wi-Fi Configured",
    "clothing_shoes": "Appropriate Gear", "batteries_charged": "Batteries Charged", "hotspot_connect": "Hotspot Ready",
    "test_recording": "Test Recording Done", "servsafe_card": "ServSafe Card",
    "sexual_harassment_training": "Harassment Training", "workplace_violence_training": "Violence Training",
    "damage_notes": "Damage Notes", "home_wifi": "Home WiFi", "overnight_charge": "Overnight Charge",
}

# checkout form text inputs: (db key, label, which of the 2 columns)
TEXT_FIELDS = [
    ("assigned_to", "Assignee Name", 0),
    ("location", "Off-Site Location Name", 0),
    ("address", "Off-Site Location Address", 0),
    ("shift_lead", "Shift Lead's Name", 1),
    ("lead_number", "Shift Lead's Phone Number", 1),
]

# required checklist: (db key, form label, short name used in the audit log)
CHECKLIST = [
    ("wifi_configured", "Configured to off-site Wi-Fi?", "Wi-Fi"),
    ("clothing_shoes", "Appropriate clothing/shoes?", "Gear"),
    ("batteries_charged", "2 batteries fully charged?", "Batteries"),
    ("hotspot_connect", "Able to connect on hotspot?", "Hotspot"),
    ("test_recording", "Run test recording (30s)?", "Test Rec"),
    ("servsafe_card", "ServSafe food handler's card?", "ServSafe"),
    ("sexual_harassment_training", "Completed sexual harassment training?", "Harassment Trng"),
    ("workplace_violence_training", "Completed workplace violence training?", "Violence Trng"),
]

YES_NO_LABELS = [COLUMNS[key] for key, _, _ in CHECKLIST] + ["Home WiFi", "Overnight Charge"]

# Every form widget carries an explicit key so its value survives a rerun. These lists are what
# each form wipes after a *successful* submit; a failed submit leaves the entries in place.
CHECKOUT_KEYS = (["co_rig"]
                 + [f"co_{key}" for key, _, _ in TEXT_FIELDS]
                 + [f"co_{key}" for key, _, _ in CHECKLIST]
                 + ["co_home_wifi", "co_overnight", "co_due_date", "co_due_time"])
RETURN_KEYS = ["rt_rig", "rt_notes"]
SERVICE_KEYS = ["sv_rig", "sv_status", "sv_notes"]

# db column -> header in the bulk-import fleet CSV
CSV_MAP = {
    "assigned_to": "Column 1",
    "location": "Off-Site Location Name",
    "address": "Off-Stie Location Address",  # typo matches the source sheet's header
    "shift_lead": "Off-Site Coordinating Shift Lead's Name",
    "lead_number": "Off-Site Coordinating Shift Lead's Number",
    "estimated_return": "Estimated Return",
    "wifi_configured": "Is your rig configured to the off-site Wi-Fi?",
    "clothing_shoes": "Do you have appropriate clothing and shoes?",
    "batteries_charged": "2 batteries (including in rig)- fully charged?",
    "hotspot_connect": "Are you able to connect on hotspot?",
    "test_recording": "Have you run a test recording on hotspot  (30 seconds)?",
    "servsafe_card": "Do you have a ServSafe food handler's card?",
    "sexual_harassment_training": "Have you completed sexual harassment training?",
    "workplace_violence_training": "Have you completed workplace violence training?",
    "damage_notes": "Is there any damage to the rig and if so what is it?",
    "home_wifi": "Do you have reliable WiFi/Ethernet at home?",
    "overnight_charge": "Can you plug in your rig to charge and upload overnight?",
}

AUDIT_COLS = ["timestamp", "rig_name", "action", "assigned_to", "notes"]
AUDIT_ALIASES = {
    "timestamp": "timestamp", "date": "timestamp",
    "rig name": "rig_name", "rig": "rig_name", "rig id": "rig_name",
    "action": "action", "status": "action",
    "assigned to": "assigned_to", "inspector name": "assigned_to", "operator": "assigned_to",
    "notes": "notes", "remarks": "notes",
}


# --- database connection ---------------------------------------------------
def db_url():
    """Read the Neon connection string out of Streamlit secrets."""
    try:
        return st.secrets["connections"]["rigs"]["url"]
    except Exception:
        st.error(
            "No database connection is configured.\n\n"
            "Open this app on share.streamlit.io, go to Settings -> Secrets, "
            "and add these two lines:\n\n"
            '[connections.rigs]\n'
            'url = "postgresql://...your Neon connection string..."'
        )
        st.stop()


@st.cache_resource
def pool():
    """One shared pool of connections for the whole app, opened lazily."""
    return ThreadedConnectionPool(1, 5, dsn=db_url(), connect_timeout=10)


def reset_pool():
    """Throw away the pool so the next call opens fresh connections."""
    try:
        pool().closeall()
    except Exception:
        pass
    pool.clear()


@contextmanager
def borrow():
    connections = pool()
    conn = connections.getconn()
    broken = False
    try:
        yield conn
    except (psycopg2.OperationalError, psycopg2.InterfaceError):
        broken = True
        raise
    except Exception:
        try:
            conn.rollback()
        except Exception:
            broken = True
        raise
    finally:
        try:
            connections.putconn(conn, close=broken)
        except Exception:
            pass


def run(work, retry=True):
    """Run `work(cursor)` inside a transaction, retrying once on a dead socket.

    Neon suspends the database after a few minutes of no traffic, which quietly
    kills any connection we were holding. The retry re-opens and tries again so
    the first person to touch the app after a quiet spell doesn't see an error.
    """
    try:
        with borrow() as conn:
            with conn.cursor() as cur:
                result = work(cur)
            conn.commit()
            return result
    except (psycopg2.OperationalError, psycopg2.InterfaceError):
        if not retry:
            raise
        reset_pool()
        return run(work, retry=False)


def db_op(query, params=(), fetch=None):
    """Run one statement. fetch: None, 'all' for rows, or 'df' for a DataFrame."""
    def work(cur):
        cur.execute(query, params)
        if fetch == "df":
            return pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])
        if fetch == "all":
            return cur.fetchall()
        return None
    return run(work)


def db_many(query, rows):
    """Run the same statement over many rows in batches - much faster remotely."""
    if not rows:
        return
    run(lambda cur: psycopg2.extras.execute_batch(cur, query, rows, page_size=100))


# --- helpers ---------------------------------------------------------------
def quoted(cols):
    return ", ".join(f'"{c}"' for c in cols)


def now():
    return datetime.now().strftime(TS_FMT)


def clean(value):
    """Coerce a cell to a plain string. Postgres rejects numpy/NaN values."""
    try:
        if value is None or pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)


def safe_rerun():
    rerun = getattr(st, "rerun", None) or getattr(st, "experimental_rerun", None)
    if rerun:
        rerun()


def flash(message):
    """Queue a success message, then rerun so it shows on the fresh page."""
    st.session_state.flash_message = message
    safe_rerun()


def clear_form_fields(flag, keys):
    """Blank a form's widgets if its last submit succeeded.

    Streamlit won't let us reset a widget's stored value once the widget has been drawn, so a
    successful submit only raises `flag` and reruns. This runs at the top of the tab, before the
    widgets exist, and drops their values so they come back at their defaults. A failed submit
    never raises the flag, so what the user typed is still there to correct.
    """
    if st.session_state.pop(flag, False):
        for key in keys:
            st.session_state.pop(key, None)


def prune_stale_choice(key, options):
    """Forget a remembered selection whose option has since disappeared.

    The rig lists come from the database on every rerun, so a rig held in a selectbox can be
    deployed or serviced by someone else in the meantime. Streamlit raises if a stored value is
    missing from the options, so drop it and let the selectbox fall back to its default.
    """
    if key in st.session_state and st.session_state[key] not in options:
        del st.session_state[key]


def fleet_columns():
    rows = db_op("SELECT column_name FROM information_schema.columns "
                 "WHERE table_schema = current_schema() AND table_name = 'fleet'", fetch="all")
    return [r[0] for r in rows]


@st.cache_resource
def init_db():
    """Create the tables if they don't exist. Cached so it runs once, not every click."""
    db_op("CREATE TABLE IF NOT EXISTS fleet (id SERIAL PRIMARY KEY, "
          "rig_name TEXT UNIQUE, status TEXT DEFAULT 'Available')")
    existing = fleet_columns()
    for col in (c for c in COLUMNS if c not in existing):
        db_op(f"""ALTER TABLE fleet ADD COLUMN IF NOT EXISTS "{col}" TEXT DEFAULT ''""")
    db_op('CREATE TABLE IF NOT EXISTS audit_log (id SERIAL PRIMARY KEY, '
          '"timestamp" TEXT, rig_name TEXT, action TEXT, assigned_to TEXT, notes TEXT)')
    return True


def log_action(rig, action, assigned="", notes="", timestamp=None):
    db_op('INSERT INTO audit_log ("timestamp", rig_name, action, assigned_to, notes) '
          "VALUES (%s,%s,%s,%s,%s)",
          (timestamp or now(), rig, action, assigned, notes))


def fetch_fleet():
    df = db_op(f"SELECT {quoted(COLUMNS)} FROM fleet ORDER BY rig_name", fetch="df")
    for col in COLUMNS:
        if col not in df:
            df[col] = ""
    return df.fillna("")


def update_rig(rig, data):
    data = {k: clean(v) for k, v in data.items()}
    data.setdefault("last_updated", now())
    assignments = ", ".join(f'"{k}"=%s' for k in data)
    db_op(f"UPDATE fleet SET {assignments} WHERE rig_name=%s", [*data.values(), rig])


def rig_names(where=""):
    clause = f" WHERE {where}" if where else ""
    return [r[0] for r in db_op(f"SELECT rig_name FROM fleet{clause} ORDER BY rig_name", fetch="all")]


def cell(row, header):
    value = row.get(header, "")
    return str(value).strip() if pd.notna(value) else ""


# --- admin sidebar ---------------------------------------------------------
def import_fleet_csv(upload):
    df_in = pd.read_csv(upload).loc[:, lambda d: ~d.columns.duplicated()]
    name_col = "Rig Name" if "Rig Name" in df_in.columns else df_in.columns[0]

    rows, cols = [], None
    for _, row in df_in.iterrows():
        rig = str(row.get(name_col, "")).strip()
        if not rig or rig.lower() == "nan":
            continue
        payload = {"status": "Available", **{k: cell(row, header) for k, header in CSV_MAP.items()},
                   "last_updated": now()}
        cols = ["rig_name", *payload]
        rows.append([rig, *payload.values()])

    if not rows:
        st.warning("No rigs found in that CSV. Check that the first column holds rig names.")
        return

    placeholders = ",".join(["%s"] * len(cols))
    updates = ", ".join(f'"{c}"=EXCLUDED."{c}"' for c in cols if c != "rig_name")
    db_many(f"INSERT INTO fleet ({quoted(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT (rig_name) DO UPDATE SET {updates}", rows)

    log_action("Bulk Import", f"CSV processed, {len(rows)} rigs imported")
    flash(f"Successfully imported {len(rows)} rigs.")


def admin_sidebar():
    """Render the password gate plus admin tools. Returns True when unlocked."""
    st.sidebar.header("System Access")
    password = st.secrets.get("ADMIN_PASSWORD", "")
    is_admin = bool(password) and st.sidebar.text_input("Admin Key", type="password") == password
    st.session_state.sidebar_state = "expanded" if is_admin else "collapsed"
    if not is_admin:
        return False

    st.sidebar.divider()
    st.sidebar.subheader("Admin Controls")

    with st.sidebar.expander("Add Single Rig"):
        new_rig = st.text_input("New Rig Name").strip()
        if st.button("Add Rig") and new_rig:
            try:
                db_op("INSERT INTO fleet (rig_name, status) VALUES (%s, 'Available')", (new_rig,))
            except psycopg2.IntegrityError:
                st.sidebar.error("Rig already exists.")
            else:
                log_action(new_rig, "Rig Added to Database")
                flash(f"Added {new_rig} to inventory.")

    with st.sidebar.expander("Delete Rig"):
        all_rigs = rig_names()
        if not all_rigs:
            st.sidebar.info("No rigs in database.")
        else:
            del_rig = st.selectbox("Select Rig to Delete", all_rigs)
            if st.button("Delete Rig"):
                db_op("DELETE FROM fleet WHERE rig_name=%s", (del_rig,))
                log_action(del_rig, "Rig Deleted from Database")
                flash(f"Deleted {del_rig} from inventory.")

    with st.sidebar.expander("Bulk Import CSV"):
        upload = st.file_uploader("Upload CSV Sheet", type=["csv"])
        if upload and st.button("Process Import"):
            import_fleet_csv(upload)

    with st.sidebar.expander("Export CSV"):
        fleet_df = fetch_fleet()
        if fleet_df.empty:
            st.sidebar.info("Database empty.")
        else:
            st.download_button("Download Full Fleet CSV",
                               fleet_df.rename(columns=COLUMNS).to_csv(index=False).encode("utf-8"),
                               "fleet_export.csv", "text/csv")
    return True


# --- tabs ------------------------------------------------------------------
def checkout_tab():
    st.subheader("Deploy Hardware")
    clear_form_fields("checkout_submitted", CHECKOUT_KEYS)
    available = rig_names("status='Available'")
    if not available:
        st.info("No rigs currently available in the system. "
                "Use the Admin controls to add hardware or import your CSV list.")
        return

    rig_options = [""] + available
    prune_stale_choice("co_rig", rig_options)

    with st.form("checkout_form"):
        st.caption("Please fill out all required text fields and checklist items to deploy a rig.")
        rig = st.selectbox("Select Rig", rig_options, key="co_rig")

        cols = st.columns(2)
        texts = {key: cols[i].text_input(label, key=f"co_{key}") for key, label, i in TEXT_FIELDS}

        st.write("---")
        st.caption("Safety & Technical Checklist (Required)")
        cols = st.columns(3)
        checks = {key: cols[i % 3].selectbox(label, YES_NO, key=f"co_{key}")
                  for i, (key, label, _) in enumerate(CHECKLIST)}

        st.write("---")
        st.caption("Additional Details & Timing (Optional)")
        left, right = st.columns(2)
        home_wifi = left.selectbox("Reliable WiFi/Ethernet at home?", YES_NO, key="co_home_wifi")
        overnight = right.selectbox("Can charge/upload overnight?", YES_NO, key="co_overnight")

        date_col, time_col = st.columns(2)
        due_date = date_col.date_input("Estimated Return Date", value=None, key="co_due_date")
        due_time = time_col.time_input("Estimated Return Time", value=None, key="co_due_time")

        if not st.form_submit_button("Check Out"):
            return

    missing_text = [label for key, label, _ in TEXT_FIELDS if not texts[key].strip()]
    missing_checks = [label for key, label, _ in CHECKLIST if not checks[key]]
    problems = []
    if not rig:
        problems.append("Please select a rig to deploy.")
    if missing_text:
        problems.append(f"The following text fields are required: {', '.join(missing_text)}")
    if missing_checks:
        problems.append("Please select an option for the following checklist questions: "
                        f"{', '.join(missing_checks)}")
    if problems:
        # Everything already entered is still in the form above, so list every problem at once.
        st.error("Submission Failed:\n" + "\n".join(f"- {problem}" for problem in problems))
        return

    eta = " at ".join(part for part in (due_date.strftime("%Y-%m-%d") if due_date else "",
                                        due_time.strftime("%I:%M %p") if due_time else "") if part)
    payload = {"status": "Deployed", "estimated_return": eta, "home_wifi": home_wifi,
               "overnight_charge": overnight, **texts, **checks}
    notes = (f"Location: {payload['location']} | Address: {payload['address']} | "
             f"Lead: {payload['shift_lead']} ({payload['lead_number']}) | Est. Return: {eta or 'N/A'}\n"
             "Checklist Answers: "
             + ", ".join(f"{short} ({checks[key]})" for key, _, short in CHECKLIST) + "\n"
             f"Optional Info: Home Wi-Fi ({home_wifi or 'N/A'}), Overnight Chg ({overnight or 'N/A'})")

    update_rig(rig, payload)
    log_action(rig, "Deployed", payload["assigned_to"], notes)
    st.session_state.checkout_submitted = True
    flash(f"🎉 **{rig}** was successfully deployed to **{payload['assigned_to']}**!"
          + (f" (Expected Return: {eta})" if eta else ""))


def dashboard_tab(is_admin):
    st.subheader("Fleet Status")
    df = fetch_fleet()
    if df.empty:
        st.info("Fleet is empty. Use the sidebar Admin controls to import your device list CSV.")
        return

    display = df.rename(columns=COLUMNS)
    if not is_admin:
        st.dataframe(display[["Rig Name", "Status", "Assigned To", "Location", "Estimated Return", "Last Updated"]],
                     use_container_width=True, hide_index=True)
        return

    st.info("Admin Mode Active: All fields and columns are visible and editable.")
    config = {"Status": st.column_config.SelectboxColumn(
        "Status", options=["Available", "Deployed", "Needs Servicing"], required=True)}
    config.update({label: st.column_config.SelectboxColumn(options=["Yes", "No", ""]) for label in YES_NO_LABELS})

    edited = st.data_editor(display, use_container_width=True, hide_index=True,
                            disabled=["Rig Name", "Last Updated"], column_config=config)
    if display.equals(edited):
        return

    for i, row in edited.rename(columns={v: k for k, v in COLUMNS.items()}).iterrows():
        if not row.equals(df.iloc[i]):
            update_rig(row["rig_name"], row.drop(["rig_name", "last_updated"]).to_dict())
            log_action(row["rig_name"], f"Admin Table Edit -> Status: {row['status']}", row["assigned_to"])
    flash("Database updated successfully!")


def return_tab():
    st.subheader("Return Hardware")
    clear_form_fields("return_submitted", RETURN_KEYS)
    deployed = rig_names("status='Deployed'")
    if not deployed:
        st.info("No rigs are currently marked as deployed.")
        return

    prune_stale_choice("rt_rig", deployed)

    with st.form("return_form"):
        rig = st.selectbox("Select Rig to Return", deployed, key="rt_rig")
        notes = st.text_area("Return Notes / Damage Report (Optional)", key="rt_notes")
        if st.form_submit_button("Return Rig"):
            cleared = {k: "" for k in COLUMNS if k not in ("rig_name", "last_updated")}
            update_rig(rig, {**cleared, "status": "Available", "damage_notes": notes})
            log_action(rig, "Returned", "", notes)
            st.session_state.return_submitted = True
            flash(f"✅ **{rig}** has been returned and is now Available.")


def servicing_tab():
    st.subheader("Mark Rig for Servicing")
    st.write("Use this section to flag an available rig that needs maintenance, "
             "or mark a serviced rig as available again.")
    clear_form_fields("service_submitted", SERVICE_KEYS)
    rigs = rig_names("status IN ('Available', 'Needs Servicing')")
    if not rigs:
        st.info("No available rigs to report.")
        return

    rig_options = [""] + rigs
    prune_stale_choice("sv_rig", rig_options)

    with st.form("service_form"):
        rig = st.selectbox("Select Rig", rig_options, key="sv_rig")
        status = st.selectbox("Update Status", ["Needs Servicing", "Available"], key="sv_status")
        notes = st.text_area("Service / Damage Notes (Required)", key="sv_notes")
        if st.form_submit_button("Update Status"):
            problems = []
            if not rig:
                problems.append("Please select a rig.")
            if not notes.strip():
                problems.append("'Service / Damage Notes' is required.")
            if problems:
                st.error("Submission Failed:\n" + "\n".join(f"- {problem}" for problem in problems))
            else:
                update_rig(rig, {"status": status, "damage_notes": notes.strip()})
                log_action(rig, f"Status updated to {status}", "", notes.strip())
                st.session_state.service_submitted = True
                flash(f"✅ **{rig}** status successfully updated to **{status}**.")


def status_from_action(action):
    """Infer a fleet status from a free-text audit action, or None."""
    if "Deployed" in action:
        return "Deployed"
    if any(k in action for k in ("Returned", "Available", "Added")):
        return "Available"
    if any(k in action for k in ("Needs Servicing", "Maintenance")):
        return "Needs Servicing"
    return None


def import_audit_csv(upload):
    audit = pd.read_csv(upload)
    audit.columns = [str(c).strip().lower() for c in audit.columns]
    audit = audit.rename(columns=AUDIT_ALIASES)
    for col in AUDIT_COLS:
        if col not in audit.columns:
            audit[col] = ""
    audit = audit[AUDIT_COLS].fillna("").sort_values("timestamp")

    log_rows, latest = [], {}
    for _, row in audit.iterrows():
        rig = str(row["rig_name"]).strip()
        if not rig:
            continue
        timestamp, action, assigned, notes = (str(row[c]) for c in AUDIT_COLS[:1] + AUDIT_COLS[2:])
        log_rows.append((timestamp, rig, action, assigned, notes))

        status = status_from_action(action)
        if status:
            # rows are in timestamp order, so the last one wins
            latest[rig] = (status, "" if status == "Available" else assigned, timestamp)

    db_many('INSERT INTO audit_log ("timestamp", rig_name, action, assigned_to, notes) '
            "VALUES (%s,%s,%s,%s,%s)", log_rows)

    if latest:
        db_many("INSERT INTO fleet (rig_name, status) VALUES (%s, 'Available') "
                "ON CONFLICT (rig_name) DO NOTHING", [(rig,) for rig in latest])
        db_many('UPDATE fleet SET status=%s, assigned_to=%s, last_updated=%s WHERE rig_name=%s',
                [(status, assigned, timestamp, rig)
                 for rig, (status, assigned, timestamp) in latest.items()])

    rigs = {row[1] for row in log_rows}
    flash(f"Successfully imported {len(log_rows)} records and synced {len(rigs)} rigs!")


def history_tab():
    st.subheader("Exchange History Log")

    with st.expander("📥 Import History Log & Update Dashboard (audit_log.csv)"):
        upload = st.file_uploader("Upload your audit_log.csv file", type=["csv"])
        if upload is not None and st.button("Process & Sync"):
            try:
                import_audit_csv(upload)
            except Exception as err:
                st.error(f"Error reading CSV file: {err}")

    log_df = db_op('SELECT "timestamp" AS "Timestamp", rig_name AS "Rig Name", action AS "Action", '
                   'assigned_to AS "Assigned To", notes AS "Notes" FROM audit_log ORDER BY id DESC',
                   fetch="df")
    if log_df.empty:
        st.info("No actions have been logged yet.")
        return

    st.dataframe(log_df, use_container_width=True, hide_index=True)
    left, right = st.columns([2, 1])
    left.download_button("Download Log CSV", log_df.to_csv(index=False).encode("utf-8"),
                         "audit_log.csv", "text/csv")
    if right.button("Clear History Log", type="primary"):
        db_op("DELETE FROM audit_log")
        flash("History log cleared!")


# --- app -------------------------------------------------------------------
def main():
    init_db()
    st.title("Rig Checkout List")
    if "flash_message" in st.session_state:
        st.success(st.session_state.pop("flash_message"))

    is_admin = admin_sidebar()
    tabs = st.tabs(["Check Out", "Dashboard", "Return", "Needs Servicing"]
                   + (["History Log"] if is_admin else []))
    with tabs[0]:
        checkout_tab()
    with tabs[1]:
        dashboard_tab(is_admin)
    with tabs[2]:
        return_tab()
    with tabs[3]:
        servicing_tab()
    if is_admin:
        with tabs[4]:
            history_tab()


st.session_state.setdefault("sidebar_state", "collapsed")
st.set_page_config(page_title="Rig Checkout System", layout="wide",
                   initial_sidebar_state=st.session_state.sidebar_state)

try:
    main()
except Exception:
    st.error("An error occurred while running the app:")
    st.code(traceback.format_exc())
