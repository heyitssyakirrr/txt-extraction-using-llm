"""
Configures the root logger for PBAI with terminal output and daily rotating log files.
Logs are written to {sys_log_dir}/system_{YYYY-MM-DD}.log, appending within the same day.
Files older than the configured month retention window are pruned automatically on each
daily rotation.
"""

from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path


# Column widths — must match %(asctime)s (23) and the padding in _LOG_FORMAT below.
_TS_W   = 23
_LVL_W  = 8
_NAME_W = 20
_DESC_W = 13   # fixed width for the header "Description" cell only

# Total outer width of the log table (used by the startup block builder).
LOG_TABLE_W = 1 + (_TS_W + 2) + 1 + (_LVL_W + 2) + 1 + (_NAME_W + 2) + 1 + (_DESC_W + 2) + 1

# Left/right padding inside the bridge that frames the startup PBAI box.
STARTUP_PAD = 14

_LOG_FORMAT = (
    f"│ %(asctime)s │ %(levelname)-{_LVL_W}s │ %(name)-{_NAME_W}s │ %(message)s"
)


class DailyRotatingFileHandler(logging.StreamHandler):
    """
    Writes log records to a daily log file: {log_dir}/system_{YYYY-MM-DD}.log.
    Rotates to a new file when the calendar day changes and prunes files
    older than `months_to_keep` months.
    """

    def __init__(self, log_dir: Path, months_to_keep: int) -> None:
        self._log_dir = log_dir
        self._months_to_keep = months_to_keep
        self._current_day: str = ""
        self._file = None  # the file handle we own; never sys.stderr
        self._open_stream()
        super().__init__(stream=self._file)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _day_key(self) -> str:
        return date.today().strftime("%Y-%m-%d")

    def _log_path(self, day: str) -> Path:
        return self._log_dir / f"system_{day}.log"

    def _open_stream(self) -> None:
        """Open (or create) the log file for today."""
        day = self._day_key()
        if self._file is not None:
            try:
                self._file.flush()
                self._file.close()
            except Exception:
                pass
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._file = open(self._log_path(day), "a", encoding="utf-8")  # noqa: SIM115
        self.stream = self._file
        self._current_day = day
        self._prune()

    def _prune(self) -> None:
        """Delete log files older than the retention window."""
        today = date.today()
        cutoff_month = today.month - self._months_to_keep
        cutoff_year = today.year
        while cutoff_month <= 0:
            cutoff_month += 12
            cutoff_year -= 1
        cutoff = date(cutoff_year, cutoff_month, today.day)

        for log_file in self._log_dir.glob("system_????-??-??.log"):
            stem = log_file.stem  # e.g. "system_2026-03-15"
            parts = stem.split("_", 1)
            if len(parts) != 2:
                continue
            try:
                file_date = date.fromisoformat(parts[1])
            except (ValueError, TypeError):
                continue
            if file_date < cutoff:
                try:
                    log_file.unlink()
                except OSError:
                    pass

    # ------------------------------------------------------------------
    # Override emit to handle day rollover
    # ------------------------------------------------------------------

    def emit(self, record: logging.LogRecord) -> None:
        if self._day_key() != self._current_day:
            self._open_stream()
        super().emit(record)


_file_handler: DailyRotatingFileHandler | None = None


def write_raw(*lines: str) -> None:
    """Write lines directly to all log outputs without any timestamp/level prefix.

    Used for standalone visual blocks (e.g. the startup block) that should
    appear outside the running log table rows.
    """
    for line in lines:
        sys.stdout.write(line + "\n")
    sys.stdout.flush()
    if _file_handler is not None and _file_handler._file is not None:
        for line in lines:
            _file_handler._file.write(line + "\n")
        _file_handler._file.flush()


def _tbl_hline(l: str, c: str, r: str) -> str:
    return (l + "─" * (_TS_W + 2) + c + "─" * (_LVL_W + 2) + c
            + "─" * (_NAME_W + 2) + c + "─" * (_DESC_W + 2) + r)


def configure_logging(sys_log_dir: Path, months_to_keep: int) -> None:
    """
    Replace the default logging configuration with:
    - A StreamHandler writing to stdout
    - A DailyRotatingFileHandler writing to {sys_log_dir}/system_{YYYY-MM-DD}.log

    Both handlers share the same box-table column format.
    The opening table header is written immediately so the first uvicorn log
    rows appear inside the table border.
    """
    global _file_handler

    formatter = logging.Formatter(_LOG_FORMAT)

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)

    _file_handler = DailyRotatingFileHandler(sys_log_dir, months_to_keep)
    _file_handler.setFormatter(formatter)

    logging.basicConfig(
        level=logging.INFO,
        handlers=[stdout_handler, _file_handler],
    )

    write_raw(
        _tbl_hline("┌", "┬", "┐"),
        "│ " + f"{'Timestamp':<{_TS_W}} │ {'Level':<{_LVL_W}} │ {'Process':<{_NAME_W}} │ {'Description':<{_DESC_W}} │",
        _tbl_hline("├", "┼", "┤"),
    )
