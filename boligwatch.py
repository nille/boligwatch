#!/usr/bin/env python3
"""
BoligWatch -- Monitor boligportal.dk for new rental listings.

Polls the boligportal.dk search API and tracks new listings matching your
search criteria.  Tracks seen listings in a local JSON file to avoid
duplicates between runs.

Usage:
    python boligwatch.py                    # Run once with defaults
    python boligwatch.py --watch            # Poll every 5 minutes
    python boligwatch.py --interval 120     # Poll every 2 minutes
    python boligwatch.py --config my.json   # Use custom config
    python boligwatch.py --init-config      # Generate a config template
    python boligwatch.py --mcp              # Start as MCP server
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
import urllib.error
import urllib.request
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


# -- Config ----------------------------------------------------------------

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
    rooms_min: int | None = None
    rooms_max: int | None = None
    max_rent: int | None = None
    min_size_m2: int | None = None
    min_rental_period: int | None = None
    max_available_from: str | None = None
    pet_friendly: bool | None = None
    balcony: bool | None = None
    furnished: bool | None = None
    parking: bool | None = None
    elevator: bool | None = None
    shareable: bool | None = None
    student_only: bool | None = None
    senior_friendly: bool | None = None
    social_housing: bool | None = None
    newbuild: bool | None = None
    electric_charging_station: bool | None = None
    dishwasher: bool | None = None
    washing_machine: bool | None = None
    dryer: bool | None = None
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
        if self.max_available_from:
            body["max_available_from"] = self.max_available_from
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
            ("social_housing", "social_housing"),
            ("newbuild", "newbuild"),
            ("electric_charging_station", "electric_charging_station"),
            ("dishwasher", "dishwasher"),
            ("washing_machine", "washing_machine"),
            ("dryer", "dryer"),
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
    "max_available_from": None,
    "pet_friendly": None,
    "balcony": None,
    "furnished": None,
    "parking": None,
    "elevator": None,
    "shareable": None,
    "student_only": None,
    "senior_friendly": None,
    "social_housing": None,
    "newbuild": None,
    "electric_charging_station": None,
    "dishwasher": None,
    "washing_machine": None,
    "dryer": None,
    "order": "DEFAULT",
    "max_pages": 5,
}


# -- API Client ------------------------------------------------------------

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
                    f"  HTTP {e.code} -- backing off {wait:.0f}s (attempt {attempt + 1}/{MAX_RETRIES})",
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
                f"  Network error -- retrying in {wait:.0f}s (attempt {attempt + 1}/{MAX_RETRIES})",
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


# -- Seen-Listings Tracker -------------------------------------------------

class SeenTracker:
    """Track which listings have been seen, detecting re-listings.

    Each entry stores ``{"seen_at": <iso>, "advertised_date": <iso|null>}``.
    Legacy entries (plain timestamp strings) are read transparently.
    A listing is considered new if its ID is unseen or its advertised_date
    is newer than the one we recorded.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._seen: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            with open(self._path, encoding="utf-8") as f:
                self._seen = json.load(f)

    def _save(self) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._seen, f, indent=2, ensure_ascii=False)

    @staticmethod
    def _get_ad_date(entry: Any) -> str | None:
        if isinstance(entry, dict):
            return entry.get("advertised_date")
        return None

    def is_new(self, listing_id: int, advertised_date: str | None = None) -> bool:
        key = str(listing_id)
        if key not in self._seen:
            return True
        if advertised_date:
            stored_ad = self._get_ad_date(self._seen[key])
            if stored_ad and advertised_date > stored_ad:
                return True
        return False

    def mark_seen(self, listing_id: int, advertised_date: str | None = None) -> None:
        self._seen[str(listing_id)] = {
            "seen_at": datetime.now(timezone.utc).isoformat(),
            "advertised_date": advertised_date,
        }
        self._save()

    def mark_all_seen(
        self,
        ids: list[int],
        advertised_dates: dict[int, str | None] | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        ad_dates = advertised_dates or {}
        for lid in ids:
            self._seen[str(lid)] = {
                "seen_at": now,
                "advertised_date": ad_dates.get(lid),
            }
        self._save()

    def reset(self) -> int:
        count = len(self._seen)
        self._seen = {}
        self._save()
        return count

    @property
    def count(self) -> int:
        return len(self._seen)

    @property
    def path(self) -> Path:
        return self._path


# -- Logging ---------------------------------------------------------------

def setup_logging(log_file: Path | None, verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s %(levelname)s %(message)s"
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(level=level, format=fmt, handlers=handlers)


# -- CLI -------------------------------------------------------------------

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
    quiet: bool = False,
    json_output: bool = False,
    peek: bool = False,
) -> list[Listing]:
    listings = fetch_listings(config)
    new_listings = [l for l in listings if tracker.is_new(l.id, l.advertised_date)]

    if json_output:
        if new_listings:
            output = [l.to_json_dict() for l in new_listings]
            print(json.dumps(output, ensure_ascii=False))
            if not peek:
                ad_dates = {l.id: l.advertised_date for l in new_listings}
                tracker.mark_all_seen([l.id for l in new_listings], advertised_dates=ad_dates)
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
        ad_dates = {l.id: l.advertised_date for l in new_listings}
        tracker.mark_all_seen([l.id for l in new_listings], advertised_dates=ad_dates)
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
) -> None:
    print(f"Watching every {interval}s (Ctrl+C to stop)...")
    log.info("Watch started -- interval=%ds", interval)
    try:
        while True:
            try:
                run_once(config, tracker)
            except urllib.error.URLError as e:
                log.warning("Network error: %s -- retrying in %ds", e, interval)
            except json.JSONDecodeError as e:
                log.warning("Parse error: %s -- retrying in %ds", e, interval)
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


# -- MCP Server ------------------------------------------------------------

_RESTRICTIVE_FILTERS = {
    "rooms_min", "rooms_max", "max_rent", "min_size_m2", "min_rental_period",
    "max_available_from", "pet_friendly", "balcony", "furnished", "parking",
    "elevator", "shareable", "student_only", "senior_friendly",
    "social_housing", "newbuild", "electric_charging_station",
    "dishwasher", "washing_machine", "dryer",
}


def _build_search_config(
    base: SearchConfig,
    *,
    cities: list[str] | None = None,
    min_lat: float | None = None,
    min_lng: float | None = None,
    max_lat: float | None = None,
    max_lng: float | None = None,
    rooms_min: int | None = None,
    rooms_max: int | None = None,
    max_rent: int | None = None,
    min_size_m2: int | None = None,
    min_rental_period: int | None = None,
    max_available_from: str | None = None,
    pet_friendly: bool | None = None,
    balcony: bool | None = None,
    furnished: bool | None = None,
    parking: bool | None = None,
    elevator: bool | None = None,
    shareable: bool | None = None,
    student_only: bool | None = None,
    senior_friendly: bool | None = None,
    social_housing: bool | None = None,
    newbuild: bool | None = None,
    electric_charging_station: bool | None = None,
    dishwasher: bool | None = None,
    washing_machine: bool | None = None,
    dryer: bool | None = None,
    max_pages: int | None = None,
) -> SearchConfig:
    """Build a SearchConfig from explicit filter arguments.

    If no filter arguments are passed, returns the full base config (saved
    search).  If ANY filter is passed, restrictive filters from the base
    config are stripped — only structural settings (categories, location,
    order, max_pages) carry over, plus whatever the caller explicitly set.

    This is the same logic for both CLI and MCP.
    """
    explicit: dict[str, Any] = {}
    if cities is not None:
        explicit["city_level_1"] = [c.lower() for c in cities]
    if min_lat is not None:
        if None in (min_lng, max_lat, max_lng):
            raise ValueError("All four bbox params (min_lat, min_lng, max_lat, max_lng) must be provided together")
        explicit["min_lat"] = min_lat
        explicit["min_lng"] = min_lng
        explicit["max_lat"] = max_lat
        explicit["max_lng"] = max_lng
    if rooms_min is not None:
        explicit["rooms_min"] = rooms_min
    if rooms_max is not None:
        explicit["rooms_max"] = rooms_max
    if max_rent is not None:
        explicit["max_rent"] = max_rent
    if min_size_m2 is not None:
        explicit["min_size_m2"] = min_size_m2
    if min_rental_period is not None:
        explicit["min_rental_period"] = min_rental_period
    if max_available_from is not None:
        explicit["max_available_from"] = max_available_from
    if pet_friendly is not None:
        explicit["pet_friendly"] = pet_friendly
    if balcony is not None:
        explicit["balcony"] = balcony
    if furnished is not None:
        explicit["furnished"] = furnished
    if parking is not None:
        explicit["parking"] = parking
    if elevator is not None:
        explicit["elevator"] = elevator
    if shareable is not None:
        explicit["shareable"] = shareable
    if student_only is not None:
        explicit["student_only"] = student_only
    if senior_friendly is not None:
        explicit["senior_friendly"] = senior_friendly
    if social_housing is not None:
        explicit["social_housing"] = social_housing
    if newbuild is not None:
        explicit["newbuild"] = newbuild
    if electric_charging_station is not None:
        explicit["electric_charging_station"] = electric_charging_station
    if dishwasher is not None:
        explicit["dishwasher"] = dishwasher
    if washing_machine is not None:
        explicit["washing_machine"] = washing_machine
    if dryer is not None:
        explicit["dryer"] = dryer
    if max_pages is not None:
        explicit["max_pages"] = max_pages

    if not explicit:
        return base

    overrides: dict[str, Any] = {
        k: v for k, v in base.to_dict().items()
        if k not in _RESTRICTIVE_FILTERS
    }
    overrides.update(explicit)

    if "min_lat" in explicit:
        overrides["city_level_1"] = None

    return SearchConfig.from_dict(overrides)


def run_mcp_server(config: SearchConfig, tracker: SeenTracker) -> None:
    """Start a stdio MCP server exposing BoligWatch tools."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        print(
            "MCP mode requires the 'mcp' package. Install it with:\n"
            "  pip install mcp\n"
            "or:\n"
            "  uv pip install mcp",
            file=sys.stderr,
        )
        sys.exit(1)

    mcp = FastMCP(
        "boligwatch",
        instructions=(
            "BoligWatch monitors boligportal.dk for rental listings in Denmark. "
            "Use search_listings to find apartments matching filters, "
            "get_new_listings to see only unseen results, "
            "and mark_seen to track which listings have been reviewed."
        ),
    )

    @mcp.tool()
    def search_listings(
        cities: list[str] | None = None,
        min_lat: float | None = None,
        min_lng: float | None = None,
        max_lat: float | None = None,
        max_lng: float | None = None,
        rooms_min: int | None = None,
        rooms_max: int | None = None,
        max_rent: int | None = None,
        min_size_m2: int | None = None,
        min_rental_period: int | None = None,
        max_available_from: str | None = None,
        pet_friendly: bool | None = None,
        balcony: bool | None = None,
        furnished: bool | None = None,
        parking: bool | None = None,
        elevator: bool | None = None,
        shareable: bool | None = None,
        student_only: bool | None = None,
        senior_friendly: bool | None = None,
        social_housing: bool | None = None,
        newbuild: bool | None = None,
        electric_charging_station: bool | None = None,
        dishwasher: bool | None = None,
        washing_machine: bool | None = None,
        dryer: bool | None = None,
        max_pages: int | None = None,
    ) -> str:
        """Search boligportal.dk for rental listings matching the given filters.

        Returns all matching listings as a JSON array regardless of seen state.

        If no filters are passed, uses the full saved search from the config.
        If any filter is passed, starts from a clean slate — only structural
        settings (location, categories) carry over.

        Args:
            cities: City names to search in (e.g. ["københavn", "frederiksberg"]).
                    Uses the server's default config if not provided.
            min_lat: Bounding box south latitude. When set, replaces city filter.
            min_lng: Bounding box west longitude.
            max_lat: Bounding box north latitude.
            max_lng: Bounding box east longitude.
            rooms_min: Minimum number of rooms.
            rooms_max: Maximum number of rooms.
            max_rent: Maximum monthly rent in DKK.
            min_size_m2: Minimum size in square meters.
            min_rental_period: Minimum lease length in months.
            max_available_from: Latest move-in date (YYYY-MM-DD).
            pet_friendly: Only include pet-friendly listings.
            balcony: Only include listings with a balcony/terrace.
            furnished: Only include furnished listings.
            parking: Only include listings with parking.
            elevator: Only include listings with an elevator.
            shareable: Only include shareable listings.
            student_only: Only include student-only listings.
            senior_friendly: Only include senior-friendly listings.
            social_housing: Only include social housing (almen bolig).
            newbuild: Only include new-build/project rentals (projektudlejning).
            electric_charging_station: Only include listings with EV charging.
            dishwasher: Only include listings with a dishwasher.
            washing_machine: Only include listings with a washing machine.
            dryer: Only include listings with a dryer.
            max_pages: Maximum pages to fetch (18 listings per page, default 5).
        """
        search = _build_search_config(
            config, cities=cities, min_lat=min_lat, min_lng=min_lng,
            max_lat=max_lat, max_lng=max_lng, rooms_min=rooms_min,
            rooms_max=rooms_max, max_rent=max_rent, min_size_m2=min_size_m2,
            min_rental_period=min_rental_period,
            max_available_from=max_available_from,
            pet_friendly=pet_friendly, balcony=balcony, furnished=furnished,
            parking=parking, elevator=elevator, shareable=shareable,
            student_only=student_only, senior_friendly=senior_friendly,
            social_housing=social_housing, newbuild=newbuild,
            electric_charging_station=electric_charging_station,
            dishwasher=dishwasher, washing_machine=washing_machine,
            dryer=dryer, max_pages=max_pages,
        )
        listings = fetch_listings(search)
        return json.dumps([l.to_json_dict() for l in listings], ensure_ascii=False)

    @mcp.tool()
    def get_new_listings(
        cities: list[str] | None = None,
        min_lat: float | None = None,
        min_lng: float | None = None,
        max_lat: float | None = None,
        max_lng: float | None = None,
        rooms_min: int | None = None,
        rooms_max: int | None = None,
        max_rent: int | None = None,
        min_size_m2: int | None = None,
        min_rental_period: int | None = None,
        max_available_from: str | None = None,
        pet_friendly: bool | None = None,
        balcony: bool | None = None,
        furnished: bool | None = None,
        parking: bool | None = None,
        elevator: bool | None = None,
        shareable: bool | None = None,
        student_only: bool | None = None,
        senior_friendly: bool | None = None,
        social_housing: bool | None = None,
        newbuild: bool | None = None,
        electric_charging_station: bool | None = None,
        dishwasher: bool | None = None,
        washing_machine: bool | None = None,
        dryer: bool | None = None,
        max_pages: int | None = None,
        mark_as_seen: bool = False,
    ) -> str:
        """Search boligportal.dk and return only listings not previously seen.

        Behaves like peek mode by default -- does not mark listings as seen
        unless mark_as_seen is True. Returns a JSON array.

        If no filters are passed, uses the full saved search from the config.
        If any filter is passed, starts from a clean slate.

        Args:
            cities: City names to search in (e.g. ["københavn", "frederiksberg"]).
            min_lat: Bounding box south latitude. When set, replaces city filter.
            min_lng: Bounding box west longitude.
            max_lat: Bounding box north latitude.
            max_lng: Bounding box east longitude.
            rooms_min: Minimum number of rooms.
            rooms_max: Maximum number of rooms.
            max_rent: Maximum monthly rent in DKK.
            min_size_m2: Minimum size in square meters.
            min_rental_period: Minimum lease length in months.
            max_available_from: Latest move-in date (YYYY-MM-DD).
            pet_friendly: Only include pet-friendly listings.
            balcony: Only include listings with a balcony/terrace.
            furnished: Only include furnished listings.
            parking: Only include listings with parking.
            elevator: Only include listings with an elevator.
            shareable: Only include shareable listings.
            student_only: Only include student-only listings.
            senior_friendly: Only include senior-friendly listings.
            social_housing: Only include social housing (almen bolig).
            newbuild: Only include new-build/project rentals (projektudlejning).
            electric_charging_station: Only include listings with EV charging.
            dishwasher: Only include listings with a dishwasher.
            washing_machine: Only include listings with a washing machine.
            dryer: Only include listings with a dryer.
            max_pages: Maximum pages to fetch (18 listings per page, default 5).
            mark_as_seen: If True, mark returned listings as seen (default False).
        """
        search = _build_search_config(
            config, cities=cities, min_lat=min_lat, min_lng=min_lng,
            max_lat=max_lat, max_lng=max_lng, rooms_min=rooms_min,
            rooms_max=rooms_max, max_rent=max_rent, min_size_m2=min_size_m2,
            min_rental_period=min_rental_period,
            max_available_from=max_available_from,
            pet_friendly=pet_friendly, balcony=balcony, furnished=furnished,
            parking=parking, elevator=elevator, shareable=shareable,
            student_only=student_only, senior_friendly=senior_friendly,
            social_housing=social_housing, newbuild=newbuild,
            electric_charging_station=electric_charging_station,
            dishwasher=dishwasher, washing_machine=washing_machine,
            dryer=dryer, max_pages=max_pages,
        )
        listings = fetch_listings(search)
        new = [l for l in listings if tracker.is_new(l.id, l.advertised_date)]
        if mark_as_seen and new:
            ad_dates = {l.id: l.advertised_date for l in new}
            tracker.mark_all_seen([l.id for l in new], advertised_dates=ad_dates)
        return json.dumps([l.to_json_dict() for l in new], ensure_ascii=False)

    @mcp.tool()
    def mark_seen(ids: list[int]) -> dict[str, Any]:
        """Mark specific listing IDs as seen so they won't appear in get_new_listings.

        Args:
            ids: List of listing IDs to mark as seen.
        """
        tracker.mark_all_seen(ids)
        return {"marked": len(ids), "total_seen": tracker.count}

    @mcp.tool()
    def reset_seen() -> dict[str, Any]:
        """Clear all seen-listing history. After this, all listings will appear as new."""
        cleared = tracker.reset()
        return {"cleared": cleared}

    @mcp.tool()
    def get_seen_stats() -> dict[str, Any]:
        """Get statistics about the seen-listings tracker."""
        return {
            "total_seen": tracker.count,
            "seen_file": str(tracker.path),
        }

    mcp.run(transport="stdio")


# -- Entry point -----------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Monitor boligportal.dk for new rental listings.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                        Show new listings once
  %(prog)s --watch                                Poll every 5 min
  %(prog)s -w -i 120                              Poll every 2 min
  %(prog)s --rooms-min 2 --rooms-max 4 --max-rent 15000
  %(prog)s --city kobenhavn --city frederiksberg
  %(prog)s --init-config                          Create config template
  %(prog)s --config my_search.json --watch        Use saved config
  %(prog)s --reset                                Clear seen-listings history
  %(prog)s --mcp                                  Start as MCP server
        """,
    )
    parser.add_argument("--watch", "-w", action="store_true", help="continuously poll for new listings")
    parser.add_argument("--interval", "-i", type=int, default=300, help="poll interval in seconds (default: 300)")
    parser.add_argument("--json", action="store_true", dest="json_output", help="output new listings as JSON (for piping to agents)")
    parser.add_argument("--peek", action="store_true", help="like --json but do NOT mark listings as seen (for retry-safe workflows)")
    parser.add_argument("--mark-seen", nargs="+", type=int, metavar="ID", help="mark specific listing IDs as seen")
    parser.add_argument("--config", "-c", type=Path, help="path to config JSON file")
    parser.add_argument("--init-config", action="store_true", help="generate a config template file")
    parser.add_argument("--seen-file", type=Path, default=DEFAULT_SEEN_FILE, help="path to seen-listings tracker")
    parser.add_argument("--log-file", type=Path, default=None, help="write log to file (default: none)")
    parser.add_argument("--verbose", "-v", action="store_true", help="verbose logging")
    parser.add_argument("--reset", action="store_true", help="clear seen-listings history before running")
    parser.add_argument("--mcp", action="store_true", help="start as MCP server (stdio transport)")

    # Inline filter overrides (take precedence over config file)
    parser.add_argument("--city", action="append", dest="cities", help="city to search (can repeat)")
    parser.add_argument("--bbox", type=str, metavar="S,W,N,E",
                        help="bounding box as min_lat,min_lng,max_lat,max_lng (replaces --city)")
    parser.add_argument("--rooms-min", type=int, help="minimum rooms")
    parser.add_argument("--rooms-max", type=int, help="maximum rooms")
    parser.add_argument("--max-rent", type=int, help="maximum monthly rent in DKK")
    parser.add_argument("--min-size", type=int, help="minimum size in m2")
    parser.add_argument("--min-rental-period", type=int, help="minimum lease in months (12 = 1 year)")
    parser.add_argument("--max-pages", type=int, help="max pages to fetch (18 results each)")
    parser.add_argument("--max-available-from", type=str, metavar="YYYY-MM-DD", help="latest move-in date")
    parser.add_argument("--pet-friendly", action="store_true", default=None, help="only pet-friendly")
    parser.add_argument("--balcony", action="store_true", default=None, help="must have balcony/terrace")
    parser.add_argument("--furnished", action="store_true", default=None, help="must be furnished")
    parser.add_argument("--shareable", action="store_true", default=None, help="must be shareable (delevenlig)")
    parser.add_argument("--student-only", action="store_true", default=None, help="student-only listings")
    parser.add_argument("--senior-friendly", action="store_true", default=None, help="senior-friendly listings")
    parser.add_argument("--social-housing", action="store_true", default=None, help="social housing only (almen bolig)")
    parser.add_argument("--newbuild", action="store_true", default=None, help="new-build/project rentals only (projektudlejning)")
    parser.add_argument("--ev-charging", action="store_true", default=None, help="must have EV charging station (ladestander)")
    parser.add_argument("--dishwasher", action="store_true", default=None, help="must have dishwasher")
    parser.add_argument("--washing-machine", action="store_true", default=None, help="must have washing machine")
    parser.add_argument("--dryer", action="store_true", default=None, help="must have dryer")

    args = parser.parse_args()

    if args.init_config:
        init_config(args.config or DEFAULT_CONFIG_FILE)
        return

    base_config = load_config(args.config)

    # Parse bbox into components
    bbox_lat: float | None = None
    bbox_lng: float | None = None
    bbox_lat_max: float | None = None
    bbox_lng_max: float | None = None
    if args.bbox:
        parts = [float(x.strip()) for x in args.bbox.split(",")]
        if len(parts) != 4:
            parser.error("--bbox requires exactly 4 values: min_lat,min_lng,max_lat,max_lng")
        bbox_lat, bbox_lng, bbox_lat_max, bbox_lng_max = parts

    config = _build_search_config(
        base_config,
        cities=args.cities,
        min_lat=bbox_lat,
        min_lng=bbox_lng,
        max_lat=bbox_lat_max,
        max_lng=bbox_lng_max,
        rooms_min=args.rooms_min,
        rooms_max=args.rooms_max,
        max_rent=args.max_rent,
        min_size_m2=args.min_size,
        min_rental_period=args.min_rental_period,
        max_available_from=args.max_available_from,
        pet_friendly=True if args.pet_friendly else None,
        balcony=True if args.balcony else None,
        furnished=True if args.furnished else None,
        shareable=True if args.shareable else None,
        student_only=True if args.student_only else None,
        senior_friendly=True if args.senior_friendly else None,
        social_housing=True if args.social_housing else None,
        newbuild=True if args.newbuild else None,
        electric_charging_station=True if args.ev_charging else None,
        dishwasher=True if args.dishwasher else None,
        washing_machine=True if args.washing_machine else None,
        dryer=True if args.dryer else None,
        max_pages=args.max_pages,
    )

    setup_logging(args.log_file, args.verbose)

    if args.reset and args.seen_file.exists():
        args.seen_file.unlink()
        print("Seen-listings history cleared.")

    tracker = SeenTracker(args.seen_file)

    if args.mcp:
        run_mcp_server(config, tracker)
        return

    if args.mark_seen:
        tracker.mark_all_seen(args.mark_seen)
        print(f"Marked {len(args.mark_seen)} listing(s) as seen.")
        return

    if args.watch:
        watch_loop(config, tracker, args.interval)
    else:
        peek = args.peek
        json_out = args.json_output or peek
        run_once(config, tracker, json_output=json_out, peek=peek)


if __name__ == "__main__":
    main()
