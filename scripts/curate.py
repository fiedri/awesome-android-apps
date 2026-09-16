"""
Curation criteria:
    - Repository inactivity (2 years)
    - Repository state ("archived": true)
    - License != FOSS
    - 404 detection / app removed from F-Droid or Play Store
        - 200 ok means the app exists
    - Detect redirects or dead sites

Data model (three layers):
    apps/*.json          identity only (name, description, source, stores)
    curate/cache.json    machine-computed facts, regenerated on every 'check'
    curate/overrides.json human decisions, versioned and NEVER overwritten

Merge rule: overrides > cache > source.

Commands:
    $ python scripts/curate.py check --dir apps
        Queries every repository and store and writes the facts into curate/cache.json.
        Never touches apps/*.json nor curate/overrides.json.

    $ python scripts/curate.py remove --dir apps --dry-run
        Shows which apps would be removed and which dead store links would be cleaned.

    $ python scripts/curate.py remove --dir apps
        Removes apps that match high-confidence criteria, cleans dead store links,
        purges orphan entries from cache/overrides and logs each removal to REMOVED.md.

Status values (derived at read time from the effective facts):
    - healthy        -> active repo, FOSS license and stores reachable
    - inactive       -> repo with no commits in the last 730 days (removed only
                         when ALL stores also return a real HTTP 404)
    - archived       -> repo was archived (removed when ALSO inactive AND all stores are 404)
    - no_open_code   -> license not detected as FOSS (needs manual review, NOT removed)
    - broken_link    -> some store returns a real 404 (informational, NOT removed on its own)
    - repo_gone      -> the source repository returns 404 (direct removal candidate)
    - (empty)        -> never checked yet, no data in cache

Automatic removal (only criteria the network cannot lie about):
    1. status == "repo_gone"  (the source code no longer exists)
    2. status == "archived" OR "inactive" + no commits in 730 days + ALL stores
       return a real HTTP 404 AND the repo publishes no releases. A timeout or
       connection error is "unknown", never counts as dead. An app is KEPT if
       any store works or the repo still ships a release (installable).
       If only SOME stores are 404 the app is kept and just those dead store
       links are suppressed via an override.

Manual review:
    Add an entry to curate/overrides.json keyed by the app "source". The "fields"
    dict wins over any computed value, so your manual decision survives re-checks.
    Pinning "status" in the override disables automatic removal for that app.
    Example:
    {
        "https://gitlab.com/xynngh/YetAnotherCallBlocker": {
            "fields": {"license": "GPL-3.0", "is_foss": true},
            "reason": "GitLab API does not expose the license; verified in the README."
        }
    }

GitHub token (optional, avoids the anonymous 60 req/h rate limit):
    - add GITHUB_TOKEN=<your_token> in a .env file at the repo root
    - or export GITHUB_TOKEN=<your_token>
    - minimal scope: public_repo (read only)
"""

import pathlib
import asyncio
import os
from datetime import datetime
import argparse
import aiohttp
from utils import (
    read_file,
    write_file,
    load_datastore,
    save_datastore,
    is_repo_active,
    get_api_url,
    derive_status,
    effective,
    merge_app,
    FOSS_LICENSES,
)

root = pathlib.Path(__file__).parent.parent.resolve()
CURATE_DIR = root / "curate"
CACHE_FILE = CURATE_DIR / "cache.json"
OVERRIDES_FILE = CURATE_DIR / "overrides.json"
removed_log = root / "REMOVED.md"
DEFAULT_DIR = root / "apps" / "test"

MAX_CONCURRENCY = 6
STORE_FIELDS = ("fdroid", "playstore", "website")


def load_token():
    """Reads GITHUB_TOKEN from the environment or from a .env file at the repo root."""
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        return token

    env_file = root / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("GITHUB_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


async def get_json(session, url):
    """GET against an API. Returns (data, http_status). (None, status) unless 200."""
    async with session.get(url) as response:
        if response.status == 403 or response.status == 429:
            print(f"Rate limit hit on {url} (status {response.status})")
            return None, response.status
        if response.status != 200:
            return None, response.status
        return await response.json(), response.status


async def check_last_commit(session, api_url, host):
    """Last real commit of the default branch. Endpoint differs per host."""
    try:
        if host == "github":
            commit_url = f"{api_url}/commits?per_page=1"
        else:
            commit_url = f"{api_url}/repository/commits?per_page=1"

        commits, _ = await get_json(session, commit_url)
        if not commits:
            return None

        commit = commits[0]
        if host == "github":
            return commit.get("commit", {}).get("committer", {}).get("date")
        return commit.get("committed_date")
    except Exception as e:
        print(f"Error fetching last commit: {e}")
        return None


async def check_repo(session, repo_api, host):
    try:
        data, http_status = await get_json(session, repo_api)
        if http_status == 404:
            return {
                "repo_http": http_status,
                "last_commit": None,
                "is_archived": False,
                "license": None,
                "is_foss": False,
                "has_release": False,
            }
        if not data:
            return None  # rate limit or another error -> leave the cache untouched

        last_commit = await check_last_commit(session, repo_api, host)
        is_archived = data.get("archived", False)
        has_release = await check_has_release(session, repo_api, host)

        license_data = data.get("license") or {}
        license_key = license_data.get("spdx_id") or license_data.get("key")

        is_foss = False
        if license_key:
            foss_licenses_lower = [item.lower() for item in FOSS_LICENSES]
            is_foss = license_key.lower() in foss_licenses_lower

        return {
            "repo_http": http_status,
            "last_commit": last_commit,
            "is_archived": is_archived,
            "license": license_key,
            "is_foss": is_foss,
            "has_release": has_release,
        }
    except Exception as e:
        print(f"Error processing repository {repo_api}: {e}")
        return None


async def check_has_release(session, api_url, host):
    """True when the repo has published releases (e.g. APKs to sideload).
    A repo with a release is still installable, so it must NOT be removed."""
    release_url = (
        f"{api_url}/releases?per_page=1" if host == "github" else f"{api_url}/releases"
    )
    releases, http_status = await get_json(session, release_url)
    if http_status == 404:
        return False
    return isinstance(releases, list) and bool(releases)


async def check_url_status(session, url):
    try:
        async with session.head(url, allow_redirects=True) as response:
            if response.status == 405:  # some CDNs do not support HEAD, retry with GET
                async with session.get(url, allow_redirects=True) as get_response:
                    return {
                        "url": url,
                        "status": get_response.status,
                        "available": get_response.status < 400,
                    }
            return {
                "url": url,
                "status": response.status,
                "available": response.status < 400,
            }
    except aiohttp.ClientConnectorError:
        return {"url": url, "status": "Connection Error", "available": None}
    except asyncio.TimeoutError:
        return {"url": url, "status": "Timeout", "available": None}
    except Exception as e:
        return {"url": url, "status": f"Error: {str(e)}", "available": None}


async def check(session, urls):
    repo = await check_repo(session, urls["api_url"], urls["host"])
    if not repo:
        return None

    stores_tasks = []
    for store_url in urls["stores"]:
        if store_url:
            stores_tasks.append(check_url_status(session, store_url))

    status_stores = await asyncio.gather(*stores_tasks) if stores_tasks else []
    repo["stores_status"] = status_stores
    return repo


async def process_check(apps_files):
    cache = load_datastore(CACHE_FILE)

    token = load_token()
    headers = {"User-Agent": "foss-apps-curator"}
    if token:
        headers["Authorization"] = f"token {token}"
        print("GitHub token loaded")
    else:
        print("No GitHub token found; anonymous API (60 req/h rate limit)")

    async with aiohttp.ClientSession(
        headers=headers, timeout=aiohttp.ClientTimeout(total=30)
    ) as session:
        semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

        async def limited(api_url, host, stores):
            async with semaphore:
                return await check(
                    session, {"api_url": api_url, "host": host, "stores": stores}
                )

        for file in apps_files:
            data = read_file(file)
            apps = data.get("apps", [])

            tasks = []
            valid_apps = []

            for app in apps:
                source = app.get("source")
                stores = [
                    app.get("fdroid", "no_available"),
                    app.get("playstore", "no_available"),
                ]
                stores = [s for s in stores if s and s != "no_available"]

                api_url, host = get_api_url(source)
                if not api_url:
                    valid_apps.append(app)
                    tasks.append(None)
                    print(f"Unsupported host, not checked: {app.get('name')}")
                    continue

                tasks.append(limited(api_url, host, stores))
                valid_apps.append(app)

            results = await asyncio.gather(*[t for t in tasks if t is not None])
            results_iter = iter(results)
            updated = 0

            for app, task in zip(valid_apps, tasks):
                if task is None:
                    continue
                res = next(results_iter)
                if res:
                    cache[app["source"]] = res
                    updated += 1

            if write_file(CACHE_FILE, cache):
                print(f"{file.name}: updated cache for {updated}/{len(apps)} apps")
            else:
                print(f"{file.name}: no changes")

    return apps_files


def removal_reason(app, has_status_override):
    """Returns the reason if the app matches a removal criteria, or None.

    Operates directly on the effective facts, NOT on the derived status: a repo
    with no commits and every store returning a real HTTP 404 is dead whether
    it is archived or just inactive.

    A human-pinned status (override) disables auto-removal: the human owns
    the fate of that app.
    """
    if has_status_override:
        return None

    if app.get("repo_http") == 404:
        return "Source repository returns 404: the code no longer exists"

    stores = app.get("stores_status") or []
    # ONLY real HTTP 404s count as dead. A timeout or connection error is
    # "unknown" and never triggers removal.
    if stores and all(s.get("status") == 404 for s in stores):
        if not is_repo_active(app.get("last_commit")):
            label = "archived" if app.get("is_archived") else "inactive"
            if app.get("has_release"):
                return None  # still installable from the repo releases
            return (
                f"Repo {label} + no commits in 730 days + ALL stores return HTTP 404 "
                "and no repo release: it can no longer be obtained anywhere"
            )

    return None


def clean_broken_stores(app):
    """Returns the override fields that suppress dead store links for an app.
    Only a real HTTP 404 suppresses a link; timeouts/errors stay untouched."""
    removed_urls = []
    live_stores = []

    for store in app.get("stores_status") or []:
        if store.get("status") == 404:
            removed_urls.append(store.get("url"))
            continue

        live_stores.append(store)

    if not removed_urls:
        return None

    fields = {"stores_status": live_stores}
    for url in removed_urls:
        for field in STORE_FIELDS:
            if app.get(field) == url:
                fields[field] = None

    return fields


def record_override(source, fields, reason):
    """Merges fields into the override entry. The HUMAN reason is never lost:
    an existing reason wins over the automatic one (the auto reason is only
    used as the default for a brand new entry)."""
    overrides = load_datastore(OVERRIDES_FILE)
    entry = overrides.get(source, {})
    merged_fields = dict(entry.get("fields", {}))
    merged_fields.update(fields)
    overrides[source] = {
        "fields": merged_fields,
        "reason": entry.get("reason") or reason,
    }
    return save_datastore(OVERRIDES_FILE, overrides)


def process_remove(apps_files, dry_run):
    cache = load_datastore(CACHE_FILE)
    overrides = load_datastore(OVERRIDES_FILE)

    removed_apps = []
    cleaned_stores = []
    orphaned_sources = []

    for file in apps_files:
        data = read_file(file)
        apps = data.get("apps", [])

        kept = []
        file_removed = 0
        file_cleaned = 0

        for app in apps:
            source = app.get("source")
            override = overrides.get(source)
            cached = cache.get(source)
            merged = effective(app, cached, override)

            # Removal is judged on the RAW facts (cache), not on the merged view:
            # a store-suppression override hides the stores, but the 404s are real
            # on the network. Only a human-pinned "status" blocks auto-removal.
            facts = merge_app(app, cached, None)
            reason = removal_reason(
                facts, has_status_override="status" in (override or {}).get("fields", {})
            )
            if reason:
                file_removed += 1
                removed_apps.append(
                    {
                        "name": app.get("name"),
                        "category": file.stem,
                        "reason": reason,
                        "source": source,
                    }
                )
                orphaned_sources.append(source)
                continue

            fields = clean_broken_stores(merged)
            if fields:
                cleaned_links = sum(1 for v in fields.values() if v is None)
                file_cleaned += cleaned_links
                cleaned_stores.append((app.get("name"), file.stem, source, fields))
            kept.append(app)

        if file_removed or file_cleaned:
            if not dry_run:
                data["apps"] = kept
                write_file(file, data)

            verb = "would remove" if dry_run else "removed"
            print(
                f"  {file.name}: {verb} {file_removed} app(s) and "
                f"{file_cleaned} dead store link(s)"
            )

    if removed_apps:
        verb = "Would remove" if dry_run else "Removed"
        print(f"\n{verb} {len(removed_apps)} app(s):")
        for entry in removed_apps:
            print(f"  - {entry['name']} ({entry['category']}): {entry['reason']}")

    if cleaned_stores:
        verb = "Would clean" if dry_run else "Cleaned"
        total = sum(1 for _, _, _, f in cleaned_stores for v in f.values() if v is None)
        print(f"\n{verb} {total} dead store link(s):")
        for name, category, _, fields in cleaned_stores:
            for field, value in fields.items():
                if value is None:
                    print(f"  - {name} ({category}): {field}")

    if not removed_apps and not cleaned_stores:
        print("Nothing to remove or clean.")
        return

    if not dry_run:
        for source in orphaned_sources:
            cache.pop(source, None)
            overrides.pop(source, None)
        save_datastore(CACHE_FILE, cache)
        save_datastore(OVERRIDES_FILE, overrides)
        for name, category, source, fields in cleaned_stores:
            record_override(
                source,
                fields,
                reason="Dead store link(s) suppressed after archived + inactive check",
            )
        if removed_apps:
            log_removed(removed_apps)


def log_removed(removed_entries):
    date = datetime.now().date().isoformat()

    if removed_log.exists():
        content = removed_log.read_text(encoding="utf-8").rstrip("\n")
    else:
        content = "# Removed Apps\n\nLog of apps automatically removed by `scripts/curate.py`."

    rows = "\n".join(
        f"| {e['name']} | {e['category']} | {e['reason']} | {e['source']} |"
        for e in removed_entries
    )

    if f"## {date}" in content:
        content += f"\n{rows}\n"
    else:
        section = f"\n\n## {date}\n\n| App | Category | Reason | Source |\n|-----|----------|--------|--------|\n{rows}"
        content += section + "\n"

    removed_log.write_text(content, encoding="utf-8")
    print(f"\nRemoval log updated: {removed_log}")


def get_apps_files(json_dir):
    json_dir = pathlib.Path(json_dir)
    if not json_dir.exists():
        print(f"Directory does not exist: {json_dir}")
        return []
    return sorted(
        item for item in json_dir.iterdir() if item.is_file() and item.suffix == ".json"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="FOSS apps curator")
    parser.add_argument("command", choices=("check", "remove"))
    parser.add_argument(
        "--dir",
        default=str(DEFAULT_DIR),
        help=f"Directory containing the .json files (default: {DEFAULT_DIR})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="In 'remove', only shows what would happen without touching anything",
    )
    args = parser.parse_args(argv)

    apps_files = get_apps_files(args.dir)
    if not apps_files:
        return

    if args.command == "check":
        asyncio.run(process_check(apps_files))
    elif args.command == "remove":
        process_remove(apps_files, args.dry_run)


if __name__ == "__main__":
    main()