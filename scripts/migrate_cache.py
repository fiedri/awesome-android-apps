"""One-shot migration: extract computed fields out of apps/*.json into curate/cache.json.

Run once (it is idempotent: apps without computed fields are left untouched):
    $ python scripts/migrate_cache.py --dir apps
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from utils import read_file, write_file, load_datastore, save_datastore

COMPUTED_FIELDS = ("repo_http", "last_commit", "is_archived", "is_foss", "stores_status", "license")


def migrate(json_dir):
    root = pathlib.Path(__file__).parent.parent.resolve()
    cache_file = root / "curate" / "cache.json"
    overrides_file = root / "curate" / "overrides.json"
    cache = load_datastore(cache_file)
    moved = 0

    for file in sorted(json_dir.glob("*.json")):
        data = read_file(file)
        apps = data.get("apps", [])
        changed = False

        for app in apps:
            source = app.get("source")
            extracted = {k: app.get(k) for k in COMPUTED_FIELDS if k in app}
            if not extracted:
                continue
            entry = cache.setdefault(source, {})
            entry.update(extracted)
            for k in extracted:
                del app[k]
            changed = True
            moved += 1

        if changed:
            write_file(file, data)

    save_datastore(cache_file, cache)
    # ensure overrides exist (empty) so build.py finds them
    if not overrides_file.exists():
        save_datastore(overrides_file, {})
    print(f"Migrated computed fields from {moved} apps -> {cache_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="One-shot cache migration")
    parser.add_argument("--dir", default="apps", help="Directory with .json identities")
    args = parser.parse_args()
    root = pathlib.Path(__file__).parent.parent.resolve()
    migrate(root / args.dir)