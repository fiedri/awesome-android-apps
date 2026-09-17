# Scripts

Helper scripts for maintaining this repository. Run them from the repo root.

## Setup

The scripts need Python 3.10+ and `aiohttp` for the network checks. Use a
virtual environment so you don't pollute your system Python (many distros block
`pip install` globally — e.g. Debian/Ubuntu with PEP 668).

```bash
# 1. create the virtual environment once
$ python3 -m venv .venv

# 2. activate it (each new terminal)
$ source .venv/bin/activate        # Linux / macOS

# 3. install the dependencies
$ pip install -r requirements.txt
```

From now on use `python` (the venv one) from the repo root:

```bash
$ python scripts/curate.py check --dir apps
$ python scripts/curate.py remove --dir apps --dry-run
$ python scripts/build.py
```

For GitHub rate limits (optional but recommended), see the [GitHub token](#github-token-optional)
section below — a token raises the API limit from 60 to 5000 req/h so `check`
can complete the whole catalogue.

| Script | Purpose |
|--------|---------|
| [`add.py`](#addpy) | Interactively add an app or a category to `apps/*.json` |
| [`build.py`](#buildpy) | Regenerate `ALL_APPS.md` (all category tables in one file, with a table of contents, a recent additions list and status legend) plus the README app count, table of contents and status legend |
| [`backfill_added.py`](#backfill_addedpy) | One-time migration: stamp each app's `added` field with its first-appearance date from git history |
| [`curate.py`](#curatepy) | Check repository/store health, mark statuses, remove dead apps and clean dead store links |

---

## add.py

```
$ python scripts/add.py
```

Prompts `[0] new app` / `[1] new category`. No command line arguments.

- **new app**: asks for category, source, name, description and optional `fdroid`, `playstore`, `website` links. Every link is validated over HTTP (must return 200). Apps are inserted alphabetically by name, and each new app gets an `added` field with today's date (`YYYY-MM-DD`).
- **new category**: asks for a slug name and an emoji, then creates `apps/<name>.json`.

After adding, run:

```
$ python scripts/build.py
```

### Parameters

None. Everything is interactive.

---

## build.py

```
$ python scripts/build.py
```

Regenerates the generated content from `apps/*.json`:

- `ALL_APPS.md` — every category table in a single file (`App | Status | Description | Stars | Last commit | Links`), with a table of contents, the status legend, and a `## Recently Added` section listing the 15 most recently added apps (by the `added` field, which every app in `apps/*.json` now carries).
- `README.md` — the `apps-count` badge, the `table-of-contents` chunk and the `status-legend` chunk.

The script is idempotent: if the source JSONs did not change, running it again produces byte-identical files (no phantom diffs).

### Parameters

None.

---

## backfill_added.py

One-time migration that stamps the `added` field (`YYYY-MM-DD`) on every app in `apps/*.json` that lacks it, using git history as the source of truth.

```bash
$ python scripts/backfill_added.py            # dry-run: show what would change
$ python scripts/backfill_added.py --run      # write the files
```

For each app without `added` it runs `git log -S "<source>" --format=%ad --date=short -- apps/` and takes the oldest date for that URL. Apps whose URL is not found in git history fall back to the bulk-import commit date. Repeated source URLs share the same date.

### Parameters

| Argument | Description |
|----------|-------------|
| `--run` | Actually write the JSON files. Without it, the script only prints what it would change (dry-run). |

---

## curate.py

```bash
# 1. Check health of every app and write the facts into curate/cache.json
$ python scripts/curate.py check --dir apps/test
#    ^ use --dir apps to target the real catalogue

# 2. Preview what would be removed / cleaned, without touching anything
$ python scripts/curate.py remove --dir apps/test --dry-run

# 3. Apply the removals, clean dead stores and log them to REMOVED.md
$ python scripts/curate.py remove --dir apps/test
```

### Data model (three layers)

`check` never touches `apps/*.json` and never touches your manual decisions. It only
writes machine-computed facts into `curate/cache.json`.

| Layer | File | Written by | Purpose |
|-------|------|------------|---------|
| Source | `apps/*.json` | `add.py` (`remove` deletes here) | Identity only: name, description, source, stores |
| Cache | `curate/cache.json` | `curate.py check` | Machine facts: last commit, archived, license, store status. Regenerated every run |
| Overrides | `curate/overrides.json` | You | Human decisions, versioned, NEVER overwritten |

Merge rule: **overrides > cache > source**.

The status is never stored: it is **derived at read time** from the effective
(merged) facts by `build.py` / `curate.py remove`.

### Manual review (your fix survives re-checks)

The whole point: if you manually fix an app, `curate.py check` will NOT clobber it.
Add an entry to `curate/overrides.json` keyed by the app `source`:

```json
{
  "https://gitlab.com/xynngh/YetAnotherCallBlocker": {
    "fields": { "license": "GPL-3.0", "is_foss": true },
    "reason": "GitLab API does not expose the license; verified in the README."
  }
}
```

- `fields` wins over any computed value, forever.
- Pinning `status` in `fields` **disables automatic removal** for that app (you own it).

### Parameters

| Argument | Description |
|----------|-------------|
| `command` | `check` or `remove` (required) |
| `--dir PATH` | Directory with the `.json` files (default: `apps/test`) |
| `--dry-run` | Only for `remove`: show the result without modifying files |

### Status values

The status is derived from the effective facts. Badge colors are defined in
`scripts/build.py` ([`STATUS_BADGES`](build.py)).

| Status | Meaning |
|--------|---------|
| `healthy` | Active repo, FOSS license and stores reachable |
| `inactive` | No commits in the last 730 days (removed only when ALL stores return a real HTTP 404 and the repo publishes no releases) |
| `archived` | Repo was archived (removed when also inactive, all stores return 404 and no releases) |
| `no_open_code` | License not detected as FOSS (manual review required, NOT removed) |
| `broken_link` | Some store returns 404 (informational, NOT removed on its own) |
| `repo_gone` | Source repository returns 404 (direct removal candidate) |
| *(no badge)* | Never checked yet — no data in the cache |

### Automatic removal criteria

Only criteria the network cannot lie about:

1. `status == "repo_gone"` — the source code no longer exists.
2. `status == "archived"` **or** `"inactive"` + no commits in 730 days + **all**
   stores return a real HTTP 404 + the repo publishes **no releases**. Only a real
   404 counts; a timeout or connection error is "unknown" and never counts as dead.
   An app is kept if any store works or the repo still ships a release (installable).

If only *some* stores return 404, the app is **kept** and just those dead store
links are suppressed via an override. Apps with a human-pinned `status` are never
auto-removed.

### One-time migration

If the repo was previously curated with the old layout (computed fields inline in
`apps/*.json`), run once to move them into the cache:

```bash
$ python scripts/migrate_cache.py --dir apps
```

### GitHub token (optional)

Without a token you get the anonymous GitHub limit of 60 req/h, which will leave most of the catalogue `unchecked`.

```bash
# either a .env file at the repo root
$ echo "GITHUB_TOKEN=ghp_..." > .env

# or an environment variable
$ export GITHUB_TOKEN=ghp_...
```

Minimal scope: `public_repo` (read only). On a fine-grained token, only `Contents: Read-only` and `Metadata: Read-only` for the repositories you want to check.