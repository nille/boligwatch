#!/usr/bin/env python3
"""
BoligWatch — Monitor boligportal.dk for new rental listings.

Polls the boligportal.dk search API and notifies you of new listings
matching your search criteria. Tracks seen listings in a local JSON file
to avoid duplicates between runs.

Usage:
    python boligwatch.py                    # Run once with defaults
    python boligwatch.py --watch            # Poll every 5 minutes
    python boligwatch.py --interval 120     # Poll every 2 minutes
    python boligwatch.py --config my.json   # Use custom config
    python boligwatch.py --init-config      # Generate a config template
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

API_URL = "https://www.boligportal.dk/api/search/list"
LISTING_BASE = "https://www.boligportal.dk"
DEFAULT_SEEN_FILE = Path(__file__).parent / ".boligwatch_seen.json"
DEFAULT_CONFIG_FILE = Path(__file__).parent / "boligwatch_config.json"
DEFAULT_LOG_FILE = Path(__file__).parent / "boligwatch.log"
PAGE_SIZE = 18

log = logging.getLogger("boligwatch")


# ── Config ────────────────────────────────────────────────────────────

@dataclass
class SearchConfig:
    categories: list[str] = field(
        default_factory=lambda: ["rental_apartment", "rental_house", "rental_townhouse"]
    )
    city_level_1: list[str] | None = field(default_factory=lambda: ["københavn"])
    city_level_2: list[str] | None = None
    min_lat: float | None = None
    min_lng: float | None = None
    max_lat: float | None = None
    max_lng: float | None = None
    rooms_min: int | None = 3
    rooms_max: int | None = None
    max_rent: int | None = None
    min_size_m2: int | None = None
    min_rental_period: int | None = None
    pet_friendly: bool | None = None
    balcony: bool | None = None
    furnished: bool | None = None
    parking: bool | None = None
    elevator: bool | None = None
    shareable: bool | None = None
    student_only: bool | None = None
    senior_friendly: bool | None = None
    order: str = "DEFAULT"
    max_pages: int = 5

    def to_api_body(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "categories": {"values": self.categories},
        }
        if self.city_level_1:
            body["city_level_1"] = {"values": self.city_level_1}
        if self.city_level_2:
            body["city_level_2"] = {"values": self.city_level_2}
        if self.rooms_min is not None or self.rooms_max is not None:
            rooms: dict[str, int] = {}
            if self.rooms_min is not None:
                rooms["gte"] = self.rooms_min
            if self.rooms_max is not None:
                rooms["lte"] = self.rooms_max
            body["rooms"] = rooms
        if self.max_rent is not None:
            body["max_monthly_rent"] = self.max_rent
        if self.min_size_m2 is not None:
            body["min_size_m2"] = self.min_size_m2
        if self.min_rental_period is not None:
            body["min_rental_period"] = self.min_rental_period
        if self.min_lat is not None:
            body["min_lat"] = self.min_lat
        if self.min_lng is not None:
            body["min_lng"] = self.min_lng
        if self.max_lat is not None:
            body["max_lat"] = self.max_lat
        if self.max_lng is not None:
            body["max_lng"] = self.max_lng

        for attr, key in [
            ("pet_friendly", "pet_friendly"),
            ("balcony", "balcony"),
            ("furnished", "furnished"),
            ("parking", "parking"),
            ("elevator", "elevator"),
            ("shareable", "shareable"),
            ("student_only", "student_only"),
            ("senior_friendly", "senior_friendly"),
        ]:
            val = getattr(self, attr)
            if val is not None:
                body[key] = val

        body["order"] = self.order
        return body

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for k, v in self.__dict__.items():
            if v is not None:
                result[k] = v
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SearchConfig:
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


DEFAULT_CONFIG_TEMPLATE = {
    "categories": ["rental_apartment", "rental_house", "rental_townhouse"],
    "city_level_1": ["københavn"],
    "city_level_2": None,
    "min_lat": None,
    "min_lng": None,
    "max_lat": None,
    "max_lng": None,
    "rooms_min": 3,
    "rooms_max": None,
    "max_rent": 20000,
    "min_size_m2": 60,
    "min_rental_period": None,
    "pet_friendly": None,
    "balcony": None,
    "furnished": None,
    "parking": None,
    "elevator": None,
    "shareable": None,
    "student_only": None,
    "senior_friendly": None,
    "order": "DEFAULT",
    "max_pages": 5,
}


# ── API Client ────────────────────────────────────────────────────────

@dataclass
class Listing:
    id: int
    url: str
    title: str
    city: str
    city_area: str
    postal_code: str
    street_name: str | None
    street_number: str | None
    rooms: float
    size_m2: float
    monthly_rent: float
    monthly_rent_currency: str
    deposit: float | None
    prepaid_rent: float | None
    available_from: str | None
    advertised_date: str | None
    created: str | None
    category: str
    energy_rating: str | None
    features: dict[str, Any]
    images: list[dict[str, Any]]

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Listing:
        return cls(
            id=data["id"],
            url=LISTING_BASE + data["url"],
            title=data.get("title", ""),
            city=data.get("city", ""),
            city_area=data.get("city_area", ""),
            postal_code=data.get("postal_code", ""),
            street_name=data.get("street_name"),
            street_number=data.get("street_number"),
            rooms=data.get("rooms", 0),
            size_m2=data.get("size_m2", 0),
            monthly_rent=data.get("monthly_rent", 0),
            monthly_rent_currency=data.get("monthly_rent_currency", "kr"),
            deposit=data.get("deposit"),
            prepaid_rent=data.get("prepaid_rent"),
            available_from=data.get("available_from"),
            advertised_date=data.get("advertised_date"),
            created=data.get("created"),
            category=data.get("category", ""),
            energy_rating=data.get("energy_rating"),
            features=data.get("features", {}),
            images=data.get("images", []),
        )

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "city": self.city,
            "city_area": self.city_area,
            "postal_code": self.postal_code,
            "street_name": self.street_name,
            "street_number": self.street_number,
            "rooms": self.rooms,
            "size_m2": self.size_m2,
            "monthly_rent": self.monthly_rent,
            "monthly_rent_currency": self.monthly_rent_currency,
            "deposit": self.deposit,
            "prepaid_rent": self.prepaid_rent,
            "available_from": self.available_from,
            "advertised_date": self.advertised_date,
            "category": self.category,
            "energy_rating": self.energy_rating,
            "features": {k: v for k, v in self.features.items() if v is True},
        }

    def format_short(self) -> str:
        rent = f"{int(self.monthly_rent):,}{self.monthly_rent_currency}".replace(",", ".")
        size = f"{int(self.size_m2)}m\u00b2"
        rooms = f"{self.rooms:g}r"
        location = self.city_area or self.city
        addr = ""
        if self.street_name:
            addr = f"{self.street_name}"
            if self.street_number:
                addr += f" {self.street_number}"
            addr += ", "
        date_str = ""
        if self.advertised_date:
            try:
                dt = datetime.fromisoformat(self.advertised_date)
                date_str = dt.strftime(" [%Y-%m-%d %H:%M]")
            except (ValueError, TypeError):
                pass
        feats = []
        for feat_name, val in self.features.items():
            if val is True:
                feats.append(feat_name.replace("_", " "))
        feat_str = f"  ({', '.join(feats)})" if feats else ""
        return f"  {rent} | {rooms} | {size} | {addr}{location}{date_str}{feat_str}\n  {self.title}\n  {self.url}"


MAX_RETRIES = 5
BACKOFF_BASE = 2.0
BACKOFF_MAX = 300.0


def _api_request(url: str, body_bytes: bytes) -> dict[str, Any]:
    """POST to the boligportal API with exponential backoff + jitter."""
    for attempt in range(MAX_RETRIES):
        req = urllib.request.Request(
            url,
            data=body_bytes,
            headers={
                "Content-Type": "text/plain;charset=UTF-8",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                delay = min(BACKOFF_BASE ** (attempt + 1), BACKOFF_MAX)
                jitter = random.uniform(0, delay * 0.5)
                wait = delay + jitter
                print(
                    f"  HTTP {e.code} — backing off {wait:.0f}s (attempt {attempt + 1}/{MAX_RETRIES})",
                    file=sys.stderr,
                )
                time.sleep(wait)
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == MAX_RETRIES - 1:
                raise
            delay = min(BACKOFF_BASE ** (attempt + 1), BACKOFF_MAX)
            jitter = random.uniform(0, delay * 0.5)
            wait = delay + jitter
            print(
                f"  Network error — retrying in {wait:.0f}s (attempt {attempt + 1}/{MAX_RETRIES})",
                file=sys.stderr,
            )
            time.sleep(wait)
    raise RuntimeError(f"Failed after {MAX_RETRIES} retries")


def fetch_listings(config: SearchConfig) -> list[Listing]:
    body = config.to_api_body()
    body_bytes = json.dumps(body).encode("utf-8")
    all_listings: list[Listing] = []

    for page in range(config.max_pages):
        offset = page * PAGE_SIZE
        url = f"{API_URL}?offset={offset}"
        data = _api_request(url, body_bytes)

        results = data.get("results", [])
        for r in results:
            all_listings.append(Listing.from_api(r))

        if not data.get("next_page_url"):
            break

    return all_listings


# ── Seen-Listings Tracker ─────────────────────────────────────────────

class SeenTracker:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._seen: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            with open(self._path, encoding="utf-8") as f:
                self._seen = json.load(f)

    def _save(self) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._seen, f, indent=2, ensure_ascii=False)

    def is_new(self, listing_id: int) -> bool:
        return str(listing_id) not in self._seen

    def mark_seen(self, listing_id: int) -> None:
        self._seen[str(listing_id)] = datetime.now(timezone.utc).isoformat()
        self._save()

    def mark_all_seen(self, ids: list[int]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        for lid in ids:
            self._seen[str(lid)] = now
        self._save()

    @property
    def count(self) -> int:
        return len(self._seen)


# ── Notifications ─────────────────────────────────────────────────────

def _notify_macos(title: str, message: str, url: str | None = None) -> None:
    """Send a macOS Notification Center alert. Opens URL on click if given."""
    script = f'display notification "{message}" with title "{title}"'
    if url:
        script = (
            f'display notification "{message}" with title "{title}"\n'
            f'-- click opens listing in browser via open_url below'
        )
    try:
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass


def notify_new_listings(listings: list[Listing], open_browser: bool = False) -> None:
    """Send one summary notification + optionally open listings in browser."""
    if not listings:
        return

    if len(listings) == 1:
        l = listings[0]
        rent = f"{int(l.monthly_rent):,}kr".replace(",", ".")
        title = "BoligWatch: 1 new listing"
        msg = f"{rent} | {l.rooms:g}r | {int(l.size_m2)}m² — {l.city_area or l.city}"
        _notify_macos(title, msg, l.url)
    else:
        rents = [l.monthly_rent for l in listings]
        title = f"BoligWatch: {len(listings)} new listings"
        msg = f"{int(min(rents)):,}–{int(max(rents)):,}kr".replace(",", ".")
        areas = sorted({l.city_area or l.city for l in listings})
        if len(areas) <= 3:
            msg += f" in {', '.join(areas)}"
        _notify_macos(title, msg)

    if open_browser:
        for l in listings:
            webbrowser.open(l.url)
            time.sleep(0.3)


def setup_logging(log_file: Path | None, verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s %(levelname)s %(message)s"
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(level=level, format=fmt, handlers=handlers)


# ── CLI ───────────────────────────────────────────────────────────────

def print_header(config: SearchConfig, total: int, new_count: int) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if config.min_lat is not None:
        location = "map area"
    elif config.city_level_1:
        location = ", ".join(config.city_level_1)
    else:
        location = "all"
    rooms = ""
    if config.rooms_min is not None and config.rooms_max is not None:
        rooms = f"{config.rooms_min}-{config.rooms_max}" if config.rooms_min != config.rooms_max else str(config.rooms_min)
    elif config.rooms_min is not None:
        rooms = f"{config.rooms_min}+"
    elif config.rooms_max is not None:
        rooms = f"up to {config.rooms_max}"
    rent = f", max {config.max_rent:,}kr".replace(",", ".") if config.max_rent else ""
    size = f", min {config.min_size_m2}m\u00b2" if config.min_size_m2 else ""
    period = f", min {config.min_rental_period}mo" if config.min_rental_period else ""

    print(f"\n{'='*60}")
    print(f"BoligWatch  {now}")
    print(f"{'='*60}")
    print(f"Search: {location} | {rooms} rooms{rent}{size}{period}")
    print(f"Found: {total} total, {new_count} new")
    print(f"{'='*60}")


def run_once(
    config: SearchConfig,
    tracker: SeenTracker,
    notify: bool = False,
    open_browser: bool = False,
    quiet: bool = False,
    json_output: bool = False,
    peek: bool = False,
) -> list[Listing]:
    listings = fetch_listings(config)
    new_listings = [l for l in listings if tracker.is_new(l.id)]

    if json_output:
        if new_listings:
            output = [l.to_json_dict() for l in new_listings]
            print(json.dumps(output, ensure_ascii=False))
            if not peek:
                tracker.mark_all_seen([l.id for l in new_listings])
        else:
            print("[]")
        return new_listings

    if not quiet:
        print_header(config, len(listings), len(new_listings))

    if new_listings:
        if not quiet:
            print()
        for listing in new_listings:
            print(f"\n{listing.format_short()}")
        tracker.mark_all_seen([l.id for l in new_listings])
        if notify:
            notify_new_listings(new_listings, open_browser=open_browser)
    elif not quiet:
        print("\nNo new listings since last check.")

    if not quiet:
        print(f"\n({tracker.count} listings tracked)")

    if new_listings:
        log.info("Found %d new listings", len(new_listings))

    return new_listings


def watch_loop(
    config: SearchConfig,
    tracker: SeenTracker,
    interval: int,
    notify: bool = True,
    open_browser: bool = False,
) -> None:
    print(f"Watching every {interval}s with notifications {'on' if notify else 'off'} (Ctrl+C to stop)...")
    log.info("Watch started — interval=%ds, notify=%s, open_browser=%s", interval, notify, open_browser)
    try:
        while True:
            try:
                run_once(config, tracker, notify=notify, open_browser=open_browser)
            except urllib.error.URLError as e:
                log.warning("Network error: %s — retrying in %ds", e, interval)
            except json.JSONDecodeError as e:
                log.warning("Parse error: %s — retrying in %ds", e, interval)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped.")
        log.info("Watch stopped by user")


def init_config(path: Path) -> None:
    if path.exists():
        print(f"Config already exists: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_CONFIG_TEMPLATE, f, indent=2, ensure_ascii=False)
    print(f"Config template written to {path}")
    print("Edit it to match your search criteria, then run:")
    print(f"  python {Path(__file__).name} --config {path}")


def load_config(path: Path | None) -> SearchConfig:
    if path and path.exists():
        with open(path, encoding="utf-8") as f:
            return SearchConfig.from_dict(json.load(f))
    return SearchConfig()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Monitor boligportal.dk for new rental listings.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                        Show new listings once
  %(prog)s --watch --notify                       Poll + macOS notifications
  %(prog)s --watch --notify --open                Also open new listings in browser
  %(prog)s -w -n -i 120                           Poll every 2 min with notifications
  %(prog)s --rooms-min 2 --rooms-max 4 --max-rent 15000
  %(prog)s --city københavn --city frederiksberg
  %(prog)s --init-config                          Create config template
  %(prog)s --config my_search.json --watch -n     Use saved config
  %(prog)s --reset                                Clear seen-listings history
        """,
    )
    parser.add_argument("--watch", "-w", action="store_true", help="continuously poll for new listings")
    parser.add_argument("--interval", "-i", type=int, default=300, help="poll interval in seconds (default: 300)")
    parser.add_argument("--notify", "-n", action="store_true", help="send macOS notifications for new listings")
    parser.add_argument("--open", action="store_true", help="open new listings in browser automatically")
    parser.add_argument("--json", action="store_true", dest="json_output", help="output new listings as JSON (for piping to agents)")
    parser.add_argument("--peek", action="store_true", help="like --json but do NOT mark listings as seen (for retry-safe workflows)")
    parser.add_argument("--mark-seen", nargs="+", type=int, metavar="ID", help="mark specific listing IDs as seen")
    parser.add_argument("--config", "-c", type=Path, help="path to config JSON file")
    parser.add_argument("--init-config", action="store_true", help="generate a config template file")
    parser.add_argument("--seen-file", type=Path, default=DEFAULT_SEEN_FILE, help="path to seen-listings tracker")
    parser.add_argument("--log-file", type=Path, default=None, help="write log to file (default: none)")
    parser.add_argument("--verbose", "-v", action="store_true", help="verbose logging")
    parser.add_argument("--reset", action="store_true", help="clear seen-listings history before running")

    # Inline filter overrides (take precedence over config file)
    parser.add_argument("--city", action="append", dest="cities", help="city to search (can repeat)")
    parser.add_argument("--bbox", type=str, metavar="S,W,N,E",
                        help="bounding box as min_lat,min_lng,max_lat,max_lng (replaces --city)")
    parser.add_argument("--rooms-min", type=int, help="minimum rooms")
    parser.add_argument("--rooms-max", type=int, help="maximum rooms")
    parser.add_argument("--max-rent", type=int, help="maximum monthly rent in DKK")
    parser.add_argument("--min-size", type=int, help="minimum size in m²")
    parser.add_argument("--min-rental-period", type=int, help="minimum lease in months (12 = 1 year)")
    parser.add_argument("--max-pages", type=int, help="max pages to fetch (18 results each)")
    parser.add_argument("--pet-friendly", action="store_true", default=None, help="only pet-friendly")
    parser.add_argument("--balcony", action="store_true", default=None, help="must have balcony")
    parser.add_argument("--furnished", action="store_true", default=None, help="must be furnished")

    args = parser.parse_args()

    if args.init_config:
        init_config(args.config or DEFAULT_CONFIG_FILE)
        return

    config = load_config(args.config)

    # Apply CLI overrides
    if args.cities:
        config.city_level_1 = [c.lower() for c in args.cities]
    if args.bbox:
        parts = [float(x.strip()) for x in args.bbox.split(",")]
        if len(parts) != 4:
            parser.error("--bbox requires exactly 4 values: min_lat,min_lng,max_lat,max_lng")
        config.min_lat, config.min_lng, config.max_lat, config.max_lng = parts
        config.city_level_1 = None  # bbox replaces city filter
    if args.rooms_min is not None:
        config.rooms_min = args.rooms_min
    if args.rooms_max is not None:
        config.rooms_max = args.rooms_max
    if args.max_rent is not None:
        config.max_rent = args.max_rent
    if args.min_size is not None:
        config.min_size_m2 = args.min_size
    if args.min_rental_period is not None:
        config.min_rental_period = args.min_rental_period
    if args.max_pages is not None:
        config.max_pages = args.max_pages
    if args.pet_friendly:
        config.pet_friendly = True
    if args.balcony:
        config.balcony = True
    if args.furnished:
        config.furnished = True

    setup_logging(args.log_file, args.verbose)

    if args.reset and args.seen_file.exists():
        args.seen_file.unlink()
        print("Seen-listings history cleared.")

    tracker = SeenTracker(args.seen_file)

    if args.mark_seen:
        tracker.mark_all_seen(args.mark_seen)
        print(f"Marked {len(args.mark_seen)} listing(s) as seen.")
        return

    if args.watch:
        watch_loop(config, tracker, args.interval, notify=args.notify, open_browser=args.open)
    else:
        peek = args.peek
        json_out = args.json_output or peek
        run_once(config, tracker, notify=args.notify, open_browser=args.open, json_output=json_out, peek=peek)


if __name__ == "__main__":
    main()
