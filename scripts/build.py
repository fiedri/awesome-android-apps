import functools, json, pathlib, re
from utils import read_file, load_datastore, effective

# status -> shield badge (shared with curate.py statuses)
STATUS_BADGES = {
    "healthy": "https://img.shields.io/badge/status-healthy-success",
    "inactive": "https://img.shields.io/badge/status-inactive-yellow",
    "archived": "https://img.shields.io/badge/status-archived-inactive",
    "no_open_code": "https://img.shields.io/badge/status-no_open_code-orange",
    "broken_link": "https://img.shields.io/badge/status-broken_link-critical",
    "repo_gone": "https://img.shields.io/badge/status-repo_gone-critical",
    "unchecked": "https://img.shields.io/badge/status-unchecked-lightgrey",
}

STATUS_INFO = {
    "healthy": "Repository active, FOSS license and stores reachable.",
    "inactive": "No commits in the last 730 days (informational, not removed).",
    "archived": "Repository archived by its maintainers.",
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


def build_category(cat):
    with cat.open("r") as f:
        cat_json = json.load(f)

    md_file = categories_dir / (cat.stem + ".md")
    with md_file.open("w") as f:
        lines = [
            f'# {cat_json.get("emoji")} {cat_json.get("title")}',
            "[`< go back home`](../README.md)",
            "",
            "| App | Status | Description | Stars | Last commit | Links |",
            "|-----|--------|-------------|-------|-------------|-------|",
        ]

        for app in cat_json.get("apps"):
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
            badge_commit = (
                f"![last commit]({last_commit_link})" if last_commit_link else ""
            )
            link_source = f'[`[source]`]({source} "source")'
            link_fdroid = f'[`[f-droid]`]({fdroid} "f-droid")' if fdroid else ""
            link_playstore = (
                f'[`[playstore]`]({playstore} "playstore")' if playstore else ""
            )
            link_website = f'[`[website]`]({website} "website")' if website else ""

            safe_description = description.replace("|", "\\|")
            links = " ".join(filter(None, [link_source, link_fdroid, link_playstore, link_website]))
            lines.append(
                f"| **{name}** | {status_badge(merged.get('status'))} | {safe_description} | {badge_stars} | {badge_commit} | {links} |"
            )

        f.write("\n".join(lines))


def build_readme():
    readme_contents = (root / "README.md").open("r").read()

    app_count_md = f'<img src="https://img.shields.io/badge/{n_apps}-apps-red?style=for-the-badge" alt="App count"/>'
    readme_contents = replace_chunk(readme_contents, "apps-count", app_count_md)

    sorted_categories = list(categories)
    sorted_categories.sort()

    toc_lines = [""]
    for category in sorted_categories:
        with category.open("r") as f:
            json_cat = json.load(f)
            title = json_cat.get("title")
            emoji = json_cat.get("emoji")
        link = category.stem
        toc_lines.append(f"- [{emoji} {title}](categories/{link}.md)")
    readme_contents = replace_chunk(
        readme_contents, "table-of-contents", "\n".join(toc_lines)
    )

    readme_contents = replace_chunk(
        readme_contents, "status-legend", build_status_legend()
    )

    (root / "README.md").open("w").write(readme_contents)


if __name__ == "__main__":
    root = pathlib.Path(__file__).parent.parent.resolve()
    scripts_dir = root / "scripts"
    json_dir = root / "apps"
    categories_dir = root / "categories"

    cache = load_datastore(root / "curate" / "cache.json")
    overrides = load_datastore(root / "curate" / "overrides.json")

    if not categories_dir.exists():
        pathlib.Path.mkdir(categories_dir)

    categories = parse_categories()
    n_apps = count_apps()
    build_readme()
    for category in categories:
        build_category(category)
