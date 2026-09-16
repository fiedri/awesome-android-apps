#!/usr/bin/env python3
import argparse, difflib, json, re, sys
from pathlib import Path

EMOJI_PLACEHOLDER = "\u2753"
NAME_CELL_RE = re.compile(r"\[(?:\*\*)?(.+?)(?:\*\*)?\]\((https?://[^)\s]+)\)")
PLAYSTORE_RE = re.compile(r"https://play\.google\.com/store/apps/details\?id=[A-Za-z0-9_.]+")
UNICODE_ESCAPE_RE = re.compile(r"\\U[0-9A-Fa-f]{8}")


def unescape_unicode(match):
    return chr(int(match.group(0)[2:], 16))


def normalize_url(url):
    normalized = url.strip().lower()
    if normalized.startswith("http://github.com/"):
        normalized = "https://github.com/" + normalized[len("http://github.com/") :]
    normalized = re.split(r"[?#]", normalized)[0]
    normalized = normalized.rstrip("/")
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    return normalized


def normalize_category(text):
    normalized = re.sub(r"[_\-]+", " ", text.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if normalized.endswith("s"):
        normalized = normalized[:-1]
    return normalized


def category_tokens(normalized):
    return [token for token in normalized.split(" ") if len(token) >= 4]


def match_score(source_norm, target_norm):
    source_tokens = set(category_tokens(source_norm))
    target_tokens = set(category_tokens(target_norm))
    shared = source_tokens & target_tokens
    if shared:
        union = source_tokens | target_tokens
        return 1.0 + len(shared) / len(union), True
    return difflib.SequenceMatcher(None, source_norm, target_norm).ratio(), False


def slugify(stem):
    return re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")


def humanize(stem):
    words = re.split(r"[_\-]+", stem)
    return " ".join(word.title() if word != "and" else word for word in words if word)


def header_title(path):
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped[2:].strip()
            if title.lower().endswith(" apps"):
                title = title[:-5].rstrip()
            return title or None
    return None


def load_json_tolerant(raw):
    try:
        return json.loads(raw), False
    except json.JSONDecodeError:
        return json.loads(UNICODE_ESCAPE_RE.sub(unescape_unicode, raw)), True


def detect_style(raw):
    indent = 4
    for line in raw.splitlines()[1:]:
        if line.strip():
            indent = len(line) - len(line.lstrip())
            break
    return indent, raw.endswith("\n")


def load_targets(apps_dir):
    files = sorted(path for path in apps_dir.iterdir() if path.suffix == ".json" and path.is_file())
    entries = []
    existing_urls = set()
    repaired = []
    for path in files:
        raw = path.read_text(encoding="utf-8")
        data, fixed = load_json_tolerant(raw)
        if fixed:
            repaired.append(path)
        data.setdefault("apps", [])
        indent, trailing = detect_style(raw)
        entries.append({
            "path": path,
            "stem": path.stem,
            "title": data.get("title") or path.stem,
            "data": data,
            "indent": indent,
            "trailing": trailing,
        })
        for app in data.get("apps", []):
            source = app.get("source")
            if source:
                existing_urls.add(normalize_url(source))
    return entries, existing_urls, repaired


def parse_source_rows(path):
    rows = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        first = cells[0]
        if not first or re.fullmatch(r"[:,\s\-]+", first):
            continue
        match = NAME_CELL_RE.match(first)
        if not match:
            if first.casefold() not in ("app name",):
                rows.append(("unparseable", (path.name, line)))
            continue
        name = match.group(1).strip()
        url = match.group(2).strip()
        description = cells[1].strip()
        playstore_match = PLAYSTORE_RE.search(line)
        playstore = playstore_match.group(0) if playstore_match else None
        rows.append(("app", (name, url, description, playstore)))
    return rows


def write_json(path, data, indent, trailing):
    content = json.dumps(data, indent=indent, ensure_ascii=True)
    if trailing:
        content += "\n"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Import apps from open-source-android-apps categories into apps/*.json")
    parser.add_argument("--source-dir", default="../open-source-android-apps")
    parser.add_argument("--target-dir", default=".")
    parser.add_argument("--dry-run", action="store_true", help="print the plan without writing anything")
    parser.add_argument("--map-file", default=None, help="JSON mapping source_category_stem -> target_json_stem")
    parser.add_argument("--min-score", type=float, default=0.53, help="minimum auto-match score threshold")
    parser.add_argument("--new-category", action="store_true", default=True, help="create categories that match nothing")
    parser.add_argument("--no-new-category", action="store_false", dest="new_category")
    args = parser.parse_args(argv)

    source_dir = Path(args.source_dir)
    target_dir = Path(args.target_dir)
    categories_dir = source_dir / "categories"
    apps_dir = target_dir / "apps"

    if not categories_dir.is_dir():
        sys.exit(f"ERROR: source categories dir not found: {categories_dir}")
    if not apps_dir.is_dir():
        sys.exit(f"ERROR: target apps dir not found: {apps_dir}")

    target_entries, existing_urls, repaired_targets = load_targets(apps_dir)
    target_by_stem = {entry["stem"]: entry for entry in target_entries}

    forced = {}
    if args.map_file:
        map_path = Path(args.map_file)
        forced = json.loads(map_path.read_text(encoding="utf-8"))
        for source_stem, target_stem in forced.items():
            if target_stem not in target_by_stem:
                sys.exit(f"ERROR: map file target '{target_stem}' does not exist (source '{source_stem}')")

    all_seen = set(existing_urls)
    source_files = sorted(categories_dir.glob("*.md"))
    source_stems = {path.stem for path in source_files}

    additions = {}
    new_titles = {}
    lines = []
    totals = {"parsed": 0, "dupes": 0, "added": 0, "non_github": 0}
    warnings = []
    unparseable = []
    emoji_warnings = []

    for path in source_files:
        stem = path.stem
        source_norm = normalize_category(stem)
        dest = None
        is_new = False
        if stem in forced:
            dest = forced[stem]
        else:
            best_target = None
            best_score = 0.0
            best_token = False
            for entry in target_entries:
                stem_score, stem_token = match_score(source_norm, normalize_category(entry["stem"]))
                title_score, title_token = match_score(source_norm, normalize_category(entry["title"]))
                if title_score > stem_score:
                    candidate, token_based = title_score, title_token
                else:
                    candidate, token_based = stem_score, stem_token
                if candidate > best_score:
                    best_score = candidate
                    best_token = token_based
                    best_target = entry
            if best_target is not None and best_score >= args.min_score:
                dest = best_target["stem"]
                if not best_token and best_score < 0.9:
                    warnings.append(f"low-confidence match: {stem} -> {dest} (score {best_score:.3f}, ratio only)")
            elif args.new_category:
                dest = slugify(stem)
                if dest not in target_by_stem:
                    is_new = True
                    new_titles[dest] = header_title(path) or humanize(stem)
            else:
                lines.append(f"{stem} -> (no match, new categories disabled) | +0 added | -0 skipped(dupes)")
                warnings.append(f"no match for '{stem}' and new categories disabled")
                continue

        host = target_by_stem.get(dest)
        if is_new:
            for other in source_stems:
                if other != stem and slugify(other) == dest:
                    warnings.append(f"new category '{dest}' also derives from source '{other}'")

        rows = parse_source_rows(path)
        added = []
        dupes = 0
        for kind, payload in rows:
            if kind == "unparseable":
                unparseable.append(payload)
                continue
            name, url, description, playstore = payload
            totals["parsed"] += 1
            if not (url.startswith("https://github.com/") or url.startswith("http://github.com/")):
                totals["non_github"] += 1
                warnings.append(f"skipped non-GitHub row: {name} ({url})")
                continue
            normalized = normalize_url(url)
            if normalized in all_seen:
                dupes += 1
                continue
            all_seen.add(normalized)
            entry = {"name": name, "description": description, "source": url}
            if playstore:
                entry["playstore"] = playstore
            added.append(entry)

        totals["added"] += len(added)
        totals["dupes"] += dupes
        additions.setdefault(dest, []).extend(added)

        if is_new:
            emoji_warnings.append(dest)

        lines.append(f"{stem} -> {dest}{' [NEW]' if is_new else ''} | +{len(added)} added | -{dupes} skipped(dupes)")

        if args.dry_run and added:
            for entry in added:
                suffix = " [playstore]" if "playstore" in entry else ""
                lines.append(f"    + {entry['name']} ({entry['source']}){suffix}")

    for source_stem in forced:
        if source_stem not in source_stems:
            warnings.append(f"map file key '{source_stem}' does not match any source category")

    lines.append("")
    lines.append("=== TOTALS ===")
    lines.append(f"parsed rows: {totals['parsed']}")
    lines.append(f"skipped (dupes): {totals['dupes']}")
    lines.append(f"new apps: {totals['added']}")
    lines.append(f"skipped non-GitHub rows: {totals['non_github']}")

    if emoji_warnings:
        lines.append("")
        lines.append("=== NEW CATEGORIES (need manual emoji) ===")
        for dest in emoji_warnings:
            lines.append(f"WARNING: category needs manual emoji: {dest}")

    if unparseable:
        lines.append("")
        lines.append("=== UNPARSEABLE ROWS ===")
        for file_name, text in unparseable:
            lines.append(f"WARNING: unparseable row in {file_name}: {text}")

    if repaired_targets:
        lines.append("")
        lines.append("=== INVALID JSON IN TARGET ===")
        for path in repaired_targets:
            touched = "will be rewritten" if (not args.dry_run and path.stem in additions) else "only read"
            lines.append(f"WARNING: {path.name} contains invalid \\U escapes in emoji; {touched}")

    if warnings:
        lines.append("")
        lines.append("=== WARNINGS ===")
        for warning in warnings:
            lines.append(f"WARNING: {warning}")

    print("\n".join(lines))

    if args.dry_run:
        print()
        print("DRY RUN — nothing written.")
        return

    written = []
    for dest, apps in additions.items():
        host = target_by_stem.get(dest)
        if host is not None:
            host["data"]["apps"].extend(apps)
            write_json(host["path"], host["data"], host["indent"], host["trailing"])
        else:
            title = new_titles.get(dest, humanize(dest))
            write_json(apps_dir / f"{dest}.json", {"title": title, "emoji": EMOJI_PLACEHOLDER, "apps": apps}, 4, False)
        written.append(dest)
    print()
    print(f"written: {', '.join(sorted(written))}")


if __name__ == "__main__":
    main()