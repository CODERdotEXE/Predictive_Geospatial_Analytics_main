"""
SiteIQ FastAPI backend.

Run:
    uvicorn main:app --reload --port 8000
"""

import logging
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from data.osm_client import fetch_city_pois, fetch_city_roads, get_city_bounds
from scoring.engine import CityBounds, ScoringEngine, STORE_TYPE_WEIGHTS


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="SiteIQ API",
    description="ML-powered geospatial site selection for retail",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # lock down in production
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

engine = ScoringEngine(h3_resolution=8)


class AnalyzeRequest(BaseModel):
    store_type: str = Field(..., description="One of: restaurant, theater, mall, cafe, grocery")
    company_name: str = Field(..., max_length=120)
    city: str = Field(..., description="E.g. 'Austin, Texas, USA'")
    resolution: Optional[int] = Field(8, ge=6, le=10)
    use_osm: Optional[bool] = Field(
        True,
        description="If false, skips OSM fetch and uses mock data (fast, for demos)",
    )


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/api/v1/store-types")
def list_store_types():
    return {
        "store_types": list(STORE_TYPE_WEIGHTS.keys()),
        "weights": STORE_TYPE_WEIGHTS,
    }


@app.post("/api/v1/analyze")
def analyze(req: AnalyzeRequest):
    if req.store_type not in STORE_TYPE_WEIGHTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported store_type. Use one of {list(STORE_TYPE_WEIGHTS.keys())}",
        )

    logger.info("Analyze: %s | %s | %s", req.store_type, req.company_name, req.city)

    bounds_tuple = get_city_bounds(req.city)
    if not bounds_tuple:
        raise HTTPException(
            status_code=404,
            detail=f"Could not geocode city '{req.city}'. Try 'City, Country' format.",
        )
    bounds = CityBounds(*bounds_tuple)

    if req.use_osm:
        pois = fetch_city_pois(req.city)
        roads = fetch_city_roads(req.city)
        logger.info("Fetched %d POIs, %d road segments", len(pois), len(roads))
    else:
        import geopandas as gpd
        pois = gpd.GeoDataFrame(columns=["geometry", "poi_type"], crs="EPSG:4326")
        roads = gpd.GeoDataFrame(columns=["geometry", "highway"], crs="EPSG:4326")
        logger.info("Skipping OSM — using mock data")

    engine.h3_resolution = req.resolution or 8
    try:
        result = engine.score_city(
            bounds=bounds,
            store_type=req.store_type,
            pois_gdf=pois if not pois.empty else None,
            roads_gdf=roads if not roads.empty else None,
            population_gdf=None,
        )
    except Exception as e:
        logger.exception("Scoring failed")
        raise HTTPException(status_code=500, detail=f"Scoring error: {e}")

    return {
        "city": req.city,
        "store_type": req.store_type,
        "company_name": req.company_name,
        "bounds": {
            "min_lon": bounds.min_lon, "min_lat": bounds.min_lat,
            "max_lon": bounds.max_lon, "max_lat": bounds.max_lat,
        },
        "n_cells": result["n_cells"],
        "feature_importances": result["feature_importances"],
        "geojson": result["geojson"],
        "weights_used": STORE_TYPE_WEIGHTS[req.store_type],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
