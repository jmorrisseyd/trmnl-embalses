#!/usr/bin/env python3
"""Build docs/paste.html: every block that has to be pasted into TRMNL, with a
copy button on each, in the order the plugin settings ask for them.

Setting the plugin up means copying six things out of this repository and into
TRMNL's forms. Reading them off GitHub means five files and a lot of scrolling,
so this collects them onto one page.

    python3 scripts/paste_page.py

Open the result locally (`open docs/paste.html`) or serve it from GitHub Pages.
Standard library only, like the rest.
"""

import html
import io
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_REPO = "jmorrisseyd/trmnl-embalses"

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>trmnl-embalses · paste into TRMNL</title>
<style>
  :root {{
    --ink: #16130f; --dim: #6b6257; --line: #ddd5c8;
    --bg: #faf7f2; --card: #fff; --accent: #b4472a;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; padding: 32px 20px 80px; background: var(--bg); color: var(--ink);
         font: 16px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
  main {{ max-width: 860px; margin: 0 auto; }}
  h1 {{ font-size: 26px; margin: 0 0 4px; letter-spacing: -0.01em; }}
  .sub {{ color: var(--dim); margin: 0 0 28px; }}
  .step {{ background: var(--card); border: 1px solid var(--line); border-radius: 10px;
           margin: 0 0 18px; overflow: hidden; }}
  .step__head {{ display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap;
                 padding: 14px 16px; border-bottom: 1px solid var(--line); }}
  .step__n {{ width: 24px; height: 24px; flex: none; border-radius: 50%; background: var(--ink);
              color: var(--card); font-size: 13px; font-weight: 600; text-align: center;
              line-height: 24px; align-self: center; }}
  .step__where {{ font-weight: 600; }}
  .step__what {{ color: var(--dim); font-size: 14px; }}
  .step__file {{ margin-left: auto; color: var(--dim); font-size: 13px;
                 font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
  .step__body {{ position: relative; }}
  pre {{ margin: 0; padding: 14px 16px; max-height: 260px; overflow: auto; background: #fbfaf8;
         font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; white-space: pre;
         -moz-tab-size: 2; tab-size: 2; }}
  /* In the header, not floating over the code: a long first line would run
     underneath it, and scrolling the block would drag more text under it. */
  .copy {{ margin-left: 12px; padding: 7px 14px; cursor: pointer; align-self: center;
           border: 1px solid var(--line); border-radius: 6px; background: var(--card);
           color: var(--ink); font: 600 13px/1 inherit; font-family: inherit; }}
  .copy:hover {{ border-color: var(--ink); }}
  .copy[data-done="1"] {{ background: var(--ink); color: var(--card); border-color: var(--ink); }}
  .note {{ background: #fff8f0; border: 1px solid #f0dcc8; border-radius: 10px;
           padding: 14px 16px; margin: 0 0 26px; font-size: 14.5px; }}
  .note b {{ color: var(--accent); }}
  footer {{ color: var(--dim); font-size: 13px; margin-top: 30px; }}
  @media (max-width: 700px) {{
    .step__file {{ margin-left: 0; }}
    .copy {{ margin-left: auto; }}
  }}
  a {{ color: var(--accent); }}
</style>
</head>
<body>
<main>
  <h1>Paste into TRMNL</h1>
  <p class="sub">The six blocks the plugin settings ask for, in order. Built from
     <code>src/</code>; figures as of {generated}.</p>

  <div class="note">
    <b>Two things that go wrong when done by eye.</b> The Form Fields box wants a
    bare YAML list: do not add a <code>custom_fields:</code> line above it. And the
    markup carries no <code>&lt;div class="view"&gt;</code> — the editor adds that.
  </div>

{steps}

  <footer>
    Data and graphs from <a href="https://www.embalses.net">Embalses.net</a> (CC BY 4.0).
    Repository: <a href="https://github.com/{repo}">{repo}</a>.
  </footer>
</main>

<script>
  // navigator.clipboard needs a secure context, which file:// is not, and it can
  // reject even where it exists — Safari and automation both do. So try it, and
  // fall back to a hidden textarea whether it is missing OR refuses.
  function copyText(text) {{
    var modern = (navigator.clipboard && window.isSecureContext)
      ? navigator.clipboard.writeText(text)
      : Promise.reject(new Error('no clipboard api'));
    return modern.catch(function () {{ return legacyCopy(text); }});
  }}

  function legacyCopy(text) {{
    return new Promise(function (resolve, reject) {{
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.style.position = 'fixed';
      ta.style.top = '-1000px';
      document.body.appendChild(ta);
      ta.select();
      var ok = false;
      try {{ ok = document.execCommand('copy'); }} catch (e) {{ ok = false; }}
      document.body.removeChild(ta);
      ok ? resolve() : reject(new Error('copy refused'));
    }});
  }}

  document.addEventListener('click', function (event) {{
    var button = event.target.closest('.copy');
    if (!button) return;
    var source = document.getElementById(button.dataset.for);
    copyText(source.textContent).then(function () {{
      button.textContent = 'Copied';
      button.dataset.done = '1';
      setTimeout(function () {{
        button.textContent = 'Copy';
        button.dataset.done = '0';
      }}, 1600);
    }}).catch(function () {{
      button.textContent = 'Select and copy';
    }});
  }});
</script>
</body>
</html>
"""

STEP = """  <section class="step">
    <div class="step__head">
      <span class="step__n">{n}</span>
      <span class="step__where">{where}</span>
      <span class="step__what">{what}</span>
      <span class="step__file">{source}</span>
      <button class="copy" data-for="{key}">Copy</button>
    </div>
    <div class="step__body">
      <pre id="{key}">{body}</pre>
    </div>
  </section>
"""


def read(path):
    with io.open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        return fh.read().rstrip("\n")


def polling_url(repo):
    """Take the URL from settings.yml, so the page cannot drift from it."""
    settings = read("src/settings.yml")
    match = re.search(r"^polling_url:\s*(\S+)", settings, re.M)
    return match.group(1) if match else (
        f"https://raw.githubusercontent.com/{repo}/main/docs/trmnl.json")


def main():
    repo = os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPO)
    as_of = "?"
    try:
        with io.open(os.path.join(ROOT, "docs", "trmnl.json"), encoding="utf-8") as fh:
            as_of = json.load(fh).get("as_of_label", "?")
    except (OSError, ValueError):
        pass

    blocks = [
        ("Polling URL", "Plugin settings, with the strategy set to Polling.",
         "src/settings.yml", polling_url(repo)),
        ("Form Fields", "The whole YAML list, with nothing above it.",
         "src/form_fields.yml", read("src/form_fields.yml")),
    ]
    for view, label in (("full", "Full"), ("half_horizontal", "Half Horizontal"),
                        ("half_vertical", "Half Vertical"), ("quadrant", "Quadrant")):
        blocks.append((f"Edit Markup → {label}", "The tab of the same name.",
                       f"src/{view}.liquid", read(f"src/{view}.liquid")))

    steps = "".join(
        STEP.format(n=i, where=html.escape(where), what=html.escape(what),
                    source=html.escape(source), key=f"block{i}",
                    body=html.escape(body))
        for i, (where, what, source, body) in enumerate(blocks, start=1))

    out = os.path.join(ROOT, "docs", "paste.html")
    with io.open(out, "w", encoding="utf-8") as fh:
        fh.write(PAGE.format(steps=steps, generated=as_of, repo=repo))
    print(f"Wrote {out}: {len(blocks)} blocks to paste")


if __name__ == "__main__":
    main()
