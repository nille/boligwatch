# BoligWatch

[![CI](https://github.com/nille/boligwatch/actions/workflows/ci.yml/badge.svg)](https://github.com/nille/boligwatch/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

CLI tool and MCP server that monitors [boligportal.dk](https://www.boligportal.dk) for new rental listings in Denmark. Polls the same public search API the website uses — no account or API key required.

## Requirements

- Python 3.10+
- CLI mode works with stdlib only (zero required dependencies)
- `pip install curl_cffi` — recommended, bypasses Cloudflare bot protection (see [Cloudflare bypass](#cloudflare-bypass))
- `pip install mcp` for MCP server mode

## Installation

```bash
# Clone the repository
git clone https://github.com/your-username/boligwatch.git
cd boligwatch

# (Optional) Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# CLI mode works out of the box with stdlib only
python boligwatch.py --help

# Recommended: install curl_cffi to bypass Cloudflare bot protection
pip install curl_cffi

# For MCP server mode, install the MCP SDK
pip install mcp

# Generate a config file and edit it to match your search
python boligwatch.py --init-config
```

## Quick start

```bash
# Run once — shows new listings (no filters unless config file provides them)
python boligwatch.py

# Use a saved config for your regular search
python boligwatch.py --config boligwatch_config.json

# Watch mode — poll every 5 minutes
python boligwatch.py --config boligwatch_config.json --watch

# Ad-hoc search with inline filters
python boligwatch.py --city københavn --rooms-min 3 --max-rent 16000 --balcony
```

## How it works

BoligWatch fetches listings from boligportal.dk's search API, filters them according to your criteria, and tracks which ones you've already seen in a local JSON file. On each run it only shows new listings — ones not previously seen.

The tracker also detects **re-listed apartments**: if a landlord re-publishes a listing with the same ID but a newer `advertised_date`, it resurfaces as new. This prevents missed opportunities when listings are taken down and re-posted. The seen file stores the `advertised_date` alongside the seen timestamp for comparison. Legacy entries (from older versions) are read transparently — re-listing detection is skipped for entries without a stored `advertised_date`.

There are three ways to use it:

1. **CLI** — run once or in watch mode, pipe JSON to other tools
2. **MCP server** — expose search and tracking as tools for Claude Code, Claude Desktop, or any MCP client
3. **Skill** — a ready-made skill that teaches Claude to translate natural-language apartment queries into MCP tool calls

## CLI reference

### Modes

| Flag | Description |
|------|-------------|
| *(default)* | Run once, print new listings, mark them as seen |
| `--watch`, `-w` | Poll continuously (default: every 300s) |
| `--interval N`, `-i N` | Poll interval in seconds (used with `--watch`) |
| `--json` | Output new listings as a JSON array, mark as seen |
| `--peek` | Output new listings as JSON, do NOT mark as seen (retry-safe) |
| `--mcp` | Start as MCP server (stdio transport) |

### Seen-listing management

| Flag | Description |
|------|-------------|
| `--mark-seen ID [ID ...]` | Mark specific listing IDs as seen |
| `--reset` | Clear all seen-listing history before running |
| `--seen-file PATH` | Custom path for the seen-listings tracker (default: `.boligwatch_seen.json`) |

### Config and logging

| Flag | Description |
|------|-------------|
| `--config PATH`, `-c PATH` | Path to a JSON config file |
| `--init-config` | Generate a config template at `--config` path or default location |
| `--log-file PATH` | Write log to file |
| `--verbose`, `-v` | Verbose (DEBUG-level) logging |

### Search filters

All filters default to no limit (unset). See [Filter behavior](#filter-behavior) for how filters interact with the config file.

#### Location

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--city NAME` | string (repeatable) | `["k\u00f8benhavn"]` | City to search. Can be repeated: `--city k\u00f8benhavn --city frederiksberg` |
| `--bbox S,W,N,E` | floats | *none* | Bounding box as `min_lat,min_lng,max_lat,max_lng`. Replaces `--city` when set |

City names use lowercase Danish with original characters: `k\u00f8benhavn`, `frederiksberg`, `aarhus`, `odense`, `aalborg`.

#### Size and price

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--rooms-min N` | int | *none* | Minimum number of rooms |
| `--rooms-max N` | int | *none* | Maximum number of rooms |
| `--max-rent N` | int | *none* | Maximum monthly rent in DKK |
| `--min-size N` | int | *none* | Minimum size in m\u00b2 |
| `--min-rental-period N` | int | *none* | Minimum lease length in months (12 = 1 year) |
| `--max-available-from DATE` | YYYY-MM-DD | *none* | Latest move-in date |

#### Property type

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--newbuild` | bool | *none* | Only new-build / project rentals (projektudlejning) |
| `--social-housing` | bool | *none* | Only social housing (almen bolig) |

#### Lifestyle

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--pet-friendly` | bool | *none* | Only pet-friendly listings |
| `--senior-friendly` | bool | *none* | Only senior-friendly listings |
| `--student-only` | bool | *none* | Only student housing |
| `--shareable` | bool | *none* | Only shareable apartments (delevenlig) |

#### Facilities

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--parking` | bool | *none* | Must have parking |
| `--elevator` | bool | *none* | Must have elevator |
| `--balcony` | bool | *none* | Must have balcony or terrace |
| `--ev-charging` | bool | *none* | Must have EV charging station (ladestander) |

#### Appliances

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--furnished` | bool | *none* | Must be furnished |
| `--dishwasher` | bool | *none* | Must have dishwasher |
| `--washing-machine` | bool | *none* | Must have washing machine |
| `--dryer` | bool | *none* | Must have dryer |

#### Pagination

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--max-pages N` | int | `5` | Maximum pages to fetch (18 listings per page, max 50) |

### CLI examples

```bash
# Pet-friendly 2-room apartments in Copenhagen under 12.000kr
python boligwatch.py --city k\u00f8benhavn --rooms-min 2 --rooms-max 2 --max-rent 12000 --pet-friendly

# Large apartments (100m2+) with balcony, available by August
python boligwatch.py --city k\u00f8benhavn --min-size 100 --balcony --max-available-from 2026-08-01

# Furnished places with dishwasher and washing machine in Frederiksberg
python boligwatch.py --city frederiksberg --furnished --dishwasher --washing-machine

# Social housing anywhere in the Copenhagen bounding box
python boligwatch.py --bbox 55.63,12.48,55.73,12.80 --social-housing

# New-build project rentals with EV charging and elevator
python boligwatch.py --city k\u00f8benhavn --newbuild --ev-charging --elevator

# Peek at new listings as JSON (safe to retry, doesn't mark seen)
python boligwatch.py --config boligwatch_config.json --peek

# Watch mode: poll every 2 minutes with a saved config
python boligwatch.py --config boligwatch_config.json --watch --interval 120

# Mark specific listings as seen
python boligwatch.py --mark-seen 5619969 2987892

# Pipe to jq for processing
python boligwatch.py --peek | jq '.[].url'
```

## Config file

A config file saves your default search criteria so you don't have to pass CLI flags every time. CLI flags always override config values.

### Generate a template

```bash
python boligwatch.py --init-config
# or specify a path:
python boligwatch.py --init-config --config my_search.json
```

### Config file format

All fields are optional. Omit a field or set it to `null` for no limit. Unknown keys are logged as warnings to help catch typos.

```json
{
  "categories": ["rental_apartment", "rental_house", "rental_townhouse"],
  "city_level_1": ["k\u00f8benhavn"],
  "city_level_2": null,
  "min_lat": null,
  "min_lng": null,
  "max_lat": null,
  "max_lng": null,
  "rooms_min": 3,
  "rooms_max": null,
  "max_rent": 17000,
  "min_size_m2": null,
  "min_rental_period": 12,
  "max_available_from": null,
  "pet_friendly": null,
  "balcony": null,
  "furnished": null,
  "parking": null,
  "elevator": null,
  "shareable": null,
  "student_only": null,
  "senior_friendly": null,
  "social_housing": null,
  "newbuild": null,
  "electric_charging_station": null,
  "dishwasher": null,
  "washing_machine": null,
  "dryer": null,
  "order": "DEFAULT",
  "max_pages": 5
}
```

#### Categories

The `categories` field controls which property types to include:

| Value | Danish | Description |
|-------|--------|-------------|
| `rental_apartment` | Lejligheder | Apartments |
| `rental_room` | V\u00e6relser | Rooms |
| `rental_house` | Huse | Houses |
| `rental_townhouse` | R\u00e6kkehuse | Townhouses |

#### Location: city vs bounding box

You can filter by city name or bounding box, but not both. When bounding box coordinates are set, city filters are ignored.

- **City**: `"city_level_1": ["k\u00f8benhavn", "frederiksberg"]`
- **Bounding box**: Set all four of `min_lat`, `min_lng`, `max_lat`, `max_lng`
- **Sub-city**: `"city_level_2": ["amager"]` (narrows within city_level_1)

## MCP server

BoligWatch runs as a local [MCP](https://modelcontextprotocol.io) server, exposing search and tracking as tools for any MCP client.

### Setup

Install the MCP SDK (the CLI works without it):

```bash
pip install mcp
```

Add to your MCP client config (`.mcp.json`, Claude Desktop config, etc.):

```json
{
  "mcpServers": {
    "boligwatch": {
      "command": "python3",
      "args": [
        "/path/to/boligwatch.py", "--mcp",
        "--config", "/path/to/boligwatch_config.json"
      ]
    }
  }
}
```

### Tools

| Tool | Description |
|------|-------------|
| `search_listings` | Search with filters, returns all matches as JSON |
| `get_new_listings` | Like search, but only returns listings not previously seen (peek by default) |
| `mark_seen` | Mark listing IDs as seen |
| `reset_seen` | Clear all seen-listing history |
| `get_seen_stats` | Get tracker statistics (count, file path) |

### Filter behavior

The same logic applies to both CLI and MCP:

- **No filters passed** = uses the full saved search from your config file (your monitoring query)
- **Any filter passed** = starts from a clean slate. Only structural settings (categories, location, order, max_pages) carry over from the config. Restrictive filters (rent, rooms, size, features) are stripped — if you ask "find apartments over 200m\u00b2" it won't silently cap at 17,000 kr because of your config.

This means `python boligwatch.py --peek` uses your saved search, but `python boligwatch.py --min-size 200` won't silently cap at 17,000 kr from the config. Same for MCP: `get_new_listings({})` = saved search, `search_listings({min_size_m2: 200})` = clean slate.

### MCP tool parameters

Both `search_listings` and `get_new_listings` accept the same filter parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cities` | `string[]` | *from config* | City names (e.g. `["k\u00f8benhavn"]`) |
| `min_lat` | `float` | *from config* | Bounding box south latitude |
| `min_lng` | `float` | *from config* | Bounding box west longitude |
| `max_lat` | `float` | *from config* | Bounding box north latitude |
| `max_lng` | `float` | *from config* | Bounding box east longitude |
| `rooms_min` | `int` | *no limit* | Minimum rooms |
| `rooms_max` | `int` | *no limit* | Maximum rooms |
| `max_rent` | `int` | *no limit* | Maximum monthly rent (DKK) |
| `min_size_m2` | `int` | *no limit* | Minimum size (m\u00b2) |
| `min_rental_period` | `int` | *no limit* | Minimum lease (months) |
| `max_available_from` | `string` | *no limit* | Latest move-in date (YYYY-MM-DD) |
| `pet_friendly` | `bool` | *no filter* | Pet-friendly only |
| `balcony` | `bool` | *no filter* | Has balcony/terrace |
| `furnished` | `bool` | *no filter* | Furnished only |
| `parking` | `bool` | *no filter* | Has parking |
| `elevator` | `bool` | *no filter* | Has elevator |
| `shareable` | `bool` | *no filter* | Shareable (delevenlig) |
| `student_only` | `bool` | *no filter* | Student-only |
| `senior_friendly` | `bool` | *no filter* | Senior-friendly |
| `social_housing` | `bool` | *no filter* | Social housing (almen bolig) |
| `newbuild` | `bool` | *no filter* | New-build / project rental |
| `electric_charging_station` | `bool` | *no filter* | EV charging |
| `dishwasher` | `bool` | *no filter* | Has dishwasher |
| `washing_machine` | `bool` | *no filter* | Has washing machine |
| `dryer` | `bool` | *no filter* | Has dryer |
| `max_pages` | `int` | `5` | Pages to fetch (18 per page, max 50) |

`get_new_listings` also accepts:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mark_as_seen` | `bool` | `false` | If true, mark returned listings as seen |

### MCP tool call examples

**Search for 3+ room apartments in Copenhagen under 16.000kr:**

```json
{
  "tool": "search_listings",
  "arguments": {
    "cities": ["k\u00f8benhavn"],
    "rooms_min": 3,
    "max_rent": 16000
  }
}
```

**Find furnished apartments with washing machine and dishwasher:**

```json
{
  "tool": "search_listings",
  "arguments": {
    "cities": ["k\u00f8benhavn"],
    "furnished": true,
    "washing_machine": true,
    "dishwasher": true
  }
}
```

**Large apartments (150m\u00b2+) anywhere in the search area:**

```json
{
  "tool": "search_listings",
  "arguments": {
    "min_size_m2": 150,
    "max_pages": 10
  }
}
```

**New-build projects with EV charging, available by September:**

```json
{
  "tool": "search_listings",
  "arguments": {
    "newbuild": true,
    "electric_charging_station": true,
    "max_available_from": "2026-09-01"
  }
}
```

**Check for unseen listings (peek mode):**

```json
{
  "tool": "get_new_listings",
  "arguments": {}
}
```

**Check for new listings and mark them as seen:**

```json
{
  "tool": "get_new_listings",
  "arguments": {
    "mark_as_seen": true
  }
}
```

**Mark specific listings as reviewed:**

```json
{
  "tool": "mark_seen",
  "arguments": {
    "ids": [5619969, 2987892]
  }
}
```

## Skill: natural-language queries

A ready-made skill is included at [`skills/bolig-watch/SKILL.md`](skills/bolig-watch/SKILL.md) that teaches Claude to translate natural-language apartment queries into MCP tool calls.

### Example queries

Once the MCP server and skill are configured, you can ask Claude things like:

```
Find me a 3-room apartment in Copenhagen under 15.000kr
```

```
Are there any pet-friendly places with a balcony in Frederiksberg?
```

```
Show me the largest apartments available right now
```

```
Any new listings since last time?
```

```
Find furnished apartments with a washing machine, at least 70m2
```

```
What's available in Amager for under 12k with at least 2 rooms?
```

```
Show me new-build projects with EV charging and elevator
```

```
Find social housing apartments in Copenhagen available before August
```

```
I've looked at those listings, mark them as seen
```

```
How many listings have I seen so far?
```

### Scheduled polling with Claude Code

Use Claude Code's loop command to have Claude poll for new listings automatically:

```
/loop 5m check for new boligportal listings. Summarize anything new.
```

## Browser automation with Playwright MCP

Combine BoligWatch with [Playwright MCP](https://github.com/microsoft/playwright-mcp) and the [Playwright MCP Bridge](https://chromewebstore.google.com/detail/playwright-mcp-bridge/mmlmfjhmonkocbjadbfplnigmagldckm) Chrome extension. Together, they let Claude control your actual browser with your logged-in boligportal.dk session.

This means Claude can navigate to listings, read details, contact landlords, fill in forms, and send messages.

### Setup

1. Install the [Playwright MCP Bridge](https://chromewebstore.google.com/detail/playwright-mcp-bridge/mmlmfjhmonkocbjadbfplnigmagldckm) extension in Chrome
2. Add both MCP servers to your config:

```json
{
  "mcpServers": {
    "boligwatch": {
      "command": "python3",
      "args": ["/path/to/boligwatch.py", "--mcp", "--config", "/path/to/config.json"]
    },
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp@latest", "--extension"]
    }
  }
}
```

### Autonomous apartment hunting

```
/loop 5m check for new boligportal listings with the boligwatch MCP.
For each new listing, open it in the browser with Playwright, save a PDF,
contact the landlord with a message in Danish, and notify me on Slack.
```

Because the extension bridges into your existing browser session, Claude authenticates as you — no separate login flow, no stored credentials.

## Cloudflare bypass

Boligportal.dk uses Cloudflare bot protection, which can block requests from standard HTTP clients like Python's `urllib` with an HTTP 403 and a JavaScript challenge. When this happens, the API becomes unreachable.

Installing `curl_cffi` enables Chrome TLS fingerprint impersonation, which bypasses the challenge transparently:

```bash
pip install curl_cffi
```

When `curl_cffi` is installed, BoligWatch automatically uses it for all API requests. When it's not installed, BoligWatch falls back to stdlib `urllib` — which works fine when Cloudflare isn't actively challenging requests.

Both backends retry on HTTP 403, 429, and 5xx errors with exponential backoff.

## Listing output format

Each listing returned by the API includes:

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Unique listing ID |
| `url` | string | Direct link to the listing |
| `title` | string | Listing title |
| `city` | string | City name |
| `city_area` | string | Sub-area (e.g. "K\u00f8benhavn S", "Amager") |
| `postal_code` | string | Postal code |
| `street_name` | string | Street name |
| `street_number` | string | Street number |
| `rooms` | float | Number of rooms |
| `size_m2` | float | Size in square meters |
| `monthly_rent` | float | Monthly rent |
| `monthly_rent_currency` | string | Currency (typically "kr") |
| `deposit` | float | Deposit amount |
| `prepaid_rent` | float | Prepaid rent |
| `available_from` | string | Move-in date (YYYY-MM-DD) |
| `advertised_date` | string | When the listing was posted |
| `category` | string | Property type |
| `energy_rating` | string | Energy label (e.g. "A2010", "C") |
| `features` | object | Boolean feature flags (pet_friendly, elevator, etc.) |

## License

[MIT](LICENSE)
