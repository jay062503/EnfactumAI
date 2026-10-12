#!/usr/bin/env python3
"""Bulk-upload a folder of company documents into the assistant's knowledge base.

Examples
  # every file visible to all employees
  python scripts/ingest_folder.py ./policies --url http://localhost:8080 --token $OS_TOKEN

  # HR-only folder
  python scripts/ingest_folder.py ./hr --roles hr_manager,super_admin --token $OS_TOKEN

  # local demo mode (no token needed)
  python scripts/ingest_folder.py ./samples

The token must belong to an employee with the PERM_DOCUMENTS_MANAGE permission. Uploads go through the
normal API, so the same validation, permission checks and audit logging apply. Run it from cron / CI to keep
the knowledge base in sync with an exported SharePoint / Google Drive / Confluence folder.
"""
import argparse
import sys
from pathlib import Path

import httpx

EXTENSIONS = {".pdf", ".docx", ".pptx", ".txt", ".md", ".markdown", ".csv", ".json", ".html", ".htm", ".xlsx", ".log",
              ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}  # images are OCR'd by the server


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", type=Path)
    ap.add_argument("--url", default="http://localhost:8080")
    ap.add_argument("--token", default="", help="Enfactum OS bearer token (not needed in demo mode)")
    ap.add_argument("--roles", default="", help="Comma-separated roles; omit to share with all employees")
    ap.add_argument("--skip-existing", action="store_true", help="Skip files whose name is already indexed")
    args = ap.parse_args()

    headers = {"Authorization": f"Bearer {args.token}"} if args.token else {}
    files = sorted(p for p in args.folder.rglob("*") if p.is_file() and p.suffix.lower() in EXTENSIONS)
    if not files:
        print("No supported files found.")
        return 1
    with httpx.Client(base_url=args.url, headers=headers, timeout=300) as client:
        existing = set()
        if args.skip_existing:
            r = client.get("/api/documents")
            r.raise_for_status()
            existing = {d["filename"] for d in r.json()["documents"]}
        ok = failed = 0
        for path in files:
            if path.name in existing:
                print(f"skip  {path}")
                continue
            data = {"visibility": "restricted" if args.roles else "all", "roles": args.roles,
                    "title": path.stem.replace("_", " ").replace("-", " ")}
            with path.open("rb") as fh:
                r = client.post("/api/documents", data=data, files={"file": (path.name, fh)})
            if r.status_code == 200:
                ok += 1
                print(f"ok    {path}  ({r.json()['chunks']} sections)")
            else:
                failed += 1
                print(f"FAIL  {path}  {r.status_code} {r.text[:200]}")
    print(f"\n{ok} indexed, {failed} failed")
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
