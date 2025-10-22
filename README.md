# HI! PARIS Career Fair — App

An app to browse candidates, open CVs, and mark follow‑up flags. Designed to duplicate per sponsor (“mécène”) with minimal changes.

---

## What it does

- Search candidates by first/last name.
- Open CVs directly from the table (each row has a link).
- Tick flags (Profile viewed / Interested / CV saved / Candidate contacted).
- Saves changes automatically to a CSV in your Dropbox **App Folder**.

It’s optimized for speed: the app **reads** a compact CSV via a **shared link** and **writes** updates via the Dropbox API. The app does not download PDFs—links open in the browser.

---

## Data format (CSV)

One row per candidate:

| Column        | Type   | Notes                                                             |
|--------------|--------|-------------------------------------------------------------------|
| `first_name` | string | Required                                                          |
| `last_name`  | string | Required                                                          |
| `file_name`  | string | **Full URL** to the CV (Dropbox shared link, or any reachable URL) |
| `seen`       | bool   | `0/1`, `true/false`, `yes/no` (missing is treated as `false`)     |
| `intend_view`| bool   | same as above                                                     |
| `cv_saved`   | bool   | same as above                                                     |
| `contacted`  | bool   | same as above                                                     |

> Keep the CSV lean (only these columns) for the best performance.

---

## Quick start (local)

1. **Clone** the repo and `cd` into it.
2. Create `.streamlit/secrets.toml` (see **Secrets** below).
3. (Optional) Put a logo at `images/hi-paris.png` (or per sponsor, e.g. `images/loreal.png`).
4. Install deps and run:
   ```bash
   pip install -r requirements.txt
   streamlit run my_app.py
   ```

> You can test read-only with just the **shared CSV URL**. Writing needs Dropbox secrets.

---

## Streamlit **secrets** (the essentials)

You’ll configure **one pair per sponsor** for the **read URL** (public shared link) and the **write path** (Dropbox App Folder).  
You also provide **Dropbox credentials** so the app can write.

### A) Per-sponsor entries

Example for two sponsors:

```toml
# L'Oréal app
STATE_SHARED_CSV_URL_LOREAL = "https://www.dropbox.com/scl/fi/.../cv_state_full_url_loreal.csv?dl=0"
STATE_DBX_PATH_LOREAL       = "/CV-CarrerFair/loreal/cv_state_full_url.csv"

# Capgemini app
STATE_SHARED_CSV_URL_CAPGEMINI = "https://www.dropbox.com/scl/fi/.../cv_state_full_url_capgemini.csv?dl=0"
STATE_DBX_PATH_CAPGEMINI       = "/CV-CarrerFair/capgemini/cv_state_full_url.csv"
```

In each sponsor app file (e.g. `my_app_loreal.py`), reference the matching keys:

```python
STATE_SHARED_CSV_URL = st.secrets.get("STATE_SHARED_CSV_URL_LOREAL")
STATE_DBX_PATH       = st.secrets.get("STATE_DBX_PATH_LOREAL")
```

- **Read URL** is public and used **only for reading** (fast).
- **Write path** is inside your **Dropbox App Folder** and used for saving.

### B) Dropbox credentials (for writing)

Choose **one** of the two options:

**Option 1 — Access token (simple)**
```toml
DROPBOX_ACCESS_TOKEN = "sl.BC...."  # App must have files.content.write scope
```

**Option 2 — Refresh token (recommended)**
```toml
DROPBOX_APP_KEY = "your_app_key"
DROPBOX_APP_SECRET = "your_app_secret"
DROPBOX_REFRESH_TOKEN = "your_refresh_token"
```

- With the refresh-token setup, the app automatically exchanges it for a short-lived access token when needed (no manual rotation).
- In your Dropbox App Console, enable the **`files.content.write`** (and read) scopes.

---

## Duplicating per sponsor (“mécène”)

1. Copy `my_app.py` → `my_app_<sponsor>.py`.
2. Update:
   - `APP_TITLE`, `LOGO_PATH`
   - `STATE_SHARED_CSV_URL = st.secrets.get("STATE_SHARED_CSV_URL_<SPONSOR>")`
   - `STATE_DBX_PATH       = st.secrets.get("STATE_DBX_PATH_<SPONSOR>")`
3. Deploy that file as a separate Streamlit app.

Each sponsor gets its own CSV & write location.

---

## Deployment notes

- On Streamlit Cloud (or your infra), add all values in the **Secrets** panel (same as the example `.toml`).
- If you see **“missing_scope: files.content.write”**, enable that scope in the Dropbox App Console → Permissions.
- If reading fails, make sure the CSV shared link is public. The app forces `dl=1` to fetch the file bytes (not the HTML page).

---

## Performance tips

- One **CSV** for identity + flags is simplest and fastest.
- Keep rows/columns minimal.
- CVs are not fetched; links just open them—this keeps the UI snappy.
- The app uses **optimistic UI**: your tick shows immediately while it writes in the background. On failure, it reverts and shows an error.

---

## Troubleshooting

- **“Dropbox token missing”**  
  Add either `DROPBOX_ACCESS_TOKEN` **or** the refresh-token trio to secrets.
- **“missing_scope: files.content.write”**  
  Enable that scope in your Dropbox app, then redeploy.
- **No links in the CV column**  
  `file_name` must contain a **full URL** (e.g., a Dropbox shared link per PDF).
- **Saves don’t persist**  
  Check the sidebar status, confirm the write path is inside your Dropbox **App Folder**, and that your app has the correct scopes.

---

## Optional styling

You can tweak the theme via `.streamlit/config.toml` and add CSS in `assets/styles.css`. The app will load them automatically.

---

### Short checklist

- [ ] Create sponsor CSV with required columns
- [ ] Generate a **shared link** for the CSV (read)
- [ ] Put write path inside **Dropbox App Folder**
- [ ] Add Dropbox secrets (access or refresh token flow)
- [ ] Set sponsor-specific secrets keys
- [ ] Deploy `my_app_<sponsor>.py`

That’s it — plug the right URLs/paths into secrets and go!
=======
# Career-Fair-App-V1
HI! PARIS Career Fair — Streamlit Application
