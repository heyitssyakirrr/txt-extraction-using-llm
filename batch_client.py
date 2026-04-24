#!/usr/bin/env python3
"""
batch_client.py
---------------
Client for the POST /extract/batch endpoint.

Usage:
    python batch_client.py --url http://localhost:8503/extract/batch \
                           --input-dir ./pdfs \
                           --output results.csv

The script:
  1. Scans --input-dir for .pdf and .txt files
  2. POSTs all files in a single request — server does all the work
  3. Prints timestamped progress lines as each file completes
  4. Downloads the final CSV from the server when done
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

SUPPORTED_EXTENSIONS = {".pdf", ".txt"}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Batch extraction client")
    p.add_argument("--url",       required=True, help="Full URL of /extract/batch endpoint")
    p.add_argument("--input-dir", required=True, help="Directory containing PDF/TXT files")
    p.add_argument("--output",    required=True, help="Output CSV file path")
    return p.parse_args()


def collect_files(input_dir: str) -> list[Path]:
    directory = Path(input_dir)
    if not directory.is_dir():
        print(f"ERROR: {input_dir} is not a directory")
        sys.exit(1)
    files = sorted(
        f for f in directory.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    return files


def timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def run(url: str, file_paths: list[Path], output_path: Path) -> None:
    """
    Send all files to the server. Print timestamped progress.
    Download the CSV when the server signals it is ready.
    """
    download_url: str | None = None
    host = url.split("//")[1].split("/")[0]  # e.g. localhost:8503

    file_handles = [(p.name, p.open("rb")) for p in file_paths]

    try:
        with httpx.stream(
            "POST",
            url,
            files=[
                ("files", (name, fh, "application/octet-stream"))
                for name, fh in file_handles
            ],
            timeout=httpx.Timeout(connect=30.0, write=300.0, read=None, pool=5.0),
        ) as response:
            if response.status_code != 200:
                body = response.read().decode(errors="replace")
                print(f"[{timestamp()}] ERROR: Server returned HTTP {response.status_code}: {body}")
                sys.exit(1)

            for line in response.iter_lines():
                if not line.strip():
                    continue

                if line.startswith("# download:"):
                    download_path = line.replace("# download:", "").strip()
                    download_url = f"http://{host}{download_path}"
                    print(f"[{timestamp()}] CSV ready on server — downloading...")
                elif line.startswith("#"):
                    print(f"[{timestamp()}] {line[2:].strip()}")

    finally:
        for _, fh in file_handles:
            fh.close()

    if download_url is None:
        print(f"[{timestamp()}] ERROR: Server did not return a download URL.")
        sys.exit(1)

    with httpx.stream(
        "GET",
        download_url,
        timeout=httpx.Timeout(connect=30.0, read=60.0),
    ) as dl_response:
        if dl_response.status_code != 200:
            body = dl_response.read().decode(errors="replace")
            print(f"[{timestamp()}] ERROR: Download failed HTTP {dl_response.status_code}: {body}")
            sys.exit(1)

        with output_path.open("wb") as out_fh:
            for chunk in dl_response.iter_bytes(chunk_size=8192):
                out_fh.write(chunk)

    print(f"[{timestamp()}] Saved to {output_path}")


def main() -> None:
    args = parse_args()
    all_files = collect_files(args.input_dir)

    if not all_files:
        print(f"[{timestamp()}] No .pdf or .txt files found in {args.input_dir}")
        sys.exit(0)

    print(f"[{timestamp()}] Found {len(all_files)} file(s) — sending to server...")

    output_path = Path(args.output)
    start = time.monotonic()

    run(args.url, all_files, output_path)

    elapsed = time.monotonic() - start
    print(f"[{timestamp()}] All done in {elapsed:.1f}s")


if __name__ == "__main__":
    main()