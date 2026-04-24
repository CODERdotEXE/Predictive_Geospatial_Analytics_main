"""OSMnx wrapper for fetching city POIs, roads, and bounding boxes."""

import logging
from typing import Optional, Tuple

import geopandas as gpd

logger = logging.getLogger(__name__)

POI_TAGS = {
    "amenity": ["restaurant", "cafe", "bar", "fast_food", "cinema",
                "theatre", "pharmacy", "marketplace"],
    "shop": ["mall", "supermarket", "convenience", "bakery",
             "department_store", "books"],
    "landuse": ["commercial", "retail"],
}


def _try_import_osmnx():
    try:
        import osmnx as ox
        return ox
    except Exception as e:
        logger.warning("osmnx unavailable (%s). Will use mock data.", e)
        return None


def fetch_city_pois(city_name: str) -> gpd.GeoDataFrame:
    ox = _try_import_osmnx()
    if ox is None:
        return gpd.GeoDataFrame(columns=["geometry", "poi_type"], crs="EPSG:4326")

    try:
        gdf = ox.features_from_place(city_name, tags=POI_TAGS)
    except Exception as e:
        logger.warning("OSM POI fetch failed for %s: %s", city_name, e)
        return gpd.GeoDataFrame(columns=["geometry", "poi_type"], crs="EPSG:4326")

    def resolve_type(row):
        for col in ("amenity", "shop", "landuse"):
            if col in row and isinstance(row[col], str):
                return row[col]
        return "other"

    gdf["poi_type"] = gdf.apply(resolve_type, axis=1)
    gdf["geometry"] = gdf.geometry.centroid
    return gdf[["geometry", "poi_type"]].reset_index(drop=True)


def fetch_city_roads(city_name: str) -> gpd.GeoDataFrame:
    ox = _try_import_osmnx()
    if ox is None:
        return gpd.GeoDataFrame(columns=["geometry", "highway"], crs="EPSG:4326")

    try:
        G = ox.graph_from_place(city_name, network_type="drive", simplify=True)
        edges = ox.graph_to_gdfs(G, nodes=False, edges=True)
        edges["highway"] = edges["highway"].apply(
            lambda x: x[0] if isinstance(x, list) else x
        )
        return edges[["geometry", "highway"]].reset_index(drop=True)
    except Exception as e:
        logger.warning("OSM road fetch failed for %s: %s", city_name, e)
        return gpd.GeoDataFrame(columns=["geometry", "highway"], crs="EPSG:4326")


def get_city_bounds(city_name: str) -> Optional[Tuple[float, float, float, float]]:
    ox = _try_import_osmnx()
    if ox is None:
        # Hardcoded fallbacks for common demo cities so the app works without OSM
        fallbacks = {
            "austin": (-97.94, 30.10, -97.56, 30.52),
            "new york": (-74.26, 40.49, -73.70, 40.92),
            "london": (-0.51, 51.28, 0.33, 51.69),
            "mumbai": (72.77, 18.89, 72.99, 19.27),
            "delhi": (76.84, 28.40, 77.35, 28.88),
            "bangalore": (77.46, 12.83, 77.78, 13.14),
            # "pilani": (75.58, 28.35, 75.65, 28.40),
        }
        key = city_name.lower().split(",")[0].strip()
        if key in fallbacks:
            logger.info("Using fallback bounds for %s", key)
            return fallbacks[key]
        return None

    try:
        gdf = ox.geocode_to_gdf(city_name)
        minx, miny, maxx, maxy = gdf.total_bounds
        return (float(minx), float(miny), float(maxx), float(maxy))
    except Exception as e:
        logger.error("Geocoding failed for %s: %s", city_name, e)
        return None
