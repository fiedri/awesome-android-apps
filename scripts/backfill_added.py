#!/usr/bin/env python3
import argparse, pathlib, subprocess

import utils

IMPORT_COMMIT_DATE = "2026-09-16"

root = pathlib.Path(__file__).parent.parent.resolve()
apps_dir = root / "apps"


def normalize_url(url):
    url = url.strip()
    if url.endswith(".git"):
        url = url[:-4]
    return url.rstrip("/")


def git_added_date(normalized):
    proc = subprocess.run(
        ["git", "log", "-S", normalized, "--format=%ad", "--date=short", "--", "apps/"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    lines = proc.stdout.strip().splitlines()
    if proc.returncode != 0 or not lines:
        return None
    return lines[-1]


def collect_sources():
    sources = []
    datas = {}
    for cat in apps_dir.iterdir():
        if not cat.is_file() or cat.suffix != ".json":
            continue
        data = utils.read_file(cat)
        datas[cat.name] = (cat, data)
        for app in data.get("apps", []):
            sources.append((cat.name, app))
    return sources, datas


def place_after_source(app, date):
    reordered = {}
    for key, value in app.items():
        reordered[key] = value
        if key == "source":
            reordered["added"] = date
    return reordered


def main():
    parser = argparse.ArgumentParser(description="Stamp added dates from git history")
    parser.add_argument("--run", action="store_true", help="write files instead of dry-run")
    args = parser.parse_args()

    sources, datas = collect_sources()
    date_cache = {}
    fallbacks = []
    per_file = {}
    total_added = 0
    total_skipped = 0
    changed_apps = set()

    for fname, app in sources:
        if "added" in app:
            total_skipped += 1
            continue
        norm = normalize_url(app.get("source") or "")
        if norm not in date_cache:
            date_cache[norm] = git_added_date(norm)
            if date_cache[norm] is None:
                date_cache[norm] = IMPORT_COMMIT_DATE
                fallbacks.append(norm)
        per_file.setdefault(fname, 0)
        per_file[fname] += 1
        app["added"] = date_cache[norm]
        changed_apps.add(id(app))
        total_added += 1

    for fname in per_file:
        data = datas[fname][1]
        data["apps"] = [
            place_after_source(a, a["added"]) if id(a) in changed_apps else a
            for a in data.get("apps", [])
        ]

    if not args.run:
        print("dry-run: would stamp `added` on %d apps" % total_added)
        print("skipped (already have `added`): %d" % total_skipped)
    else:
        for fname, (cat, data) in datas.items():
            if fname in per_file:
                utils.write_file(cat, data)
        print("run: stamped `added` on %d apps" % total_added)
        print("skipped (already have `added`): %d" % total_skipped)

    for fname in sorted(per_file):
        print("  %s: %d" % (fname, per_file[fname]))
    print("fallback to %s: %d apps" % (IMPORT_COMMIT_DATE, len(fallbacks)))
    if fallbacks:
        for norm in sorted(fallbacks):
            print("    %s" % norm)


if __name__ == "__main__":
    main()