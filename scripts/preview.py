#!/usr/bin/env python3
"""Render the four Liquid views into preview.html, to check them in a browser.

Optional development helper: needs `pip install python-liquid`. It is not used
by the GitHub Action, and TRMNL itself never runs it.

    python3 scripts/preview.py                     # all reservoirs in the payload
    python3 scripts/preview.py --limit 1           # what a single reservoir looks like
"""

import argparse
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

PAGE = """<!DOCTYPE html>
<html class="trmnl">
<head>
  <meta charset="utf-8" />
  <title>trmnl-embalses preview</title>
  <link rel="stylesheet" href="https://trmnl.com/css/latest/plugins.css" />
  <script src="https://trmnl.com/js/latest/plugins.js"></script>
  <style>
    body {{ margin: 0; padding: 0; background: #4b5563; font-family: sans-serif; }}
    .preview {{ display: flex; flex-direction: column; gap: 10px; align-items: flex-start; }}
    .preview__case {{ color: #fff; font: 12px/1.4 ui-monospace, monospace; }}
    .screen {{ background: #fff; }}
  </style>
</head>
<body class="environment trmnl">
  <div class="preview">{cases}</div>
</body>
</html>
"""

CASE = """
    <div class="preview__case">
      <div>{name}</div>
      <div class="screen screen--og screen--1bit">{open}{body}{close}</div>
    </div>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", default=os.path.join(ROOT, "docs", "trmnl.json"))
    parser.add_argument("--out", default=os.path.join(ROOT, "preview.html"))
    parser.add_argument("--limit", type=int, help="only render the first N reservoirs")
    args = parser.parse_args()

    with open(args.data, encoding="utf-8") as fh:
        data = json.load(fh)
    if args.limit:
        data["reservoirs"] = data["reservoirs"][: args.limit]
        data["count"] = len(data["reservoirs"])

    env = Environment()
    cases = []
    for view, mashup in VIEWS:
        with open(os.path.join(ROOT, "src", f"{view}.liquid"), encoding="utf-8") as fh:
            template = env.from_string(fh.read())
        cases.append(CASE.format(
            name=f"{view} — {len(data['reservoirs'])} reservoir(s)",
            open=f'<div class="mashup {mashup}">' if mashup else "",
            close="</div>" if mashup else "",
            body=template.render(**data),
        ))

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(PAGE.format(cases="".join(cases)))
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
