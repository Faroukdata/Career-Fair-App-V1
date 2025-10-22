# my_app.py — single-page, autosave (debounced), optimistic UI, direct CV links
# with refresh-token auth + auto-retry on expired access tokens

import io
import time
import pathlib
import pandas as pd
import streamlit as st
import requests, dropbox

# ================== SETTINGS ==================
APP_TITLE        = "CAPGEMINI Career Fair"
PAGE_ICON        = "🎓"

# Read (fast): public shared CSV URL (dl=0 or dl=1, we force dl=1)
STATE_SHARED_CSV_URL = st.secrets.get("STATE_SHARED_CSV_URL_CAPGEMINI")

# Write (API): path inside your Dropbox App Folder
STATE_DBX_PATH  = st.secrets.get("STATE_DBX_PATH_CAPGEMINI")

AUTOSAVE_DEBOUNCE_SEC = 0.35  # coalesce rapid toggles into one write
LOGO_PATH = "images/capgemini.png"
# ==============================================

# ---------- UI boot ----------
st.set_page_config(page_title=APP_TITLE, page_icon=PAGE_ICON, layout="wide")

# CSS (facultatif)
css = pathlib.Path("assets/styles.css")
if css.exists():
    st.markdown(f"<style>{css.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

# En-tête avec logo
lc, rc = st.columns([1, 4])
with lc:
    try:
        st.image(LOGO_PATH, width=140)
    except Exception:
        pass
with rc:
    st.markdown(
        "<h1 class='app-title' style='margin:0'>CAPGEMINI Career Fair</h1>"
        "<p class='app-subtitle'>Search • Direct CV links • Auto-save (debounced)</p>"
        "<hr class='hr-soft'/>",
        unsafe_allow_html=True,
    )

# ---------- Columns ----------
FIRST, LAST, FILE = "first_name","last_name","file_name"   # FILE is a full URL
SEEN, INT, SAVE, CONT = "seen","intend_view","cv_saved","contacted"
BOOL_COLS = [SEEN, INT, SAVE, CONT]
ALL_COLS  = [FIRST, LAST, FILE, *BOOL_COLS]

# ---------- Dropbox auth (access token OR refresh token) ----------
def _access_token_from_refresh() -> str | None:
    """Exchange refresh token -> short-lived access token (about 4h)."""
    s = st.secrets
    need = ("DROPBOX_APP_KEY", "DROPBOX_APP_SECRET", "DROPBOX_REFRESH_TOKEN")
    if not all(k in s for k in need):
        return None
    r = requests.post(
        "https://api.dropbox.com/oauth2/token",
        data={
            "refresh_token": s["DROPBOX_REFRESH_TOKEN"],
            "grant_type": "refresh_token",
            "client_id": s["DROPBOX_APP_KEY"],
            "client_secret": s["DROPBOX_APP_SECRET"],
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["access_token"]

@st.cache_resource(show_spinner=False)
def _build_dbx_client() -> dropbox.Dropbox:
    """
    Build a Dropbox client using:
    1) DROPBOX_ACCESS_TOKEN if present,
    2) otherwise, refresh flow with APP_KEY/SECRET/REFRESH_TOKEN.
    """
    s = st.secrets
    tok = s.get("DROPBOX_ACCESS_TOKEN")
    if not tok:
        tok = _access_token_from_refresh()
    if not tok:
        raise RuntimeError(
            "Dropbox token missing. Provide either DROPBOX_ACCESS_TOKEN "
            "or the trio DROPBOX_APP_KEY, DROPBOX_APP_SECRET, DROPBOX_REFRESH_TOKEN."
        )
    return dropbox.Dropbox(tok)

def _refresh_dbx_client() -> dropbox.Dropbox:
    """Force-refresh client via refresh token (no cache)."""
    tok = _access_token_from_refresh()
    if not tok:
        # If refresh flow not configured, fall back to cached client (may still be valid)
        return _build_dbx_client()
    return dropbox.Dropbox(tok)

# Cached client (will be valid for the session; we also retry on expiration)
DBX = None
dbx_error = None
try:
    DBX = _build_dbx_client()
except Exception as e:
    dbx_error = str(e)

# ---------- Sidebar diag ----------
st.sidebar.subheader("Status")
st.sidebar.write("🔐 Token:", "✅" if DBX else f"❌ {dbx_error or ''}")
st.sidebar.write("📄 CSV (shared link):", "✅" if STATE_SHARED_CSV_URL else "❌")
st.sidebar.write("📝 Write path (App Folder):", STATE_DBX_PATH)
st.sidebar.toggle("Auto-save on change", value=True, key="autosave")

# ---------- Helpers ----------
def _ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in (FIRST, LAST, FILE):
        if c not in df: df[c] = ""
    for c in BOOL_COLS:
        if c not in df:
            df[c] = False
        else:
            ser = df[c].astype(str).str.strip().str.lower()
            df[c] = ser.map({
                "true": True, "1": True, "yes": True, "y": True,
                "false": False, "0": False, "no": False, "n": False
            }).fillna(False).astype(bool)
    return df[[FIRST, LAST, FILE, *BOOL_COLS]]

def _force_dl1(url: str) -> str:
    if not url:
        return url
    # ensure dl=1 so requests.get returns the file bytes (not HTML)
    if "dl=" in url:
        base, _, tail = url.partition("dl=")
        rest = tail.split("&", 1)[1] if "&" in tail else ""
        return base + "dl=1" + (("&" + rest) if rest else "")
    return (url + ("&" if "?" in url else "?") + "dl=1")

@st.cache_data(show_spinner=False, ttl=10)
def fetch_state_df() -> pd.DataFrame:
    url = _force_dl1(STATE_SHARED_CSV_URL)
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    df = pd.read_csv(io.BytesIO(r.content))  # comma-separated CSV
    return _ensure_schema(df)

def _ensure_folder_tree(dbx: dropbox.Dropbox, path: str):
    from posixpath import dirname
    parent = dirname(path.rstrip("/"))
    if not parent or parent == "/":
        return
    try:
        dbx.files_create_folder_v2(parent)
    except dropbox.exceptions.ApiError:
        pass  # exists → ignore

def _upload_with_auto_refresh(data: bytes, path: str) -> tuple[bool, str|None]:
    """
    Try upload; if AuthError expired_access_token/missing_scope appears,
    refresh the client once and retry.
    """
    global DBX
    try:
        _ensure_folder_tree(DBX, path)
        DBX.files_upload(data, path=path, mode=dropbox.files.WriteMode("overwrite"))
        return (True, None)
    except dropbox.exceptions.AuthError as e:
        # Try one refresh if refresh flow is configured
        try:
            DBX = _refresh_dbx_client()
            _ensure_folder_tree(DBX, path)
            DBX.files_upload(data, path=path, mode=dropbox.files.WriteMode("overwrite"))
            return (True, None)
        except Exception as e2:
            return (False, f"AuthError after refresh: {e2}")
    except dropbox.exceptions.ApiError as e:
        return (False, f"ApiError: {e}")
    except Exception as e:
        return (False, f"Write error: {e}")

def write_state_df(full_df: pd.DataFrame) -> tuple[bool, str|None]:
    """Write whole CSV back to the App Folder path (with auto-refresh retry)."""
    if DBX is None:
        return (False, "Dropbox not configured")

    out = _ensure_schema(full_df).copy()
    for c in BOOL_COLS:
        out[c] = out[c].astype(int)  # 0/1 for light CSV

    bio = io.BytesIO()
    out.to_csv(bio, index=False)
    data = bio.getvalue()
    return _upload_with_auto_refresh(data, STATE_DBX_PATH)

def _key(df: pd.DataFrame) -> pd.Series:
    return (
        df[FIRST].fillna("").astype(str).str.strip().str.lower() + "||" +
        df[LAST ].fillna("").astype(str).str.strip().str.lower() + "||" +
        df[FILE ].fillna("").astype(str).str.strip()
    )

# ---------- Load DF in session once ----------
if "df" not in st.session_state:
    try:
        st.session_state.df = fetch_state_df()
    except Exception as e:
        st.error(f"Failed to load CSV from shared link: {e}")
        st.stop()

# Track last save time for debounce
if "last_save_ts" not in st.session_state:
    st.session_state.last_save_ts = 0.0

# ---------- Search (Clear BEFORE creating the input to avoid the Streamlit error) ----------
if "q" not in st.session_state:
    st.session_state.q = ""

cc, ic = st.columns([1, 4])
with cc:
    if st.button("Clear search"):
        st.session_state.q = ""   # équivaut à taper "" + Entrée
        st.rerun()
with ic:
    st.text_input("Search (first/last name)", key="q", placeholder="e.g. Kadri Farouk")

# Filtrage
base_df = st.session_state.df
if st.session_state.q:
    qn = st.session_state.q.strip().lower()
    view_df = base_df[
        base_df[FIRST].fillna("").str.lower().str.contains(qn) |
        base_df[LAST ].fillna("").str.lower().str.contains(qn)
    ].copy()
else:
    view_df = base_df.copy()

total = len(view_df)
if total == 0:
    st.info("No candidates.")
    st.stop()

# ---------- Grid (direct CV links; edit flags only) ----------
st.write("### Candidates")

snap_key = "snapshot_all"
grid_key = "grid_all"

display_df = view_df[[FIRST, LAST, FILE, *BOOL_COLS]].copy()

edited = st.data_editor(
    display_df,
    key=grid_key,  # stable key avoids widget churn
    column_config={
        FIRST: st.column_config.TextColumn("First name", disabled=True),
        LAST:  st.column_config.TextColumn("Last name", disabled=True),
        FILE:  st.column_config.LinkColumn("CV", display_text="Open"),
        SEEN:  st.column_config.CheckboxColumn("Profile viewed"),
        INT:   st.column_config.CheckboxColumn("Interested in viewing profile"),
        SAVE:  st.column_config.CheckboxColumn("CV saved"),
        CONT:  st.column_config.CheckboxColumn("Candidate contacted"),
    },
    hide_index=True,
    use_container_width=True,
    num_rows="fixed",
)

# Current flags on visible rows
curr_flags = edited[[FIRST, LAST, FILE, *BOOL_COLS]].copy()
curr_flags["_k"] = _key(curr_flags)

# Previous snapshot (for diff)
prev_flags = st.session_state.get(snap_key)

def _diff_rows(prev: pd.DataFrame, curr: pd.DataFrame) -> pd.DataFrame:
    if prev is None or prev.empty:
        return pd.DataFrame(columns=curr.columns)
    merged = curr.merge(prev[["_k", *BOOL_COLS]], on="_k", how="left", suffixes=("", "_old"))
    changed = (
        (merged[SEEN] != merged[f"{SEEN}_old"]) |
        (merged[INT]  != merged[f"{INT}_old"])  |
        (merged[SAVE] != merged[f"{SAVE}_old"]) |
        (merged[CONT] != merged[f"{CONT}_old"])
    ).fillna(False)
    return merged.loc[changed, curr.columns]

changed_rows = _diff_rows(prev_flags, curr_flags)

# ---------- Auto-save (debounced) with optimistic UI ----------
if st.session_state.get("autosave", True) and not changed_rows.empty:
    now = time.time()
    if (now - st.session_state.last_save_ts) >= AUTOSAVE_DEBOUNCE_SEC:
        # 1) Optimistic update on full DF
        full = st.session_state.df.copy()
        full["_k"] = _key(full)
        delta = changed_rows[["_k", *BOOL_COLS]].copy()
        full = full.merge(delta, on="_k", how="left", suffixes=("", "_new"))
        for c in BOOL_COLS:
            full[c] = full[f"{c}_new"].combine_first(full[c]).astype(bool)
            if f"{c}_new" in full:
                full.drop(columns=[f"{c}_new"], inplace=True)
        full.drop(columns=["_k"], inplace=True)

        backup = st.session_state.df
        st.session_state.df = full

        ok, err = write_state_df(full)
        st.session_state.last_save_ts = now

        if ok:
            st.toast(f"Saved {len(changed_rows)} change(s) ✅")
            st.session_state[snap_key] = curr_flags.copy()
        else:
            st.session_state.df = backup
            st.error(f"Auto-save failed: {err}")

# Init snapshot on first draw
if snap_key not in st.session_state:
    st.session_state[snap_key] = curr_flags.copy()
