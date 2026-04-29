from __future__ import annotations

"""
csv_writer.py
-------------
CSV formatting helpers for batch extraction output.

Provides:
  - _CSV_HEADER   : the column header row
  - _escape_csv_field : RFC-4180 field escaping
  - _make_data_row    : build a CSV row from a successful extraction result
  - _make_error_row   : build a CSV row for a permanently failed file
  - _comment          : build a plain-text progress comment line
"""

_CSV_HEADER = "filename,bank_name,fi_num,master_account_number,sub_account_number\r\n"


def _escape_csv_field(value: str | None) -> str:
    if value is None:
        return ""
    s = str(value)
    if "," in s or '"' in s or "\n" in s or "\r" in s:
        s = '"' + s.replace('"', '""') + '"'
    return s


def _make_data_row(filename: str, result) -> str:
    d = result.data
    fields = [
        filename,
        d.bank_name,
        d.fi_num,
        d.master_account_number,
        d.sub_account_number,
    ]
    return ",".join(_escape_csv_field(f) for f in fields) + "\r\n"


def _make_error_row(filename: str) -> str:
    fields = [filename, "", "", "", ""]
    return ",".join(_escape_csv_field(f) for f in fields) + "\r\n"


def _comment(message: str) -> str:
    return f"# {message}\r\n"