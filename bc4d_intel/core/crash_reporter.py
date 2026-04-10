"""Automatic crash reporting to GitHub Issues.

When the app crashes, this creates a GitHub Issue with:
- Error traceback
- System info (Python version, OS, screen size)
- App state summary (what was loaded, what screen was active)

The GitHub token is encoded (not encrypted — this is obfuscation
for casual inspection, not security). Anyone with the source code
can decode it. The token should have ONLY 'issues:write' scope.
"""

from __future__ import annotations
import base64, json, logging, os, platform, traceback
from datetime import datetime

log = logging.getLogger("bc4d_intel.crash_reporter")

# ── GitHub config ────────────────────────────────────────────────
# To set up: create a PAT at https://github.com/settings/tokens
# with ONLY "repo" scope. Then encode it:
#   python -c "import base64; print(base64.b64encode(b'ghp_YourTokenHere').decode())"
# Paste the result below.

_REPO = "Jan-Nicola-Beyer/bc4d-intel"
_TOKEN_B64 = ""  # paste base64-encoded token here


def _get_token() -> str:
    if not _TOKEN_B64:
        return ""
    try:
        return base64.b64decode(_TOKEN_B64).decode("utf-8")
    except Exception:
        return ""


def report_crash(
    exc_type, exc_value, exc_tb,
    app_state=None,
    active_screen: str = "",
) -> bool:
    """Send crash report to GitHub Issues. Returns True if successful."""
    token = _get_token()
    if not token:
        log.warning("Crash reporter: no token configured")
        return False

    # Build report body
    tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))

    system_info = (
        f"- Python: {platform.python_version()}\n"
        f"- OS: {platform.system()} {platform.release()} ({platform.version()})\n"
        f"- Machine: {platform.machine()}\n"
        f"- Time: {datetime.now().isoformat()}\n"
    )

    state_info = "No app state available."
    if app_state:
        try:
            state_info = (
                f"- Staffel: {getattr(app_state, 'staffel_name', '?')}\n"
                f"- N Pre: {getattr(app_state, 'n_pre', '?')}\n"
                f"- N Post: {getattr(app_state, 'n_post', '?')}\n"
                f"- Matched: {getattr(app_state, 'matched_pairs', '?')}\n"
                f"- Questions analysed: {len(getattr(app_state, 'tagged_responses', {}))}\n"
                f"- Report sections: {len(getattr(app_state, 'report_sections', {}))}\n"
                f"- Active screen: {active_screen}\n"
            )
        except Exception:
            state_info = "Error reading app state."

    body = (
        f"## Automatic Crash Report\n\n"
        f"### Error\n```\n{str(exc_value)}\n```\n\n"
        f"### Traceback\n```python\n{tb_text[-2000:]}\n```\n\n"
        f"### System\n{system_info}\n\n"
        f"### App State\n{state_info}\n"
    )

    title = f"[Crash] {exc_type.__name__}: {str(exc_value)[:80]}"

    # Send to GitHub Issues API
    try:
        import urllib.request
        url = f"https://api.github.com/repos/{_REPO}/issues"
        data = json.dumps({
            "title": title,
            "body": body,
            "labels": ["crash-report"],
        }).encode("utf-8")

        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Authorization", f"token {token}")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/vnd.github.v3+json")

        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status in (200, 201):
                result = json.loads(resp.read())
                log.info("Crash report filed: %s", result.get("html_url", ""))
                return True
    except Exception as e:
        log.warning("Failed to send crash report: %s", e)

    return False
