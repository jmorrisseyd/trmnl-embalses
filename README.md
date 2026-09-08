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

In TRMNL: Plugins → Private Plugin → Create.

- **Strategy**: Polling
- **URL**: the polling URL from above
- **Refresh rate**: 12 hours is plenty; the source data changes weekly
- **Markup**: paste each file from [`src/`](src) into the matching layout tab —
  `full.liquid`, `half_horizontal.liquid`, `half_vertical.liquid`,
  `quadrant.liquid`

Two optional custom fields are defined in [`src/settings.yml`](src/settings.yml):
`heading` (the text in the bottom bar) and `footer` (whether the summary line
under a list of reservoirs shows Spain, the total of your own reservoirs, or
nothing). Both have sensible defaults if you skip them.

If you use [`trmnlp`](https://github.com/usetrmnl/trmnlp), the `src/` directory
is already in its expected shape — `trmnlp serve` picks up `settings.yml` and
the four templates, and `.trmnlp.yml` sets the custom fields for the preview.

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
