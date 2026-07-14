# PDF Annotations → Knowledge Base Sync

Pulls every Xodo highlight/note from PDFs in a Google Drive folder and
pushes them into the central Knowledge Base (same one the Android share
capture feeds into). Runs daily automatically, plus a manual "Run now"
button. Free (GitHub Actions free tier + Google Drive API free tier).

Re-running is safe — same highlight always maps to the same Knowledge Base
entry (no duplicates), so this can run every night without piling up copies.

## One-time setup

### 1. Create a Google Cloud service account (read-only Drive access)
1. Go to [console.cloud.google.com](https://console.cloud.google.com), create
   a project.
2. Enable the **Google Drive API** (APIs & Services → Enable APIs → search
   "Google Drive API" → Enable).
3. **IAM & Admin → Service Accounts → Create Service Account** (any name, no
   roles needed).
4. Open it → **Keys** tab → **Add Key → Create new key → JSON** — downloads
   a `.json` file, you'll paste its contents into a GitHub secret below.
5. Copy the service account's email (`xxxx@xxxx.iam.gserviceaccount.com`).

### 2. Share your exam/PDF Drive folder with the service account
- Open the Drive folder with your PDFs → Share → paste the service account
  email → **Viewer** access is enough (read-only).
- Grab the folder ID from the URL:
  `https://drive.google.com/drive/folders/`**`THIS_PART_IS_THE_ID`**

### 3. Create the GitHub repo and add secrets
1. New repo, e.g. `pdf-kb-sync`, push these files to it.
2. Repo → **Settings → Secrets and variables → Actions → New repository
   secret**, add four:
   - `GOOGLE_SERVICE_ACCOUNT_JSON` — entire contents of the JSON key file
   - `SOURCE_FOLDER_ID` — your PDF folder ID
   - `KB_API_BASE` — your Knowledge Base Worker URL (e.g.
     `https://knowledge-base.jarvismyvpa.workers.dev`)
   - `KB_API_TOKEN` — the same token you set with `wrangler secret put
     API_TOKEN` for the Knowledge Base

### 4. Run it
- **Manual:** repo → Actions tab → "Sync PDF Annotations to Knowledge Base"
  → Run workflow.
- **Automatic:** every day at 00:00 Dhaka time.

## Notes
- Only annotations Xodo has synced back into the PDF on Drive will show up
  — give it a minute after annotating before running.
- Freehand drawings/shapes are skipped (no extractable text).
- Each PDF is downloaded temporarily to the GitHub Actions runner only —
  nothing touches your phone/iPad storage.
