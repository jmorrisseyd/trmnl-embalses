# trmnl-embalses

A [TRMNL](https://usetrmnl.com) plugin showing the state of one or more Spanish
reservoirs, with the figures scraped from [embalses.net](https://www.embalses.net).

For each reservoir the screen shows how full it is now, how much water that is
against capacity, the change over the past week, and — as a marker on the fill
bar — where the same week sits in the ten-year average. With a single reservoir
configured you get a large single reading with the comparisons spelled out; with
several you get one row each, plus a summary line for Spain as a whole.

All four TRMNL layouts are covered: `full`, `half_horizontal`, `half_vertical`
and `quadrant`.

## How it fits together

embalses.net publishes HTML, and TRMNL's polling strategy wants JSON, so
something has to sit in between:

```
embalses.net  ->  scripts/embalses.py (GitHub Action, daily)  ->  docs/trmnl.json  ->  TRMNL polls it
                        \-> data/detail.json (per-reservoir figures, refreshed weekly)
```

The Action commits the JSON back to this repository, so there is no server to
run and nothing to pay for. The payload carries **every reservoir embalses.net
reports weekly figures for** (about 374 of them), and you choose which to show
from the plugin's own settings in TRMNL — no repo edit needed to change the
screen.

## Setup

### 1. Find the ids you want

A reservoir's id is the number in its embalses.net URL — `Rules` at
`embalses.net/pantano-871-rules.html` is `871`. You can read them straight off
the site, or search by name here:

```bash
python3 scripts/embalses.py search cenajo
```

```
   id  name                             basin                   cap hm3  now hm3  fill
  795  El Cenajo                        Segura                      437      278   63.6%
```

You type those ids into the plugin's **Embalses** field in TRMNL (step 3), most
important first — the views show the first few and the narrow layouts only have
room for three.

[`config.json`](config.json) holds the fallback used when that field is left
empty, plus the number format — `es` (1.234,5) or `en` (1,234.5):

```json
{
  "title": "Embalses",
  "number_format": "es",
  "reservoirs": [795, 830, 816, 799]
}
```

Run the build once to check it works and to see the data you will get. The
first run reads every reservoir's own page to fill `data/detail.json`, which
takes a few minutes; later runs only top it up:

```bash
python3 scripts/embalses.py build
```

That writes `docs/trmnl.json`. The scraper is standard library only — no
`pip install` needed, here or in the Action.

### 2. Publish the JSON

Push this repository to GitHub and enable Actions. The workflow in
[`.github/workflows/update.yml`](.github/workflows/update.yml) runs daily at
06:20 UTC, and commits `docs/trmnl.json` only when the figures have moved. Run
it once by hand first (Actions → Update reservoir data → Run workflow).

Your polling URL is then either of these — the raw URL needs no extra setup, the
Pages URL needs Settings → Pages → Deploy from branch → `main` / `/docs`:

```
https://raw.githubusercontent.com/<user>/<repo>/main/docs/trmnl.json
https://<user>.github.io/<repo>/trmnl.json
```

### 3. Create the TRMNL plugin

Private plugins need the Developer add-on (or a BYOD licence) on your TRMNL
account. In TRMNL: **Plugins → search "Private Plugin" → Add**.

Fill in the settings form:

- **Name**: Embalses (for your eyes only)
- **Strategy**: Polling
- **Polling URL**: your `raw.githubusercontent.com` URL from step 2
- **Polling verb**: GET
- **Form Fields**: paste the whole of [`src/form_fields.yml`](src/form_fields.yml),
  exactly as it is. That box wants a bare YAML array, so do not include a
  `custom_fields:` line above it — with one, TRMNL reads a dictionary and
  answers "Custom Fields should be a valid YAML array". This is what gives you
  the **Embalses** box to type ids into
- Leave the polling headers and body empty, and leave "remove bleed margin" off

Save. Then click **Edit Markup** and paste each file from [`src/`](src) into the
tab of the same name: `full`, `half_horizontal`, `half_vertical`, `quadrant`.
The templates deliberately have no `<div class="view">` wrapper — the editor
supplies it, and TRMNL's docs say those classes are for standalone pages only.

Back on the plugin settings page, click **Force Refresh** to pull the JSON
straight away rather than waiting for the next poll. With a single polling URL
TRMNL puts the response at the root, so the markup reads `{{ reservoirs }}` and
`{{ national.percent_text }}` directly; you can see the whole payload under
"Your Variables" in the markup editor.

Finally add the plugin to a playlist and set its refresh rate. Twelve hours is
plenty — the source data only changes weekly.

## The annual chart

Turn the **Gráfico anual** field on and, when a single reservoir is selected,
the full view swaps its stat tiles for embalses.net's own annual chart — this
year against the last two and the ten-year average, which is what those tiles
were saying anyway.

The chart lives at `/cache/pantano-<id>.png`, so the template builds its URL
from the same id as everything else and nothing has to be mirrored. It is drawn
in colour, and a plain greyscale turns its pale min/max band into heavy
dithered hatching, so the template dims the image before boosting contrast:
that drops the band and the gridlines to white while all four series stay
black. A brighter setting looks cleaner still but silently loses the green 2024
line, which is why the values are what they are. The image is left at its own
560x250 rather than stretched, so the 1px lines and small labels land on whole
pixels.

The graphs are published by Embalses.net under CC BY 4.0 — free to use and
adapt with credit — and the view carries the attribution.

## Previewing without trmnlp

`trmnlp` needs Ruby 3. If you would rather not install it, there is a small
Python preview that renders all four views against real data using TRMNL's own
stylesheet:

```bash
pip install python-liquid
python3 scripts/preview.py            # every reservoir in the payload
python3 scripts/preview.py --limit 1  # the single-reservoir layouts
open preview.html
```

## What the payload looks like

TRMNL rejects a polling payload over 100 kB, and this one carries every
reservoir so the form field can name any of them. Repeating long key names 374
times cost more than all the values put together, so entries are short keys
holding plain numbers and the templates do the formatting. That is 45 kB:

```json
{
  "as_of_label": "07/09/2026",
  "last_year_label": "2025",
  "default_ids": "795,830,816,799",
  "reservoirs": [
    {"id": "871", "n": "Rules", "b": "Med. Andaluza", "pv": "Granada",
     "r": "Guadalfeo", "v": 96, "c": 111, "d": -2, "p": 86.5, "ly": 72.1, "a": 68.5}
  ],
  "national": { "...": "formatted strings for all of Spain" }
}
```

| key | meaning | key | meaning |
|-----|---------|-----|---------|
| `id` | the number in the page URL | `v` | hm³ stored |
| `n` | name | `c` | hm³ capacity |
| `b` | basin | `d` | hm³ change this week |
| `pv` | province | `p` | % full |
| `r` | river | `ly` | % the same week last year |
| | | `a` | % ten-year average for this week |

`national` is a single object, so it keeps its pre-formatted strings — it is
where the thousands separators actually matter (35.073 hm³). Per-reservoir
figures are formatted in Liquid instead, which means no thousands separator on
the nine reservoirs holding over 1.000 hm³.

## Data source and courtesy

The figures belong to [embalses.net](https://www.embalses.net), which compiles
them from the Ministerio para la Transición Ecológica, AEMET, the SAIH networks
of the river authorities, CEDEX and SIAR. Keep the attribution on screen or in
your plugin description if you share this.

The scraper identifies itself, pauses between requests and obeys `robots.txt`.
A daily run costs sixteen requests — the basin pages, which carry the current
figures for everyone. The reservoirs' own pages are the only source for last
year and the ten-year average, so those are fetched once per reservoir per week,
when the site's data date changes, and cached in `data/detail.json` in between.
Please leave that shape alone; it is someone else's site.

## Licence

MIT for the code here. The data is not mine to license.
