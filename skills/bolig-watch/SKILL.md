---
name: bolig-watch
description: >-
  Search Danish rental listings on boligportal.dk using natural language.
  Translates queries like "3-room apartment in Amager under 15k" into
  structured searches via the BoligWatch MCP server and returns results
  with links. Use when the user asks about apartments, rentals, or housing
  in Denmark.
compatibility: Requires the boligwatch MCP server to be running. Python 3.10+.
allowed-tools: mcp__boligwatch__search_listings mcp__boligwatch__get_new_listings mcp__boligwatch__mark_seen mcp__boligwatch__reset_seen mcp__boligwatch__get_seen_stats
metadata:
  author: boligwatch
  version: "2.0"
---

# BoligWatch Skill

Search boligportal.dk for rental listings using natural language.

## When to activate

- The user asks about apartments, rentals, or housing in Denmark
- The user mentions boligportal, boligwatch, or Danish cities in a housing context
- The user wants to check for new listings or track what they've already seen

## Available MCP tools

| Tool | Purpose |
|------|---------|
| `search_listings` | Search with filters, returns all matches |
| `get_new_listings` | Returns only listings not previously seen |
| `mark_seen` | Mark listing IDs as reviewed |
| `reset_seen` | Clear all seen history |
| `get_seen_stats` | Check tracker state |

## How to translate natural language to search parameters

Map the user's intent to these filter parameters:

### Location

| User says | Parameter | Example value |
|-----------|-----------|---------------|
| "in Copenhagen" / "i K\u00f8benhavn" | `cities` | `["k\u00f8benhavn"]` |
| "in Frederiksberg" | `cities` | `["frederiksberg"]` |
| "K\u00f8benhavn and Frederiksberg" | `cities` | `["k\u00f8benhavn", "frederiksberg"]` |
| "in this area" + coordinates | `min_lat`, `min_lng`, `max_lat`, `max_lng` | bounding box |

### Size and price

| User says | Parameter | Example value |
|-----------|-----------|---------------|
| "3 rooms" / "3-room" | `rooms_min` + `rooms_max` | `3`, `3` |
| "at least 3 rooms" / "3+" | `rooms_min` | `3` |
| "2-4 rooms" | `rooms_min` + `rooms_max` | `2`, `4` |
| "under 15k" / "max 15.000kr" | `max_rent` | `15000` |
| "at least 60m2" / "60 square meters" | `min_size_m2` | `60` |
| "long-term" / "at least a year" | `min_rental_period` | `12` |
| "available by August" / "move in before Sept" | `max_available_from` | `"2026-08-01"` |

### Property type

| User says | Parameter | Example value |
|-----------|-----------|---------------|
| "new-build" / "projekt" / "projektudlejning" | `newbuild` | `true` |
| "social housing" / "almen bolig" | `social_housing` | `true` |

### Lifestyle

| User says | Parameter | Example value |
|-----------|-----------|---------------|
| "pet-friendly" / "allows pets" / "husdyr" | `pet_friendly` | `true` |
| "senior-friendly" / "seniorvenlig" | `senior_friendly` | `true` |
| "student housing" / "kun studerende" | `student_only` | `true` |
| "shareable" / "delevenlig" | `shareable` | `true` |

### Facilities

| User says | Parameter | Example value |
|-----------|-----------|---------------|
| "with balcony" / "altan" / "terrasse" | `balcony` | `true` |
| "with parking" / "parkering" | `parking` | `true` |
| "with elevator" / "has lift" | `elevator` | `true` |
| "EV charging" / "ladestander" | `electric_charging_station` | `true` |

### Appliances

| User says | Parameter | Example value |
|-----------|-----------|---------------|
| "furnished" / "m\u00f8bleret" | `furnished` | `true` |
| "dishwasher" / "opvaskemaskine" | `dishwasher` | `true` |
| "washing machine" / "vaskemaskine" | `washing_machine` | `true` |
| "dryer" / "t\u00f8rretumbler" | `dryer` | `true` |

### City name mapping

The API uses lowercase Danish city names with original Danish characters:

- K\u00f8benhavn \u2192 `k\u00f8benhavn`
- Frederiksberg \u2192 `frederiksberg`
- Aarhus / \u00c5rhus \u2192 `aarhus`
- Odense \u2192 `odense`
- Aalborg / \u00c5lborg \u2192 `aalborg`

## Important: filter inheritance

MCP tools do NOT inherit restrictive filters (rent, rooms, size, features) from the server config. Only structural settings (location, categories) carry over. This means if a user asks "find the largest apartments" you don't need to worry about hidden rent caps from the config file.

## Workflow

1. Parse the user's request into search filters
2. Decide: use `get_new_listings` if the user wants "new" or "unseen" listings, otherwise use `search_listings`
3. Call the tool with the mapped parameters
4. Format results as a readable summary with:
   - Monthly rent and deposit
   - Rooms, size, and location
   - Available from date
   - Notable features (pet-friendly, balcony, etc.)
   - Direct link to the listing on boligportal.dk
5. If the user wants to track which listings they've reviewed, call `mark_seen` with the IDs

## Response format

Present each listing clearly:

```
**Vesterbrogade 42, K\u00f8benhavn** \u2014 3 rooms, 78m\u00b2
12.500 kr/month (deposit: 37.500 kr) \u00b7 Available from 1 May 2026
Pet-friendly, balcony
\u2192 https://www.boligportal.dk/lejebolig/...
```

Group by area when showing multiple results. Mention the total count. If no results match, suggest relaxing filters.

## Examples

**User:** "Find me a 2-3 room apartment in Copenhagen under 14.000kr"

\u2192 Call `search_listings` with:
```json
{
  "cities": ["k\u00f8benhavn"],
  "rooms_min": 2,
  "rooms_max": 3,
  "max_rent": 14000
}
```

**User:** "Any new listings since last time?"

\u2192 Call `get_new_listings` with no filter overrides (uses server defaults)

**User:** "Show me furnished places with a washing machine, at least 70m2"

\u2192 Call `search_listings` with:
```json
{
  "furnished": true,
  "washing_machine": true,
  "min_size_m2": 70
}
```

**User:** "Find social housing available before August"

\u2192 Call `search_listings` with:
```json
{
  "social_housing": true,
  "max_available_from": "2026-08-01"
}
```

**User:** "New-build projects with EV charging and elevator"

\u2192 Call `search_listings` with:
```json
{
  "newbuild": true,
  "electric_charging_station": true,
  "elevator": true
}
```

**User:** "What's the biggest apartment available right now?"

\u2192 Call `search_listings` with `max_pages: 10`, then sort results by `size_m2` descending

**User:** "I've looked at listings 5619969 and 2987892, mark them"

\u2192 Call `mark_seen` with `ids: [5619969, 2987892]`
