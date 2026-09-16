import json
from datetime import datetime, timezone
from urllib.parse import quote_plus

# Used to detect FOSS licenses both at check time and when deriving status.
FOSS_LICENSES = [
    "MIT",
    "Apache-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "ISC",
    "Unlicense",
    "CC0-1.0",
    "0BSD",
    "GPL-2.0",
    "GPL-2.0-or-later",
    "GPL-3.0",
    "GPL-3.0-or-later",
    "AGPL-3.0",
    "AGPL-3.0-or-later",
    "LGPL-2.1",
    "LGPL-2.1-or-later",
    "LGPL-3.0",
    "LGPL-3.0-or-later",
    "MPL-2.0",
    "EPL-2.0",
    "CDDL-1.0",
    "EUPL-1.2",
]

# Keys that mean "this app has been checked at least once".
HAS_DATA_KEYS = ("repo_http", "last_commit", "stores_status", "license", "is_foss")


def read_file(path_file):
    with open(path_file, "r", encoding="utf-8") as archivo:
        datos = json.load(archivo)

    return datos


def write_file(path_file, data):
    new_content = json.dumps(data, indent=4, ensure_ascii=True)
    original = ""
    path_file.parent.mkdir(parents=True, exist_ok=True)
    if path_file.exists():
        original = path_file.read_text(encoding="utf-8")
        if original.endswith("\n") and not new_content.endswith("\n"):
            new_content += "\n"

    if new_content == original:
        return False

    with open(path_file, "w", encoding="utf-8") as archivo:
        archivo.write(new_content)

    return True


def load_datastore(path):
    """Loads a JSON datastore (cache or overrides), returning {} if missing."""
    if not path.exists():
        return {}
    return read_file(path)


def save_datastore(path, data):
    """Writes a JSON datastore (cache or overrides), creating the parent dir."""
    path.parent.mkdir(parents=True, exist_ok=True)
    return write_file(path, data)


def is_repo_active(last_commit_str):
    """Checks whether the last commit happened within the last 2 years (730 days)."""
    if not last_commit_str:
        return False
    try:
        commit_date = datetime.fromisoformat(last_commit_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        days_diff = (now - commit_date).days
        return days_diff <= 730
    except Exception:
        return False


def get_api_url(source):
    """Converts the source URL into the repository API URL."""
    if not source:
        return None, None

    if source.startswith("https://github.com/"):
        api_url = source.replace("https://github.com/", "https://api.github.com/repos/", 1)
        return api_url, "github"

    if source.startswith("https://gitlab.com/"):
        clean_path = source.replace("https://gitlab.com/", "").strip("/")
        clean_path = clean_path.split("/-/")[0]
        encoded = quote_plus(clean_path)
        return f"https://gitlab.com/api/v4/projects/{encoded}", "gitlab"

    return None, None


def derive_status(app):
    """Derives the status from effective facts. Priority: archived > no_open_code >
    broken_link > inactive > healthy."""
    if app.get("repo_http") == 404:
        return "repo_gone"
    if app.get("is_archived"):
        return "archived"
    if not app.get("is_foss"):
        return "no_open_code"
    stores = app.get("stores_status") or []
    if any(not s.get("available", True) for s in stores):
        return "broken_link"
    if not is_repo_active(app.get("last_commit")):
        return "inactive"
    return "healthy"


def merge_app(source, cached, override):
    """Merges identity (source) + machine facts (cached) + human decisions (override).
    Priority: override > cached > source."""
    app = dict(source)
    app.update(cached or {})
    app.update((override or {}).get("fields", {}))
    return app


def effective(source, cached, override):
    """Merge and resolve the final view + status for one source app.

    - A pinned status in the override always wins.
    - Otherwise the status is derived from the effective facts.
    - If there is no data yet, the status is empty (not yet curated)."""
    override_fields = (override or {}).get("fields", {})
    app = merge_app(source, cached, override)
    if "status" in override_fields:
        app["status"] = override_fields["status"]
    elif any(key in app for key in HAS_DATA_KEYS):
        app["status"] = derive_status(app)
    else:
        app["status"] = ""
    return app