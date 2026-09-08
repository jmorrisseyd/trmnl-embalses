#!/usr/bin/env python3
"""Render the four Liquid views into preview.html, to check them in a browser.

Optional development helper: needs `pip install python-liquid`. It is not used
by the GitHub Action, and TRMNL itself never runs it.

    python3 scripts/preview.py                     # all reservoirs in the payload
    python3 scripts/preview.py --limit 1           # what a single reservoir looks like
"""

import argparse
import html
import json
import os
import sys

try:
    from liquid import Environment
except ImportError:  # pragma: no cover - a helpful message beats a traceback
    sys.exit("preview.py needs python-liquid:  pip install python-liquid")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Half and quadrant views only get their size inside a mashup grid, the same
# way the device stacks two or four plugins on one screen.
VIEWS = [
    ("full", None),
    ("half_horizontal", "mashup--1Tx1B"),
    ("half_vertical", "mashup--1Lx1R"),
    ("quadrant", "mashup--2x2"),
]

# The templates themselves carry no view wrapper: TRMNL's editor supplies it,
# and its docs say the view classes are for standalone pages only. So the
# preview, being a standalone page, has to add it back.

# Each view gets its own document in an iframe. They share class names —
# .layout, and whatever custom CSS a template defines — so rendering them all in
# one page lets one template's rules reach another's markup, which is not what
# the device does and quietly misleads.
PAGE = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>trmnl-embalses preview</title>
  <style>
    body {{ margin: 0; padding: 0; background: #4b5563; font-family: sans-serif; }}
    .preview {{ display: flex; flex-direction: column; gap: 10px; align-items: flex-start; }}
    .preview__case {{ color: #fff; font: 12px/1.4 ui-monospace, monospace; }}
    iframe {{ border: 0; display: block; background: #fff; }}
  </style>
</head>
<body>
  <div class="preview">{cases}</div>
</body>
</html>
"""

FRAME = """<!DOCTYPE html>
<html class="trmnl">
<head>
  <meta charset="utf-8" />
  <link rel="stylesheet" href="https://trmnl.com/css/latest/plugins.css" />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;350;375;400;450;600;700&display=swap" rel="stylesheet" />
  <style>body {{ margin: 0; }}</style>
</head>
<body class="environment trmnl">
  <div class="screen screen--og screen--1bit">{open}<div class="view view--{view}">{body}</div>{close}</div>
</body>
</html>
"""

CASE = """
    <div class="preview__case">
      <div>{name}</div>
      <iframe width="800" height="480" srcdoc="{frame}"></iframe>
    </div>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", default=os.path.join(ROOT, "docs", "trmnl.json"))
    parser.add_argument("--out", default=os.path.join(ROOT, "preview.html"))
    parser.add_argument("--ids", help="comma separated ids to render, as the form field would")
    parser.add_argument("--limit", type=int, help="only render the first N of the selection")
    parser.add_argument("--footer", default="españa", help="footer field: españa, conjunto or ninguno")
    parser.add_argument("--heading", default="Embalses", help="heading field")
    parser.add_argument("--chart", default="no", help="chart field: si or no")
    args = parser.parse_args()

    with open(args.data, encoding="utf-8") as fh:
        data = json.load(fh)
    # Stand in for the plugin's form fields, which is where the templates read
    # the selection from (falling back to default_ids in the payload).
    selection = (args.ids or data.get("default_ids", "")).split(",")
    selection = [token.strip() for token in selection if token.strip()]
    if args.limit:
        selection = selection[: args.limit]
    data["trmnl"] = {"plugin_settings": {"custom_fields_values": {
        "reservoir_ids": ",".join(selection),
        "heading": args.heading,
        "footer": args.footer,
        "chart": args.chart,
    }}}

    env = Environment()
    cases = []
    for view, mashup in VIEWS:
        with open(os.path.join(ROOT, "src", f"{view}.liquid"), encoding="utf-8") as fh:
            template = env.from_string(fh.read())
        frame = FRAME.format(
            view=view,
            open=f'<div class="mashup {mashup}">' if mashup else "",
            close="</div>" if mashup else "",
            body=template.render(**data),
        )
        cases.append(CASE.format(
            name=f"{view} — {len(selection)} reservoir(s): {','.join(selection)} | footer={args.footer}",
            frame=html.escape(frame, quote=True),
        ))

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(PAGE.format(cases="".join(cases)))
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
