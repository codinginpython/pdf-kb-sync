"""
PDF -> Knowledge Base sync
--------------------------
Scans a Google Drive folder (recursively) for PDFs, extracts every
highlight / underline / sticky-note left in Xodo, and pushes each one into
the central Knowledge Base Worker API (POST /api/highlights).

Re-running this safely UPDATES existing entries instead of duplicating them
(each annotation gets a stable id derived from the PDF + page + content, so
the same highlight always maps to the same Knowledge Base row).

Required environment variables (set as GitHub Actions secrets):
  SOURCE_FOLDER_ID   - Drive folder ID containing your exam/PDF library
  KB_API_BASE        - your Knowledge Base Worker URL, e.g. https://knowledge-base.xxxx.workers.dev
  KB_API_TOKEN       - the token you set with `wrangler secret put API_TOKEN`
  (service_account.json must exist in the working directory)
"""

import io
import os
import uuid
import requests
import fitz  # PyMuPDF
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
SERVICE_ACCOUNT_FILE = "service_account.json"
LOCAL_DOWNLOAD_DIR = "downloaded_pdfs"

ANNOT_TYPES_WITH_HIGHLIGHT_TEXT = {"Highlight", "Underline", "StrikeOut", "Squiggly"}


def get_drive_service():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds)


def list_pdfs_in_folder(service, folder_id):
    pdfs = []
    query = f"'{folder_id}' in parents and trashed = false"
    page_token = None
    while True:
        resp = (
            service.files()
            .list(
                q=query,
                fields="nextPageToken, files(id, name, mimeType, webViewLink)",
                pageToken=page_token,
            )
            .execute()
        )
        for f in resp.get("files", []):
            if f["mimeType"] == "application/vnd.google-apps.folder":
                pdfs.extend(list_pdfs_in_folder(service, f["id"]))
            elif f["mimeType"] == "application/pdf":
                pdfs.append(f)
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return pdfs


def download_file(service, file_id, dest_path):
    request = service.files().get_media(fileId=file_id)
    fh = io.FileIO(dest_path, "wb")
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.close()


def get_highlighted_text(page, annot):
    quad_points = annot.vertices
    if not quad_points:
        return ""
    text_parts = []
    for i in range(0, len(quad_points), 4):
        quad = quad_points[i : i + 4]
        if len(quad) < 4:
            continue
        rect = fitz.Quad(quad).rect
        snippet = page.get_text("text", clip=rect).strip()
        if snippet:
            text_parts.append(snippet)
    return " ".join(text_parts)


def extract_annotations_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    results = []
    for page_index in range(len(doc)):
        page = doc[page_index]
        annots = page.annots()
        if not annots:
            continue
        for annot in annots:
            subtype = annot.type[1]
            info = annot.info or {}
            note_text = (info.get("content") or "").strip()
            highlighted_text = ""
            if subtype in ANNOT_TYPES_WITH_HIGHLIGHT_TEXT:
                highlighted_text = get_highlighted_text(page, annot)
            if not highlighted_text and not note_text:
                continue
            results.append(
                {
                    "page": page_index + 1,
                    "type": subtype,
                    "highlighted_text": highlighted_text,
                    "note": note_text,
                }
            )
    doc.close()
    return results


def stable_id(*parts):
    key = "|".join(str(p) for p in parts)
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


def push_to_kb(kb_base, kb_token, items):
    if not items:
        return
    resp = requests.post(
        kb_base.rstrip("/") + "/api/highlights",
        headers={"Authorization": f"Bearer {kb_token}", "Content-Type": "application/json"},
        json=items,
        timeout=60,
    )
    resp.raise_for_status()
    print(f"  Pushed {len(items)} item(s): {resp.json()}")


def main():
    source_folder_id = os.environ["SOURCE_FOLDER_ID"]
    kb_base = os.environ["KB_API_BASE"]
    kb_token = os.environ["KB_API_TOKEN"]

    os.makedirs(LOCAL_DOWNLOAD_DIR, exist_ok=True)

    service = get_drive_service()

    print("Listing PDFs in source folder...")
    pdfs = list_pdfs_in_folder(service, source_folder_id)
    print(f"Found {len(pdfs)} PDF(s).")

    total_pushed = 0
    for pdf in pdfs:
        local_path = os.path.join(LOCAL_DOWNLOAD_DIR, pdf["id"] + ".pdf")
        print(f"Downloading: {pdf['name']}")
        try:
            download_file(service, pdf["id"], local_path)
        except Exception as e:
            print(f"  Failed to download {pdf['name']}: {e}")
            continue

        try:
            annots = extract_annotations_from_pdf(local_path)
        except Exception as e:
            print(f"  Failed to read annotations from {pdf['name']}: {e}")
            continue
        finally:
            if os.path.exists(local_path):
                os.remove(local_path)

        print(f"  Found {len(annots)} annotation(s).")
        if not annots:
            continue

        items = []
        for a in annots:
            entry_id = stable_id(pdf["id"], a["page"], a["type"], a["highlighted_text"], a["note"])
            items.append(
                {
                    "id": entry_id,
                    "source_type": "pdf",
                    "source_app": "xodo",
                    "title": pdf["name"],
                    "highlighted_text": a["highlighted_text"],
                    "note": a["note"],
                    "location_label": f"Page {a['page']}",
                    "original_link": pdf.get("webViewLink"),
                }
            )

        try:
            push_to_kb(kb_base, kb_token, items)
            total_pushed += len(items)
        except Exception as e:
            print(f"  Failed to push annotations for {pdf['name']}: {e}")

    print(f"Done. Total annotations pushed/updated: {total_pushed}")


if __name__ == "__main__":
    main()
