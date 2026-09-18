import functools, json, pathlib, re, sys
from utils import read_file, load_datastore, effective

RECENT_ADDED_COUNT = 15

# status -> shield badge (shared with curate.py statuses)
STATUS_BADGES = {
    "healthy": "https://img.shields.io/badge/status-healthy-success",
    "inactive": "https://img.shields.io/badge/status-inactive-yellow",
    "archived": "https://img.shields.io/badge/status-archived-inactive",
    "license_not_detected": "https://img.shields.io/badge/status-license_not_detected-lightgrey",
    "no_open_code": "https://img.shields.io/badge/status-no_open_code-orange",
    "broken_link": "https://img.shields.io/badge/status-broken_link-critical",
    "repo_gone": "https://img.shields.io/badge/status-repo_gone-critical",
    "unchecked": "https://img.shields.io/badge/status-unchecked-lightgrey",
}

STATUS_INFO = {
    "healthy": "Repository active, FOSS license and stores reachable.",
    "inactive": "No commits in the last 730 days (removed only when all stores return a real HTTP 404 and the repo publishes no releases).",
    "archived": "Repository archived by its maintainers (removed when inactive, all stores 404 and no releases).",
    "license_not_detected": "License field is missing or empty (needs manual review; likely FOSS but scanner didn't detect the SPDX identifier).",
    "no_open_code": "License not detected as FOSS (needs manual review).",
    "broken_link": "At least one store returns 404 (informational, not removed alone).",
    "repo_gone": "Source repository returns 404 - removed by curate.py.",
}


def status_badge(status):
    if not status:
        return ""
    url = STATUS_BADGES.get(status)
    if not url:
        return str(status)
    return f"![{status}]({url})"


def build_status_legend():
    lines = [
        "| Status | Meaning |",
        "|--------|---------|",
    ]
    for status, meaning in STATUS_INFO.items():
        lines.append(f"| {status_badge(status)} | {meaning} |")
    lines.append("| _(no badge)_ | Not checked yet by curate.py. |")
    return "\n".join(lines)


def build_recently_added():
    entries = []
    for cat in categories:
        with cat.open("r") as f:
            cat_json = json.load(f)
        for app in cat_json.get("apps", []):
            merged = effective(app, cache.get(app.get("source")), overrides.get(app.get("source")))
            added = merged.get("added")
            if not added:
                continue
            source = merged.get("source")
            name = merged.get("name")
            fdroid = merged.get("fdroid")
            playstore = merged.get("playstore")
            website = merged.get("website")
            links = " ".join(filter(None, [
                f'[`[f-droid]`]({fdroid} "f-droid")' if fdroid else "",
                f'[`[playstore]`]({playstore} "playstore")' if playstore else "",
                f'[`[website]`]({website} "website")' if website else "",
            ]))
            link_source = f'[`{name}`]({source} "link")'
            entries.append(
                (added, name.casefold(), link_source, cat, links)
            )

    lines = [
        "## Recently Added",
        "| App | Category | Added | Store |",
        "|-----|----------|-------|-------|",
    ]
    if not entries:
        print("WARNING: no app has an `added` field; Recently Added will be empty.", file=sys.stderr)
        lines.append("| _No apps with an `added` date yet._ | | | |")
        return lines

    by_date = {}
    for added, namekey, link_source, cat, links in entries:
        by_date.setdefault(added, []).append((namekey, link_source, cat, links))
    dates = sorted(by_date.keys(), reverse=True)
    top = []
    for added in dates:
        for namekey, link_source, cat, links in sorted(by_date[added]):
            top.append((added, namekey, link_source, cat, links))
            if len(top) == RECENT_ADDED_COUNT:
                break
        if len(top) == RECENT_ADDED_COUNT:
            break

    for added, namekey, link_source, cat, links in top:
        with cat.open("r") as f:
            cat_json = json.load(f)
        category_cell = f"[{cat_json.get('emoji')} {cat_json.get('title')}](#{cat.stem})"
        lines.append(f"| **{link_source}** | {category_cell} | {added} | {links} |")

    return lines


def parse_categories():
    cats = list(filter(lambda f: f.suffix == ".json", pathlib.Path.iterdir(json_dir)))

    return cats


def replace_chunk(content, marker, chunk):
    # replaces the text between the comments with the specified marker with the content
    r = re.compile(f"<!-- {marker} starts -->.*<!-- {marker} ends -->", re.DOTALL)
    chunk = f"<!-- {marker} starts -->\n{chunk}\n<!-- {marker} ends -->"
    return r.sub(chunk, content)


def count_apps():
    count = 0
    for cat in categories:
        with cat.open("r") as f:
            cat_json = json.load(f)
            count += len(cat_json.get("apps"))

    return count


def render_category(cat):
    with cat.open("r") as f:
        cat_json = json.load(f)

    lines = [
        f'<a id="{cat.stem}"></a>',
        f'## {cat_json.get("emoji")} {cat_json.get("title")}',
        "",
        "| App | Status | Description | Stars | Last commit | Links |",
        "|-----|--------|-------------|-------|-------------|-------|",
    ]

    for app in sorted(
        cat_json.get("apps"), key=lambda app: app.get("name", "").casefold()
    ):
        merged = effective(app, cache.get(app.get("source")), overrides.get(app.get("source")))
        name = merged.get("name")
        description = merged.get("description")
        source = merged.get("source")
        fdroid = merged.get("fdroid")
        playstore = merged.get("playstore")
        website = merged.get("website")

        m = re.match(
            r"https://(gitlab|github)\.com/([a-zA-Z0-9\-_.]+)/([a-zA-Z0-9\-_.]+)",
            source,
        )
        if m == None:
            stars_link = merged.get("stars_link")
            last_commit_link = merged.get("last_commit_link")
        else:
            stars_link = (
                f"https://badgen.net/{m.group(1)}/stars/{'/'.join(m.group(2,3))}"
            )
            last_commit_link = f"https://img.shields.io/{m.group(1)}/last-commit/{'/'.join(m.group(2,3))}"

        badge_stars = f"![Stars]({stars_link})" if stars_link else ""
        stars = merged.get("stars")
        if isinstance(stars, int):
            stars_cell = f"{stars:,}"
        elif badge_stars:
            stars_cell = badge_stars
        else:
            stars_cell = "—"
        badge_commit = (
            f"![last commit]({last_commit_link})" if last_commit_link else ""
        )
        link_source = f'[`{name}`]({source} "link")'
        link_fdroid = f'[`[f-droid]`]({fdroid} "f-droid")' if fdroid else ""
        link_playstore = (
            f'[`[playstore]`]({playstore} "playstore")' if playstore else ""
        )
        link_website = f'[`[website]`]({website} "website")' if website else ""

        safe_description = description.replace("|", "\\|")
        links = " ".join(filter(None, [link_fdroid, link_playstore, link_website]))
        lines.append(
            f"| **{link_source}** | {status_badge(merged.get('status'))} | {safe_description} | {stars_cell} | {badge_commit} | {links} |"
        )

    return lines + ["", "[**`^ back to top ^`**](#title)"]


def build_all_apps():
    sorted_categories = sorted(categories)

    lines = [
        "<h1 id='title'>All Apps</h1>",
        "[`< go back home`](../README.md)",
        "",
        "## Table of Contents",
        "- [🆕 Recently Added](#recently-added)",
    ]
    for category in sorted_categories:
        with category.open("r") as f:
            json_cat = json.load(f)
        lines.append(
            f"- [{json_cat.get('emoji')} {json_cat.get('title')}](#{category.stem})"
        )

    lines.append("")
    lines.extend(build_recently_added())

    lines.append("")
    lines.append("## App Status")
    lines.append(build_status_legend())

    for category in sorted_categories:
        lines.append("")
        lines.extend(render_category(category))
    content_folder = root / "content"
    content_folder.mkdir(parents=True, exist_ok=True)
    (content_folder / "ALL_APPS.md").open("w").write("\n".join(lines) + "\n")


if __name__ == "__main__":
    root = pathlib.Path(__file__).parent.parent.resolve()
    scripts_dir = root / "scripts"
    json_dir = root / "apps"

    cache = load_datastore(root / "curate" / "cache.json")
    overrides = load_datastore(root / "curate" / "overrides.json")

    categories = parse_categories()
    n_apps = count_apps()
    build_all_apps()
