"""Step-by-step diagnostics for WhatsApp target attempts.

Every automated target creates one :class:`Trace`. The trace writes the same
line to three places:

1. a per-target file in ``data/debug/trace_<timestamp>_<target>.log``
2. the Live page feed through the runner's ``on_event`` callback
3. the flat ``logs`` table with ``source='poster'``

Failures additionally capture a screenshot plus the ``#side``/``#main`` DOM so
a broken selector can be inspected after the fact.
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from config import APP_HOME, DATA_DIR
from db_logic import log
from . import settings as app_settings

# Same row selectors as poster.py. Kept here so describe_results() can be used
# without importing poster (which imports this module).
ROW_SELECTORS = [
    '#pane-side div[role="row"]',
    '#pane-side div[role="listitem"]',
    'div[role="row"]',
    'div[role="listitem"]',
    'div[data-testid="cell-frame-container"]',
]

MAX_DEBUG_FILES = 100


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip())
    return cleaned.strip("_")[:80] or "target"


def _setting_bool(key: str, default: bool) -> bool:
    try:
        return bool(app_settings.get_setting(key, default))
    except Exception:
        return default


def _display_path(path: Path) -> str:
    """Prefer a path relative to the project so log lines stay short."""
    try:
        return str(path.relative_to(APP_HOME)).replace("\\", "/")
    except Exception:
        return str(path)


def _visible_rows(page, selector: str):
    try:
        rows = page.query_selector_all(selector)
    except Exception:
        return []
    visible = []
    for row in rows:
        try:
            if row.is_visible():
                visible.append(row)
        except Exception:
            continue
    return visible


def describe_results(page) -> Dict[str, Any]:
    """Count visible result rows per selector and read the first ten texts."""
    counts: Dict[str, int] = {}
    texts: Dict[str, list[str]] = {}
    for selector in ROW_SELECTORS:
        rows = _visible_rows(page, selector)
        counts[selector] = len(rows)
        texts[selector] = []
        for row in rows[:10]:
            try:
                text = (row.inner_text() or "").strip()
            except Exception:
                text = ""
            if text:
                texts[selector].append(re.sub(r"\s+", " ", text))
    return {"counts": counts, "texts": texts}


def describe_results_line(page) -> str:
    """One-line ``selector=count`` summary used by the trace."""
    counts = describe_results(page)["counts"]
    return " | ".join(f"{selector}={count}" for selector, count in counts.items())


class Trace:
    """Per-target attempt trace.

    ``step`` lines are routine detail and honour the ``detailed_logs`` setting.
    ``fail`` / ``capture`` / ``finish`` lines are always surfaced because they
    carry the actionable failure reason.
    """

    def __init__(
        self,
        on_event: Optional[Callable[[str], None]],
        target: str,
        run_id: Optional[int] = None,
        attempt: int = 1,
        attempts: int = 3,
    ) -> None:
        self.on_event = on_event
        self.target = (target or "").strip()
        self.run_id = run_id
        self.attempt = max(1, int(attempt or 1))
        self.attempts = max(1, int(attempts or 1))
        self.started_at = time.time()
        self.finished = False
        self.failure_step: Optional[str] = None
        self.failure_detail = ""
        # Set when the chat opened but cannot accept messages (e.g. read-only
        # group). Retrying the search/open cannot help.
        self.stop_retries = False

        self.detailed_logs = _setting_bool("detailed_logs", True)
        self.debug_capture_enabled = _setting_bool("debug_capture", True)
        self.trace_files = _setting_bool("trace_files", True)

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.debug_dir = Path(DATA_DIR) / "debug"
        try:
            self.debug_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self.path: Optional[Path] = None
        if self.trace_files:
            self.path = self.debug_dir / f"trace_{stamp}_{_safe_name(self.target)}.log"

        run_label = "-" if self.run_id is None else str(self.run_id)
        self._write(
            f"[target] {self.target} | attempt {self.attempt}/{self.attempts} | run {run_label}",
            routine=True,
        )
        # Keep the whole debug directory bounded, not just failure captures:
        # trace files are written for successful targets too.
        self._prune()

    # ── time / file helpers ─────────────────────────────────────────────
    def elapsed(self) -> float:
        return max(0.0, time.time() - self.started_at)

    def _write(self, line: str, *, level: str = "info", routine: bool = True) -> None:
        if self.trace_files and self.path is not None:
            try:
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
            except Exception:
                pass
        if routine and not self.detailed_logs:
            return
        try:
            log(level, line, "poster")
        except Exception:
            pass
        if self.on_event is not None:
            try:
                self.on_event(line)
            except Exception:
                pass

    def file_only(self, text: str) -> None:
        """Write detail (for example the full message) only to the trace file."""
        if not self.trace_files or self.path is None:
            return
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(text.rstrip("\n") + "\n")
        except Exception:
            pass

    # ── public trace API ────────────────────────────────────────────────
    def step(self, phase: str, action: str, detail: str = "") -> None:
        line = f"[{phase}] {action}"
        if detail:
            line += f" | {detail}"
        line += f" | elapsed={self.elapsed():.1f}s"
        self._write(line, routine=True)

    def fail(self, phase: str, action: str, detail: str) -> None:
        """Record the exact failing step.

        ``phase`` is the trace area (``group``, ``composer``, ...) and
        ``action`` is the step name used in the final result line.
        """
        self.failure_step = action
        self.failure_detail = detail
        line = f"[{phase}] FAILED | step={action}"
        if detail:
            line += f" | reason={detail}"
        line += f" | elapsed={self.elapsed():.1f}s"
        self._write(line, level="warning", routine=False)

    def retry(self, attempt: int, delay: float = 0.0, detail: str = "") -> None:
        self.attempt = max(1, int(attempt))
        reason = detail or f"attempt {self.attempt}/{self.attempts} in {delay:.1f}s"
        self._write(
            f"[target] retrying | {reason} | elapsed={self.elapsed():.1f}s",
            routine=True,
        )

    def capture(self, page, label: str) -> Tuple[Optional[str], Optional[str]]:
        """Save a screenshot and the ``#side`` / ``#main`` DOM for a failure."""
        if not self.debug_capture_enabled or page is None:
            return None, None
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        base = f"{stamp}_{_safe_name(self.target)}_{_safe_name(label)}"
        png_path = self.debug_dir / f"{base}.png"
        html_path = self.debug_dir / f"{base}.html"

        screenshot: Optional[Path] = None
        try:
            page.screenshot(path=str(png_path), full_page=False)
            screenshot = png_path
        except Exception:
            screenshot = None

        html: Optional[Path] = None
        try:
            side = page.evaluate(
                "() => { const el = document.querySelector('#side'); return el ? el.outerHTML : ''; }"
            )
            main = page.evaluate(
                "() => { const el = document.querySelector('#main'); return el ? el.outerHTML : ''; }"
            )
            html_path.write_text(
                "<!-- #side -->\n" + (side or "") + "\n<!-- #main -->\n" + (main or ""),
                encoding="utf-8",
            )
            html = html_path
        except Exception:
            html = None

        shot_label = _display_path(screenshot) if screenshot else "-"
        html_label = _display_path(html) if html else "-"
        self._write(
            f"[capture] screenshot={shot_label} | html={html_label} | elapsed={self.elapsed():.1f}s",
            level="warning",
            routine=False,
        )
        self._prune()
        return (str(screenshot) if screenshot else None, str(html) if html else None)

    def skip(self, reason: str) -> None:
        line = (
            f"[result] TARGET SKIPPED | target={self.target} | reason={reason}"
            f" | total={self.elapsed():.1f}s"
        )
        self.finished = True
        self._write(line, level="info", routine=False)

    def finish(self, success: bool, step: str = "", detail: str = "") -> None:
        if self.finished:
            return
        self.finished = True
        if success:
            line = (
                f"[result] MESSAGE SENT SUCCESSFULLY | target={self.target}"
                f" | total={self.elapsed():.1f}s"
            )
            summary = (
                f"[summary] target={self.target} | success=yes | step={step or 'send'}"
                f" | total={self.elapsed():.1f}s"
            )
            self._write(line, level="info", routine=False)
            self._write(summary, level="info", routine=False)
            return

        failed_step = step or self.failure_step or "unknown"
        line = (
            f"[result] TARGET FAILED | step={failed_step} | target={self.target}"
            f" | total={self.elapsed():.1f}s"
        )
        if detail:
            line += f" | reason={detail}"
        summary = (
            f"[summary] target={self.target} | success=no | step={failed_step}"
            f" | total={self.elapsed():.1f}s"
        )
        self._write(line, level="error", routine=False)
        self._write(summary, level="info", routine=True)

    # ── housekeeping ────────────────────────────────────────────────────
    def _prune(self) -> None:
        try:
            files = [path for path in self.debug_dir.iterdir() if path.is_file()]
        except Exception:
            return
        files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        for path in files[MAX_DEBUG_FILES:]:
            try:
                path.unlink()
            except Exception:
                continue
