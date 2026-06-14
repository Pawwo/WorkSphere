#!/usr/bin/env python3
"""Preview key requirements extraction for a job URL."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.inbox.language_triage import fetch_posting_text_sync
from app.services.scrape.posting_extract import description_for_storage, extract_key_description


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview posting extract for URL")
    parser.add_argument("url", help="Job posting URL")
    parser.add_argument("--portal", default="", help="Portal id (linkedin-pl, pracuj, …)")
    args = parser.parse_args()

    raw = fetch_posting_text_sync(args.url) or ""
    portal = args.portal or ("linkedin-pl" if "linkedin" in args.url.lower() else "")
    extracted = extract_key_description(raw, portal=portal, url=args.url)
    stored = description_for_storage(raw, portal=portal, url=args.url)

    print(f"raw_len={len(raw)} extracted_len={len(extracted)} stored_len={len(stored)}")
    print("--- extracted ---")
    print(extracted or "(empty)")
    print("--- stored (description) ---")
    print(stored or "(empty)")


if __name__ == "__main__":
    main()
