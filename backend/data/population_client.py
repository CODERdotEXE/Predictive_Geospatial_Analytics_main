"""Load real population data for a city using cached WorldPop rasters."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple
from urllib.parse import urlparse

import h3
import numpy as np
import pandas as pd
import pycountry
import rasterio
import requests
from rasterio.transform import xy
from rasterio.windows import Window, from_bounds

from data.osm_client import _try_import_osmnx


logger = logging.getLogger(__name__)

WORLDPOP_API_ROOT = "https://www.worldpop.org/rest/data/pop"
WORLDPOP_CACHE_DIR = Path(__file__).resolve().parents[1] / "cache" / "population" / "worldpop"
WORLDPOP_HTTP_HEADERS = {
    "User-Agent": "SiteIQ/1.0 (https://www.worldpop.org/)",
}

CURRENT_YEAR = date.today().year
WORLDPOP_DATASETS = (
    {
        "alias": os.getenv("WORLDPOP_PRIMARY_ALIAS", "G2_CN_POP_R25A_1km"),
        "target_year": int(os.getenv("WORLDPOP_PRIMARY_YEAR", str(max(CURRENT_YEAR - 1, 2015)))),
    },
    {
        "alias": os.getenv("WORLDPOP_FALLBACK_ALIAS", "wpicuadj1km"),
        "target_year": int(os.getenv("WORLDPOP_FALLBACK_YEAR", "2020")),
    },
)

CITY_COUNTRY_FALLBACKS: Dict[str, str] = {
    "austin": "United States",
    "new york": "United States",
    "london": "United Kingdom",
    "mumbai": "India",
    "delhi": "India",
    "bangalore": "India",
    "bengaluru": "India",
    "pilani": "India",
}

COUNTRY_ISO3_ALIASES: Dict[str, str] = {
    "Bolivia": "BOL",
    "Czechia": "CZE",
    "Democratic Republic of the Congo": "COD",
    "Iran": "IRN",
    "Laos": "LAO",
    "Micronesia": "FSM",
    "Moldova": "MDA",
    "North Korea": "PRK",
    "Palestine": "PSE",
    "Russia": "RUS",
    "South Korea": "KOR",
    "Syria": "SYR",
    "Taiwan": "TWN",
    "Tanzania": "TZA",
    "United States": "USA",
    "Venezuela": "VEN",
    "Vietnam": "VNM",
}


@dataclass(frozen=True)
class WorldPopDataset:
    alias: str
    iso3: str
    year: int
    url: str


def fetch_city_population(
    city_name: str,
    bounds: Tuple[float, float, float, float],
    h3_resolution: int,
) -> pd.DataFrame:
    """Return per-H3-cell population totals for the city bounds."""
    iso3 = _resolve_city_iso3(city_name)
    if not iso3:
        logger.warning("Could not resolve country ISO3 for %s", city_name)
        return pd.DataFrame(columns=["hex_id", "population"])

    dataset = _resolve_worldpop_dataset(iso3)
    if dataset is None:
        logger.warning("No WorldPop dataset available for ISO3=%s", iso3)
        return pd.DataFrame(columns=["hex_id", "population"])

    raster_path = _ensure_cached_raster(dataset)
    population = _extract_population_by_h3(raster_path, bounds, h3_resolution)
    logger.info(
        "Loaded WorldPop population for %s using %s %s (%d populated hexes)",
        city_name,
        dataset.alias,
        dataset.year,
        len(population),
    )
    return population


def _resolve_city_iso3(city_name: str) -> Optional[str]:
    country_name = _resolve_country_name(city_name)
    if not country_name:
        return None
    return _country_name_to_iso3(country_name)


def _resolve_country_name(city_name: str) -> Optional[str]:
    key = city_name.lower().split(",")[0].strip()
    if key in CITY_COUNTRY_FALLBACKS:
        return CITY_COUNTRY_FALLBACKS[key]

    if "," in city_name:
        explicit_country = city_name.split(",")[-1].strip()
        iso3 = _country_name_to_iso3(explicit_country)
        if iso3:
            return explicit_country

    ox = _try_import_osmnx()
    if ox is None:
        return None

    try:
        gdf = ox.geocode_to_gdf(city_name)
    except Exception as exc:
        logger.warning("Population geocode failed for %s: %s", city_name, exc)
        return None

    if gdf.empty:
        return None

    display_name = str(gdf.iloc[0].get("display_name", "")).strip()
    if not display_name:
        return None
    return display_name.split(",")[-1].strip()


def _country_name_to_iso3(country_name: str) -> Optional[str]:
    country_name = country_name.strip()
    if not country_name:
        return None

    if country_name in COUNTRY_ISO3_ALIASES:
        return COUNTRY_ISO3_ALIASES[country_name]

    try:
        return pycountry.countries.lookup(country_name).alpha_3
    except LookupError:
        pass

    try:
        return pycountry.countries.search_fuzzy(country_name)[0].alpha_3
    except LookupError:
        logger.warning("Could not map country name '%s' to ISO3", country_name)
        return None


def _resolve_worldpop_dataset(iso3: str) -> Optional[WorldPopDataset]:
    for candidate in WORLDPOP_DATASETS:
        try:
            response = requests.get(
                f"{WORLDPOP_API_ROOT}/{candidate['alias']}",
                params={"iso3": iso3},
                headers=WORLDPOP_HTTP_HEADERS,
                timeout=30,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning(
                "WorldPop API lookup failed for %s (%s): %s",
                iso3,
                candidate["alias"],
                exc,
            )
            continue

        entries = response.json().get("data", [])
        dataset = _select_dataset_entry(entries, iso3, candidate["alias"], candidate["target_year"])
        if dataset is not None:
            return dataset

    return None


def _select_dataset_entry(
    entries: Iterable[dict],
    iso3: str,
    alias: str,
    target_year: int,
) -> Optional[WorldPopDataset]:
    candidates = []
    for entry in entries:
        try:
            year = int(entry["popyear"])
            url = entry["files"][0]
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        candidates.append((year, url))

    if not candidates:
        return None

    prior_years = [item for item in candidates if item[0] <= target_year]
    year, url = max(prior_years or candidates, key=lambda item: item[0])
    return WorldPopDataset(alias=alias, iso3=iso3, year=year, url=url)


def _ensure_cached_raster(dataset: WorldPopDataset) -> Path:
    WORLDPOP_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    source_name = Path(urlparse(dataset.url).path).name
    cache_name = f"{dataset.iso3}_{dataset.year}_{dataset.alias}_{source_name}"
    raster_path = WORLDPOP_CACHE_DIR / cache_name
    if raster_path.exists() and raster_path.stat().st_size > 0:
        return raster_path

    temp_path = raster_path.with_suffix(raster_path.suffix + ".part")
    logger.info("Downloading WorldPop raster: %s", dataset.url)
    try:
        with requests.get(
            dataset.url,
            headers=WORLDPOP_HTTP_HEADERS,
            stream=True,
            timeout=120,
        ) as response:
            response.raise_for_status()
            with temp_path.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        handle.write(chunk)
    except requests.RequestException:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise

    temp_path.replace(raster_path)
    return raster_path


def _extract_population_by_h3(
    raster_path: Path,
    bounds: Tuple[float, float, float, float],
    h3_resolution: int,
) -> pd.DataFrame:
    min_lon, min_lat, max_lon, max_lat = bounds

    with rasterio.open(raster_path) as src:
        window = from_bounds(min_lon, min_lat, max_lon, max_lat, src.transform)
        full_window = Window(0, 0, src.width, src.height)
        window = window.round_offsets().round_lengths().intersection(full_window)
        if window.width <= 0 or window.height <= 0:
            return pd.DataFrame(columns=["hex_id", "population"])

        band = src.read(1, window=window, masked=True)
        if band.size == 0:
            return pd.DataFrame(columns=["hex_id", "population"])

        valid = (~band.mask) & np.isfinite(band) & (band > 0)
        rows, cols = np.where(valid)
        if len(rows) == 0:
            return pd.DataFrame(columns=["hex_id", "population"])

        window_transform = src.window_transform(window)
        xs, ys = xy(window_transform, rows, cols, offset="center")
        xs = np.asarray(xs)
        ys = np.asarray(ys)

        in_bounds = (
            (xs >= min_lon)
            & (xs <= max_lon)
            & (ys >= min_lat)
            & (ys <= max_lat)
        )
        if not np.any(in_bounds):
            return pd.DataFrame(columns=["hex_id", "population"])

        xs = xs[in_bounds]
        ys = ys[in_bounds]
        pop_values = np.asarray(band[rows[in_bounds], cols[in_bounds]], dtype=float)

    cell_ids = [_latlng_to_cell(lat, lon, h3_resolution) for lon, lat in zip(xs, ys)]
    df = pd.DataFrame({"hex_id": cell_ids, "population": pop_values})
    return df.groupby("hex_id", as_index=False)["population"].sum()


def _latlng_to_cell(lat: float, lon: float, resolution: int) -> str:
    try:
        return h3.latlng_to_cell(lat, lon, resolution)
    except AttributeError:
        return h3.geo_to_h3(lat, lon, resolution)
