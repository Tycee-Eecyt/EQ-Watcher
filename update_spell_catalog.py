#!/usr/bin/env python3
"""Build EQ Watcher's compact P99 class spell catalog from wiki source pages."""

import argparse
import json
import re
import ssl
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


CLASSES = {
    "Bard": "Bard",
    "Cleric": "Cleric",
    "Druid": "Druid",
    "Enchanter": "Enchanter",
    "Magician": "Magician",
    "Necromancer": "Necromancer",
    "Paladin": "Paladin",
    "Ranger": "Ranger",
    "Shadow Knight": "Shadow_Knight",
    "Shaman": "Shaman",
    "Wizard": "Wizard",
}
WIKI_URL = "https://p99wiki.eqgeeks.org/{page}"
LEGACY_RAW_URL = "https://wiki.project1999.com/{page}?action=raw"


def wiki_source(page):
    request = Request(LEGACY_RAW_URL.format(page=page), headers={"User-Agent": "EQ-Watcher/1.0"})
    # The legacy mirror currently serves the same P99 wiki data with an
    # incomplete certificate chain. This updater is manual; the running app
    # never makes this insecure request.
    context = ssl._create_unverified_context()
    with urlopen(request, timeout=45, context=context) as response:
        return response.read().decode("utf-8", errors="replace")


def relevant_section(source, bard=False):
    heading = re.search(
        r"^=\s*(?:(?:Ranger|Bard)\s+)?(?:Songs|Spells)\s*=\s*$",
        source,
        re.MULTILINE | re.IGNORECASE,
    )
    if not heading:
        raise ValueError("No Songs/Spells section found")
    tail = source[heading.end():]
    next_section = re.search(r"^=\s*[^=\n].*?=\s*$", tail, re.MULTILINE)
    return tail[:next_section.start()] if next_section else tail


def parse_class(source, bard=False):
    section = relevant_section(source, bard=bard)
    levels = {}
    if bard:
        for block in re.findall(r"\{\{(?:Template:)?SongRow\b.*?\}\}", section, re.DOTALL | re.IGNORECASE):
            name = re.search(r"\|\s*name\s*=\s*([^\n|}]+)", block, re.IGNORECASE)
            level = re.search(r"\|\s*level\s*=\s*(\d+)", block, re.IGNORECASE)
            if name and level:
                levels.setdefault(str(int(level.group(1))), []).append(name.group(1).strip())
    else:
        matches = list(re.finditer(r"^==\s*Level\s+(\d+)\s*==\s*$", section, re.MULTILINE | re.IGNORECASE))
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(section)
            block = section[match.end():end]
            names = [
                item.strip()
                for item in re.findall(r"\|\s*name\s*=\s*([^\n|}]+)", block, re.IGNORECASE)
            ]
            if names:
                levels[str(int(match.group(1)))] = list(dict.fromkeys(names))
    if not levels:
        raise ValueError("No spell levels found")
    return dict(sorted(levels.items(), key=lambda item: int(item[0])))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, help="Read pre-downloaded CLASS.raw files")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "data" / "p99_spell_catalog.json",
    )
    args = parser.parse_args()

    classes = {}
    for label, page in CLASSES.items():
        source = (args.raw_dir / f"{page}.raw").read_text(errors="replace") if args.raw_dir else wiki_source(page)
        classes[label] = {
            "wiki_url": WIKI_URL.format(page=page),
            "levels": parse_class(source, bard=label == "Bard"),
        }
        count = sum(len(spells) for spells in classes[label]["levels"].values())
        print(f"{label}: {count} spells")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "Project 1999 Wiki class spell lists",
        "classes": classes,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
