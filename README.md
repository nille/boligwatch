# BoligWatch

CLI tool that monitors [boligportal.dk](https://www.boligportal.dk) for new rental listings in Denmark. Polls the search API, tracks what you've already seen, and notifies you when something new appears.

No account or API key required — it uses the same public search endpoint as the website.

## Quick start

```bash
# Run once — shows new listings matching defaults (3+ rooms in Copenhagen)
python boligwatch.py

# Watch mode — poll every 5 minutes with macOS notifications
python boligwatch.py --watch --notify

# Also open new listings in your browser automatically
python boligwatch.py --watch --notify --open
```

## Configuration

You can override search parameters via CLI flags or a JSON config file.

### CLI flags

```bash
python boligwatch.py --city københavn --city frederiksberg --rooms-min 2 --max-rent 15000
python boligwatch.py --bbox 55.63,12.48,55.73,12.80   # bounding box instead of city
python boligwatch.py --min-size 60 --min-rental-period 12 --pet-friendly
```

### Config file

```bash
# Generate a config template
python boligwatch.py --init-config

# Use it
python boligwatch.py --config boligwatch_config.json --watch --notify
```

See `boligwatch_config.example.json` for all available fields. CLI flags override config file values.

## All options

| Flag | Description |
|------|-------------|
| `--watch`, `-w` | Poll continuously |
| `--interval`, `-i` | Poll interval in seconds (default: 300) |
| `--notify`, `-n` | macOS notification on new listings |
| `--open` | Open new listings in browser |
| `--json` | Output as JSON (for piping to other tools) |
| `--peek` | Like `--json` but don't mark listings as seen |
| `--mark-seen ID [ID ...]` | Mark specific listing IDs as seen |
| `--config`, `-c` | Path to config JSON |
| `--init-config` | Generate config template |
| `--seen-file` | Custom path for seen-listings tracker |
| `--log-file` | Write log to file |
| `--verbose`, `-v` | Verbose logging |
| `--reset` | Clear seen-listings history |
| `--city` | City filter (repeatable) |
| `--bbox S,W,N,E` | Bounding box filter (replaces city) |
| `--rooms-min` / `--rooms-max` | Room count range |
| `--max-rent` | Max monthly rent in DKK |
| `--min-size` | Min size in m2 |
| `--min-rental-period` | Min lease in months |
| `--pet-friendly` | Only pet-friendly listings |
| `--balcony` | Must have balcony |
| `--furnished` | Must be furnished |

## JSON output

The `--json` and `--peek` flags output new listings as a JSON array, which makes it easy to pipe into other tools or scripts:

```bash
# Get new listings as JSON
python boligwatch.py --json

# Peek without marking as seen (safe to retry)
python boligwatch.py --peek
```

## Using with Claude Code

BoligWatch pairs well with [Claude Code](https://claude.ai/claude-code) for hands-free apartment hunting. The `--json` and `--peek` flags are designed for agent consumption.

### Scheduled polling

Use Claude Code's [scheduled tasks](https://code.claude.com/docs/en/scheduled-tasks) to have Claude poll for new listings and act on them autonomously:

```
/loop 5m run python boligwatch.py --peek and summarize any new listings. If something looks promising, open it in the browser.
```

Or let Claude choose the polling interval dynamically:

```
/loop run python boligwatch.py --peek --min-rental-period 12 --max-rent 16000 and tell me about new listings. If a listing has 3+ rooms in Amager or Christianshavn, open it in the browser and draft a short inquiry message.
```

You can also set a one-shot reminder:

```
in 2 hours, check boligwatch for new listings and ping me if anything appeared
```

Scheduled tasks are session-scoped and expire after 7 days. For durable scheduling that survives restarts, see [Claude Code routines](https://code.claude.com/docs/en/routines) or [desktop scheduled tasks](https://code.claude.com/docs/en/desktop-scheduled-tasks).

### Browser automation with Playwright MCP

The real power comes from combining BoligWatch with [Playwright MCP](https://github.com/microsoft/playwright-mcp) and the [Playwright MCP Bridge](https://chromewebstore.google.com/detail/playwright-mcp-bridge/mmlmfjhmonkocbjadbfplnigmagldckm) Chrome extension. Together, they let Claude control your actual browser — with your logged-in boligportal.dk session, cookies, and all.

This means Claude can do more than just find listings. It can navigate to them, read the full details, contact the landlord, fill in forms, and send messages — all without you in the loop.

**Setup:**

1. Install the [Playwright MCP Bridge](https://chromewebstore.google.com/detail/playwright-mcp-bridge/mmlmfjhmonkocbjadbfplnigmagldckm) extension in Chrome
2. Add the Playwright MCP server to your Claude Code config with the `--extension` flag:

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp@latest", "--extension"]
    }
  }
}
```

**Example — fully autonomous apartment hunting:**

```
/loop 5m run python boligwatch.py --peek and review any new listings.
For anything under 16.000kr with 3+ rooms, use Playwright to open the
listing on boligportal.dk, read the full description, and if it looks
good, click "Kontakt udlejer" and send a short inquiry message in Danish.
Mark contacted listings as seen with --mark-seen.
```

Because the extension bridges into your existing browser session, Claude authenticates as you — no separate login flow, no stored credentials, no headless browser. It sees exactly what you would see.

## Requirements

- Python 3.10+
- No external dependencies (stdlib only)
- macOS for notifications (optional — the CLI works anywhere)
