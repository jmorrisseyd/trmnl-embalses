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
```

The Action commits the JSON back to this repository, so there is no server to
run and nothing to pay for. The scraper only ever asks for the pages of the
reservoirs you configured, plus the home page for the national total.

## Setup

### 1. Choose your reservoirs

Search by name to get the ids (this reads the sixteen basin pages, not all four
hundred reservoir pages):

```bash
python3 scripts/embalses.py search cenajo
```

```
   id  name                             basin                   cap hm3  now hm3  fill
  795  El Cenajo                        Segura                      437      278   63.6%
```

Put the ids in [`config.json`](config.json), most important first — the views
show the first few and the narrow layouts only have room for three:

```json
{
  "title": "Embalses",
  "number_format": "es",
  "reservoirs": [795, 830, 816, 799]
}
```

`number_format` is `es` (1.234,5) or `en` (1,234.5). Run the build once to check
it works and to see the data you will get:

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
- **Form Fields** (optional): paste the two field definitions from
  [`src/settings.yml`](src/settings.yml) — everything under `custom_fields:`,
  starting at `- keyname: heading`, dedented so each `-` is at the left margin
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

```json
{
  "as_of": "2026-09-07",
  "as_of_label": "07/09/2026",
  "reservoirs": [
    {
      "id": 795,
      "name": "El Cenajo",
      "basin": "Segura",
      "province": "Albacete",
      "volume_hm3": 278.0,
      "capacity_hm3": 437.0,
      "percent": 63.62,
      "change_hm3": 0.0,
      "last_year_percent": 17.85,
      "avg10_percent": 28.05,
      "percent_text": "63,6",
      "bar_percent": 63.6,
      "trend_glyph": "▬"
    }
  ],
  "total": { "...": "your reservoirs combined" },
  "national": { "...": "all of Spain" }
}
```

Numbers come in two forms: the raw value for arithmetic (`percent`) and a
pre-formatted string for display (`percent_text`), so the templates never have
to do Spanish number formatting in Liquid.

## Data source and courtesy

The figures belong to [embalses.net](https://www.embalses.net), which compiles
them from the Ministerio para la Transición Ecológica, AEMET, the SAIH networks
of the river authorities, CEDEX and SIAR. Keep the attribution on screen or in
your plugin description if you share this.

The scraper identifies itself, pauses between requests, obeys `robots.txt`, and
fetches at most one page per reservoir per day. Please leave it that way — if
you want dozens of reservoirs, consider that each one is another daily request
to someone else's site.

## Licence

MIT for the code here. The data is not mine to license.
