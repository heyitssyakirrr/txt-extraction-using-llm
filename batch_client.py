#!/usr/bin/env python3
"""
batch_client.py
---------------
Example client for the POST /extract/batch endpoint.

Usage:
    python batch_client.py --url http://0.0.0.0:8503/extract/batch \
                           --input-dir ./pdfs \
                           --output results.csv \
                           --chunk-size 50

The script:
  1. Scans --input-dir for .pdf and .txt files
  2. Splits them into chunks of --chunk-size
  3. POSTs each chunk to the endpoint
  4. Writes data rows to --output (CSV)
  5. Prints # progress lines to stderr so you can watch progress live

Redirect stderr to a log file if you want to keep both:
    python batch_client.py ... > results.csv 2> run.log
    (or just let the script write the CSV file as shown above)
"""

import argparse
import sys
import time
from pathlib import Path

import httpx

SUPPORTED_EXTENSIONS = {".pdf", ".txt"}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Batch extraction client")
    p.add_argument("--url",        required=True,  help="Full URL of /extract/batch endpoint")
    p.add_argument("--input-dir",  required=True,  help="Directory containing PDF/TXT files")
    p.add_argument("--output",     required=True,  help="Output CSV file path")
    p.add_argument("--chunk-size", type=int, default=50, help="Files per request (default: 50)")
    p.add_argument("--timeout",    type=int, default=7200, help="Per-request timeout seconds (default: 7200)")
    return p.parse_args()


def collect_files(input_dir: str) -> list[Path]:
    directory = Path(input_dir)
    if not directory.is_dir():
        print(f"ERROR: {input_dir} is not a directory", file=sys.stderr)
        sys.exit(1)
    files = sorted(
        f for f in directory.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    return files


def chunk(lst: list, size: int):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


def send_chunk(
    url: str,
    file_paths: list[Path],
    timeout: int,
) -> list[str]:
    """
    Send one chunk of files to the endpoint.
    Returns a list of CSV data lines (excludes # comment lines).
    Prints # comment lines to stderr for live terminal progress.
    """
    data_lines: list[str] = []

    # Open all files for this chunk and send as multipart
    file_handles = [(p.name, p.open("rb")) for p in file_paths]

    try:
        with httpx.stream(
            "POST",
            url,
            headers={"X-API-Key": api_key},
            files=[("files", (name, fh, "application/octet-stream")) for name, fh in file_handles],
            timeout=timeout,
        ) as response:
            if response.status_code != 200:
                body = response.read().decode(errors="replace")
                print(
                    f"ERROR: Server returned HTTP {response.status_code}: {body}",
                    file=sys.stderr,
                )
                return []

            for line in response.iter_lines():
                if line.startswith("#"):
                    print(line, file=sys.stderr)
                elif line.strip():
                    data_lines.append(line)

    finally:
        for _, fh in file_handles:
            fh.close()

    return data_lines


def main() -> None:
    args = parse_args()
    all_files = collect_files(args.input_dir)

    if not all_files:
        print(f"No .pdf or .txt files found in {args.input_dir}", file=sys.stderr)
        sys.exit(0)

    total_files = len(all_files)
    chunks = list(chunk(all_files, args.chunk_size))
    total_chunks = len(chunks)

    print(
        f"# Found {total_files} file(s) — "
        f"{total_chunks} chunk(s) of up to {args.chunk_size}",
        file=sys.stderr,
    )

    output_path = Path(args.output)
    header_written = False
    grand_start = time.monotonic()

    with output_path.open("w", encoding="utf-8", newline="") as out_fh:
        for chunk_index, file_chunk in enumerate(chunks, start=1):
            print(
                f"# Sending chunk {chunk_index}/{total_chunks} "
                f"({len(file_chunk)} files)...",
                file=sys.stderr,
            )

            lines = send_chunk(args.url, file_chunk, args.timeout)

            for line in lines:
                # First data line from first chunk is the CSV header
                if not header_written:
                    out_fh.write(line + "\n")
                    header_written = True
                else:
                    # Skip repeated headers from subsequent chunks
                    if not line.startswith("filename,"):
                        out_fh.write(line + "\n")

            # Flush after each chunk so partial results are on disk
            # even if the script is interrupted mid-run
            out_fh.flush()

    elapsed = time.monotonic() - grand_start
    print(
        f"# All done. {total_files} file(s) processed in {elapsed:.1f}s. "
        f"Output: {output_path}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()