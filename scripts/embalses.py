#!/usr/bin/env python3
"""Scrape embalses.net and build the JSON payload a TRMNL plugin polls.

Two subcommands:

    search <term>   look a reservoir up by name and print its id
    build           fetch the reservoirs listed in config.json -> docs/trmnl.json

Standard library only, so the GitHub Action needs no pip install.

The pages are plain server-rendered HTML. Every figure on a reservoir page
lives in the same little structure, which is also what the national summary on
the home page uses:

    <div class="FilaSeccion">
        <div class="Campo">Capacidad:</div>
        <div class="Resultado">437</div>
        <div class="Unidad">hm<sup>3</sup></div>
        <div class="Resultado">&nbsp;</div>
    </div>

so one row parser covers both.
"""

import argparse
import html
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone

BASE = "https://www.embalses.net"
USER_AGENT = (
    "trmnl-embalses/1.0 (+https://github.com/jmorrisseyd/trmnl-embalses) "
    "python-urllib"
)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, ".cache")


# --------------------------------------------------------------------------
# fetching
# --------------------------------------------------------------------------

def fetch(url, cache_seconds=0, retries=3):
    """GET a page, optionally serving it from .cache/ during development."""
    cache_path = None
    if cache_seconds > 0:
        os.makedirs(CACHE_DIR, exist_ok=True)
        cache_path = os.path.join(CACHE_DIR, re.sub(r"[^a-zA-Z0-9]+", "_", url) + ".html")
        if os.path.exists(cache_path) and time.time() - os.path.getmtime(cache_path) < cache_seconds:
            with open(cache_path, encoding="utf-8") as fh:
                return fh.read()

    last_error = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={
                "User-Agent": USER_AGENT,
                "Accept-Language": "es-ES,es;q=0.9",
            })
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8", errors="replace")
            break
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            last_error = error
            if attempt == retries - 1:
                raise RuntimeError(f"could not fetch {url}: {error}") from error
            time.sleep(2 * (attempt + 1))
    else:  # pragma: no cover - the loop always breaks or raises
        raise RuntimeError(f"could not fetch {url}: {last_error}")

    if cache_path:
        with open(cache_path, "w", encoding="utf-8") as fh:
            fh.write(body)
    return body


# --------------------------------------------------------------------------
# HTML helpers
# --------------------------------------------------------------------------

TAG_RE = re.compile(r"<[^>]+>")


def text_of(fragment):
    """Strip tags and entities from an HTML fragment, collapsing whitespace."""
    text = TAG_RE.sub(" ", fragment)
    text = html.unescape(text).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def fold(text):
    """Lowercase and strip accents, for comparing labels and search terms."""
    stripped = unicodedata.normalize("NFD", text)
    stripped = "".join(c for c in stripped if unicodedata.category(c) != "Mn")
    return stripped.lower()


def to_number(text):
    """'35.073' -> 35073.0, '62,58' -> 62.58, '' -> None (Spanish notation)."""
    cleaned = text.replace(".", "").replace(",", ".").replace("+", "").strip()
    if not re.fullmatch(r"-?\d+(\.\d+)?", cleaned or ""):
        return None
    return float(cleaned)


def sections(page):
    """Split a page into its <div class="SeccionCentral"> blocks, by title."""
    found = {}
    for chunk in page.split('<div class="SeccionCentral">')[1:]:
        match = re.search(r'class="SeccionCentral_TituloTexto">(.*?)</div>', chunk, re.S)
        title = text_of(match.group(1)) if match else ""
        found.setdefault(fold(title), chunk)
    return found


def stat_rows(section):
    """Yield (label, [values]) for each FilaSeccion row of a section."""
    for chunk in section.split('class="FilaSeccion"')[1:]:
        label_match = re.search(r'class="Campo(?:Inf)?">(.*?)</div>', chunk, re.S)
        if not label_match:
            continue
        label = text_of(label_match.group(1)).rstrip(":")
        values = [
            text_of(value)
            for value in re.findall(r'class="Resultado(?:Inf)?">(.*?)</div>', chunk, re.S)
        ]
        yield label, values


# --------------------------------------------------------------------------
# parsing a stat block (a reservoir, or the national summary)
# --------------------------------------------------------------------------

def parse_stats(section):
    """Pull the water figures out of a 'Agua embalsada' style section."""
    stats = {}
    for label, values in stat_rows(section):
        key = fold(label)
        first = to_number(values[0]) if values else None
        second = to_number(values[1]) if len(values) > 1 else None

        if key.startswith("agua embalsada"):
            stats["volume_hm3"] = first
            stats["percent"] = second
            date_match = re.search(r"\((\d{2})-(\d{2})-(\d{4})\)", label)
            if date_match:
                day, month, year = date_match.groups()
                stats["as_of"] = f"{year}-{month}-{day}"
                stats["as_of_label"] = f"{day}/{month}/{year}"
        elif key.startswith("variacion semana"):
            stats["change_hm3"] = first
            stats["change_percent"] = second
        elif key.startswith("capacidad"):
            stats["capacity_hm3"] = first
        elif key.startswith("misma semana (med"):
            stats["avg10_hm3"] = first
            stats["avg10_percent"] = second
        elif key.startswith("misma semana"):
            stats["last_year_hm3"] = first
            stats["last_year_percent"] = second
            year_match = re.search(r"\((\d{4})\)", label)
            if year_match:
                stats["last_year_label"] = year_match.group(1)
    return stats


INFO_KEYS = {
    "cuenca": "basin",
    "provincia": "province",
    "rio": "river",
    "municipio presa": "municipality",
    "tipo de presa": "dam_type",
}


def parse_info(page):
    """Read the 'Datos del Embalse' box: basin, province, river, municipality."""
    section = sections(page).get("datos del embalse")
    if not section:
        return {}
    info = {}
    for label, values in stat_rows(section):
        key = INFO_KEYS.get(fold(label).rstrip(":"))
        if key and values and values[0]:
            info[key] = values[0]
    return info


def parse_reservoir(page, reservoir_id, url):
    """Turn a /pantano-<id>-<slug>.html page into a dict of figures."""
    blocks = sections(page)
    name = ""
    section = None
    for title, chunk in blocks.items():
        if title.startswith("embalse:"):
            name = title.split(":", 1)[1].strip()
            match = re.search(r'class="SeccionCentral_TituloTexto">(.*?)</div>', chunk, re.S)
            if match:
                name = text_of(match.group(1)).split(":", 1)[1].strip()
            section = chunk
            break
    if section is None:
        raise RuntimeError(f"no reservoir block found on {url}")

    record = {"id": reservoir_id, "name": name, "url": url}
    record.update(parse_stats(section))
    record.update(parse_info(page))
    if record.get("volume_hm3") is None:
        raise RuntimeError(f"no water figures found on {url}")
    return record


def parse_national(page):
    """Read the Spain-wide totals off the home page."""
    section = sections(page).get("agua embalsada en espana")
    if not section:
        raise RuntimeError("no national block found on the home page")
    national = {"name": "España", "url": BASE}
    national.update(parse_stats(section))
    return national


# --------------------------------------------------------------------------
# the reservoir index (used by `search`)
# --------------------------------------------------------------------------

BASIN_LINK_RE = re.compile(r'href="(https://www\.embalses\.net/cuenca-\d+-[a-z0-9-]+\.html)"')
RESERVOIR_LINK_RE = re.compile(
    r'<tr class="ResultadoCampo">(.*?)</tr>', re.S)
PANTANO_RE = re.compile(r'href="[^"]*?/pantano-(\d+)-([a-z0-9-]+)\.html"[^>]*>(.*?)</a>', re.S)


def build_index(cache_seconds=21600):
    """List every reservoir by walking the 16 basin pages (not 400 detail pages)."""
    home = fetch(BASE + "/", cache_seconds=cache_seconds)
    basins = sorted(set(BASIN_LINK_RE.findall(home)))
    index = []
    seen = set()
    for basin_url in basins:
        page = fetch(basin_url, cache_seconds=cache_seconds)
        basin_name = ""
        title = re.search(r'class="SeccionCentral_TituloTexto">Cuenca (.*?)\(', page, re.S)
        if title:
            basin_name = text_of(title.group(1))
        for row in RESERVOIR_LINK_RE.findall(page):
            link = PANTANO_RE.search(row)
            if not link:
                continue
            reservoir_id = int(link.group(1))
            if reservoir_id in seen:
                continue
            seen.add(reservoir_id)
            cells = [text_of(cell) for cell in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
            numbers = [to_number(cell) for cell in cells[1:4]] + [None, None, None]
            index.append({
                "id": reservoir_id,
                "slug": link.group(2),
                "name": text_of(link.group(3)).replace("[+]", "").strip(),
                "basin": basin_name,
                "capacity_hm3": numbers[0],
                "volume_hm3": numbers[1],
                "change_hm3": numbers[2],
            })
        time.sleep(0.5)
    index.sort(key=lambda entry: fold(entry["name"]))
    return index


def reservoir_url(reservoir_id, slug):
    return f"{BASE}/pantano-{reservoir_id}-{slug}.html"


def resolve_url(reservoir_id, index_cache={}, cache_seconds=21600):
    """Find a reservoir's canonical URL from the index (its slug is in the path)."""
    if not index_cache:
        for entry in build_index(cache_seconds=cache_seconds):
            index_cache[entry["id"]] = entry
    entry = index_cache.get(int(reservoir_id))
    if not entry:
        raise RuntimeError(
            f"reservoir {reservoir_id} is not listed on embalses.net; "
            f"run `embalses.py search <name>` to find the right id"
        )
    return reservoir_url(entry["id"], entry["slug"])


# --------------------------------------------------------------------------
# formatting for the display
# --------------------------------------------------------------------------

def format_number(value, decimals=0, locale="es", signed=False):
    """Render a number the Spanish way (1.234,5) or the English way (1,234.5)."""
    if value is None:
        return "—"
    text = f"{abs(value):,.{decimals}f}"
    if locale == "es":
        text = text.translate(str.maketrans({",": ".", ".": ","}))
    if value < 0:
        return "-" + text
    if signed and value > 0:
        return "+" + text
    return text


def decorate(record, locale="es"):
    """Add the pre-formatted strings and derived figures the templates use."""
    percent = record.get("percent")
    if percent is None and record.get("capacity_hm3"):
        percent = 100.0 * record["volume_hm3"] / record["capacity_hm3"]
        record["percent"] = round(percent, 2)

    change = record.get("change_hm3")
    record["trend"] = "flat" if not change else ("up" if change > 0 else "down")
    record["trend_glyph"] = {"up": "▲", "down": "▼", "flat": "▬"}[record["trend"]]

    avg10 = record.get("avg10_percent")
    if percent is not None and avg10 is not None:
        record["vs_avg10_points"] = round(percent - avg10, 1)
        record["vs_avg10_text"] = format_number(record["vs_avg10_points"], 1, locale, signed=True)
    last_year = record.get("last_year_percent")
    if percent is not None and last_year is not None:
        record["vs_last_year_points"] = round(percent - last_year, 1)
        record["vs_last_year_text"] = format_number(record["vs_last_year_points"], 1, locale, signed=True)

    # Widths for the fill bar and the ten-year-average marker, clamped so a
    # reservoir sitting above capacity cannot overflow its track.
    record["bar_percent"] = round(min(max(percent or 0, 0), 100), 1)
    if avg10 is not None:
        record["avg10_bar_percent"] = round(min(max(avg10, 0), 100), 1)

    record["percent_text"] = format_number(percent, 1, locale)
    record["percent_round"] = format_number(percent, 0, locale)
    record["volume_text"] = format_number(record.get("volume_hm3"), 0, locale)
    record["capacity_text"] = format_number(record.get("capacity_hm3"), 0, locale)
    record["change_text"] = format_number(change, 0, locale, signed=True)
    record["change_percent_text"] = format_number(record.get("change_percent"), 1, locale, signed=True)
    record["last_year_text"] = format_number(record.get("last_year_percent"), 1, locale)
    record["avg10_text"] = format_number(avg10, 1, locale)
    return record


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def command_search(args):
    index = build_index()
    needle = fold(" ".join(args.term))
    matches = [entry for entry in index if needle in fold(entry["name"])] if needle else index
    if not matches:
        print(f"No reservoir matches {' '.join(args.term)!r}", file=sys.stderr)
        return 1
    print(f"{'id':>5}  {'name':<32} {'basin':<22} {'cap hm3':>8} {'now hm3':>8}  fill")
    for entry in matches:
        capacity = entry["capacity_hm3"] or 0
        volume = entry["volume_hm3"] or 0
        fill = f"{100 * volume / capacity:5.1f}%" if capacity else "    —"
        print(f"{entry['id']:>5}  {entry['name'][:32]:<32} {entry['basin'][:22]:<22} "
              f"{capacity:>8.0f} {volume:>8.0f}  {fill}")
    print(f"\n{len(matches)} reservoir(s). Put the ids in config.json.", file=sys.stderr)
    return 0


def command_build(args):
    with open(args.config, encoding="utf-8") as fh:
        config = json.load(fh)

    ids = [int(value) for value in args.ids.split(",")] if args.ids else config.get("reservoirs", [])
    if not ids:
        print("config.json lists no reservoirs", file=sys.stderr)
        return 1
    locale = config.get("number_format", "es")
    cache_seconds = args.cache

    home = fetch(BASE + "/", cache_seconds=cache_seconds)
    national = decorate(parse_national(home), locale)

    reservoirs = []
    for reservoir_id in ids:
        url = resolve_url(reservoir_id, cache_seconds=cache_seconds)
        page = fetch(url, cache_seconds=cache_seconds)
        reservoirs.append(decorate(parse_reservoir(page, int(reservoir_id), url), locale))
        time.sleep(0.5)

    # A combined figure, so a screen showing several reservoirs can also show
    # what they hold between them.
    capacity = sum(r["capacity_hm3"] or 0 for r in reservoirs)
    volume = sum(r["volume_hm3"] or 0 for r in reservoirs)
    total = decorate({
        "name": config.get("title", "Total"),
        "capacity_hm3": capacity,
        "volume_hm3": volume,
        "percent": round(100 * volume / capacity, 2) if capacity else None,
        "change_hm3": sum(r.get("change_hm3") or 0 for r in reservoirs),
    }, locale)

    as_of = next((r.get("as_of") for r in reservoirs if r.get("as_of")), national.get("as_of"))
    as_of_label = next(
        (r.get("as_of_label") for r in reservoirs if r.get("as_of_label")),
        national.get("as_of_label"),
    )

    payload = {
        "title": config.get("title", "Embalses"),
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "as_of": as_of,
        "as_of_label": as_of_label,
        "source": BASE,
        "count": len(reservoirs),
        "reservoirs": reservoirs,
        "total": total,
        "national": national,
    }

    # embalses.net moves once a week, so most runs produce the same figures with
    # a fresh timestamp. Keep the old timestamp in that case, and the daily
    # Action has nothing to commit instead of committing noise.
    previous = None
    if os.path.exists(args.out):
        try:
            with open(args.out, encoding="utf-8") as fh:
                previous = json.load(fh)
        except (OSError, ValueError):
            previous = None
    if previous:
        before = {k: v for k, v in previous.items() if k != "generated_at"}
        after = {k: v for k, v in payload.items() if k != "generated_at"}
        if before == after:
            payload["generated_at"] = previous.get("generated_at", payload["generated_at"])

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    state = "unchanged" if previous and before == after else "updated"
    print(f"Wrote {args.out} ({state}): {len(reservoirs)} reservoir(s), data of {as_of_label}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    subparsers = parser.add_subparsers(dest="command", required=True)

    search = subparsers.add_parser("search", help="find a reservoir id by name")
    search.add_argument("term", nargs="*", help="part of the reservoir name")
    search.set_defaults(func=command_search)

    build = subparsers.add_parser("build", help="write the TRMNL JSON payload")
    build.add_argument("--config", default=os.path.join(ROOT, "config.json"))
    build.add_argument("--out", default=os.path.join(ROOT, "docs", "trmnl.json"))
    build.add_argument("--ids", help="comma separated ids, overriding config.json")
    build.add_argument("--cache", type=int, default=0,
                       help="serve pages from .cache/ for N seconds (development)")
    build.set_defaults(func=command_build)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
