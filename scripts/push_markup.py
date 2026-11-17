#!/usr/bin/env python3
"""Push the templates in src/ to the private plugin on trmnl.com.

TRMNL cannot pull markup from a repository: the plugin's only link to this one
is its polling URL, which carries the data. The templates are a copy, and they
drift the moment either side changes. This pushes src/ over the top of them.

    export TRMNL_API_KEY=trmnl_xxxxx     # Account > API keys, needs "content"
    python3 scripts/push_markup.py --dry-run
    python3 scripts/push_markup.py

Standard library only. The plugin is identified by plugin_setting_id in
config.json, or --plugin-setting-id.

Uses PUT /api/plugin_settings/<id>/markup/<size> from TRMNL's Account API. The
same thing is a command away if you would rather not keep a key around:

    brew install usetrmnl/tap/trmnl
    trmnl write-markup <id> markup_full < src/full.liquid
"""

import argparse
import io
import json
import os
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://trmnl.com/api"
# Cloudflare turns away urllib's default User-Agent with a 1010, so say who we are.
USER_AGENT = "trmnl-embalses/1.0 (+https://github.com/jmorrisseyd/trmnl-embalses)"

# The four views, and the size each one is stored under.
SIZES = {
    "full": "markup_full",
    "half_horizontal": "markup_half_horizontal",
    "half_vertical": "markup_half_vertical",
    "quadrant": "markup_quadrant",
}


def normalise(text):
    """TRMNL stores markup with CRLF line endings, so compare without them."""
    return text.replace("\r\n", "\n").rstrip("\n")


def call(method, path, key, payload=None):
    request = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
            **({"Content-Type": "application/json"} if payload is not None else {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
        return json.loads(body) if body else {}
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:200]
        raise SystemExit(
            f"{method} {path} -> {error.code} {error.reason}\n  {detail}\n"
            + ("  The key needs the 'content' capability to write markup.\n"
               if error.code == 403 and "capability" in detail else "")
            + ("  Check TRMNL_API_KEY; create one under Account > API keys.\n"
               if error.code == 401 else "")
        ) from error


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default=os.path.join(ROOT, "config.json"))
    parser.add_argument("--plugin-setting-id", type=int,
                        help="overrides plugin_setting_id in config.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what differs without writing anything")
    parser.add_argument("--only", choices=sorted(SIZES),
                        help="push a single view")
    args = parser.parse_args()

    key = os.environ.get("TRMNL_API_KEY")
    if not key:
        raise SystemExit("Set TRMNL_API_KEY (Account > API keys, 'content' capability).")

    setting_id = args.plugin_setting_id
    if not setting_id:
        try:
            with io.open(args.config, encoding="utf-8") as fh:
                setting_id = json.load(fh).get("plugin_setting_id")
        except (OSError, ValueError):
            setting_id = None
    if not setting_id:
        raise SystemExit(
            "No plugin to push to: add \"plugin_setting_id\" to config.json, or "
            "pass --plugin-setting-id. It is the number in the plugin's URL, "
            "trmnl.com/plugin_settings/<id>/edit.")

    views = [args.only] if args.only else list(SIZES)
    changed = unchanged = 0
    for view in views:
        size = SIZES[view]
        local = normalise(io.open(os.path.join(ROOT, "src", f"{view}.liquid"),
                                 encoding="utf-8").read())
        remote = normalise(
            call("GET", f"/plugin_settings/{setting_id}/markup/{size}", key)
            .get("data", {}).get("markup", ""))

        if local == remote:
            print(f"  {view:16} unchanged")
            unchanged += 1
            continue
        if args.dry_run:
            print(f"  {view:16} differs ({len(remote)} -> {len(local)} chars)")
            changed += 1
            continue
        call("PUT", f"/plugin_settings/{setting_id}/markup/{size}", key,
             {"content": local})
        print(f"  {view:16} pushed ({len(local)} chars)")
        changed += 1

    verb = "would change" if args.dry_run else "pushed"
    print(f"{changed} {verb}, {unchanged} already current "
          f"(plugin {setting_id})")
    if changed and not args.dry_run:
        print("Force Refresh the plugin in TRMNL to see it on the device.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
