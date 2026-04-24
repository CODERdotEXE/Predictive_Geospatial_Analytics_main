"""
ScoringEngine: ML-powered site-selection scoring using Gradient Boosting.

Pipeline:
  1. Discretize city into H3 hex grid
  2. Extract geospatial features per cell
  3. Normalize features
  4. Predict suitability via a pre-trained GradientBoostingRegressor
     (trained on synthetic labels derived from expert heuristics — in production
     you'd replace the synthetic labels with real store-performance data)
  5. Apply Gaussian spatial smoothing so neighboring cells have coherent scores
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import geopandas as gpd
import h3
import numpy as np
import pandas as pd
from shapely.geometry import Polygon, mapping
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain knowledge encoded as heuristic weights — used to generate synthetic
# training labels. In production, replace with real store revenue labels.
# ---------------------------------------------------------------------------
STORE_TYPE_WEIGHTS: Dict[str, Dict[str, float]] = {
    "restaurant": {"population": 0.30, "poi_synergy": 0.25, "competitor_penalty": 0.15,
                   "connectivity": 0.15, "commercial": 0.15},
    "theater":    {"population": 0.25, "poi_synergy": 0.30, "competitor_penalty": 0.10,
                   "connectivity": 0.25, "commercial": 0.10},
    "mall":       {"population": 0.35, "poi_synergy": 0.10, "competitor_penalty": 0.20,
                   "connectivity": 0.25, "commercial": 0.10},
    "cafe":       {"population": 0.25, "poi_synergy": 0.25, "competitor_penalty": 0.20,
                   "connectivity": 0.10, "commercial": 0.20},
    "grocery":    {"population": 0.40, "poi_synergy": 0.10, "competitor_penalty": 0.25,
                   "connectivity": 0.15, "commercial": 0.10},
}

SYNERGY_MAP: Dict[str, Dict[str, List[str]]] = {
    "restaurant": {"synergy": ["cinema", "theatre", "mall", "cafe", "bar"],
                   "competitor": ["restaurant", "fast_food"]},
    "theater":    {"synergy": ["restaurant", "cafe", "bar", "mall"],
                   "competitor": ["cinema", "theatre"]},
    "mall":       {"synergy": ["restaurant", "cinema", "cafe"],
                   "competitor": ["mall", "department_store"]},
    "cafe":       {"synergy": ["bookshop", "university", "mall"],
                   "competitor": ["cafe"]},
    "grocery":    {"synergy": ["pharmacy", "bakery"],
                   "competitor": ["supermarket", "convenience"]},
}

FEATURE_COLS = ["population", "poi_synergy", "competitor_penalty",
                "connectivity", "commercial"]


@dataclass
class CityBounds:
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float

    def to_polygon(self) -> Polygon:
        return Polygon([
            (self.min_lon, self.min_lat), (self.max_lon, self.min_lat),
            (self.max_lon, self.max_lat), (self.min_lon, self.max_lat),
        ])


class MLScoringModel:
    """
    Per-store-type Gradient Boosting model.

    Trained on synthetic samples where labels come from the heuristic weighted
    sum PLUS non-linear interaction terms (e.g., population * connectivity
    bonus) PLUS random noise. This simulates the kind of complex, non-linear
    relationships that real store revenue data exhibits.
    """

    def __init__(self, store_type: str, n_samples: int = 5000, seed: int = 42):
        self.store_type = store_type
        self.weights = STORE_TYPE_WEIGHTS[store_type]
        self.scaler = StandardScaler()
        self.model = GradientBoostingRegressor(
            n_estimators=150,
            max_depth=4,
            learning_rate=0.05,
            min_samples_split=20,
            subsample=0.8,
            random_state=seed,
        )
        self._train(n_samples, seed)

    def _generate_synthetic_data(self, n: int, seed: int) -> Tuple[np.ndarray, np.ndarray]:
        """Generate synthetic (features, labels) using heuristics + interactions."""
        rng = np.random.RandomState(seed)
        X = rng.beta(a=2, b=5, size=(n, len(FEATURE_COLS)))  # skewed toward low values

        w = self.weights
        # Linear component (the expert-weighted sum)
        linear = (
            w["population"] * X[:, 0] +
            w["poi_synergy"] * X[:, 1] +
            w["competitor_penalty"] * X[:, 2] +
            w["connectivity"] * X[:, 3] +
            w["commercial"] * X[:, 4]
        )
        # Non-linear interaction bonuses — real-world synergies
        interaction = (
            0.15 * X[:, 0] * X[:, 3] +          # population × connectivity
            0.10 * X[:, 1] * X[:, 4] +          # poi synergy × commercial
            0.08 * np.sqrt(X[:, 2] * X[:, 0])   # low-competition × population
        )
        # Penalize bad combos (high competition + low synergy kills a site)
        penalty = 0.12 * (1 - X[:, 2]) * (1 - X[:, 1])

        y = linear + interaction - penalty + rng.normal(0, 0.03, n)
        y = np.clip(y, 0, 1)
        return X, y

    def _train(self, n: int, seed: int) -> None:
        X, y = self._generate_synthetic_data(n, seed)
        Xs = self.scaler.fit_transform(X)
        self.model.fit(Xs, y)
        logger.info("Trained ML model for '%s': train R² = %.3f",
                    self.store_type, self.model.score(Xs, y))

    def predict(self, features: np.ndarray) -> np.ndarray:
        Xs = self.scaler.transform(features)
        preds = self.model.predict(Xs)
        return np.clip(preds, 0, 1)

    def feature_importances(self) -> Dict[str, float]:
        return dict(zip(FEATURE_COLS, self.model.feature_importances_.tolist()))


class ScoringEngine:
    """Grid builder + feature extractor + ML scorer + spatial smoother."""

    def __init__(self, h3_resolution: int = 8):
        self.h3_resolution = h3_resolution
        # Lazy cache: train a model per store type on first use
        self._models: Dict[str, MLScoringModel] = {}

    def _get_model(self, store_type: str) -> MLScoringModel:
        if store_type not in self._models:
            self._models[store_type] = MLScoringModel(store_type)
        return self._models[store_type]

    # -------------------- Grid --------------------
    def build_hex_grid(self, bounds: CityBounds) -> gpd.GeoDataFrame:
        poly_geojson = mapping(bounds.to_polygon())
        try:
            # h3 v4 API
            hex_ids = h3.polygon_to_cells(
                h3.LatLngPoly([(lat, lon) for lon, lat in poly_geojson["coordinates"][0]]),
                self.h3_resolution,
            )
        except AttributeError:
            # h3 v3 fallback
            hex_ids = h3.polyfill(poly_geojson, self.h3_resolution, geo_json_conformant=True)

        records = []
        for hex_id in hex_ids:
            try:
                boundary = h3.cell_to_boundary(hex_id)
            except AttributeError:
                boundary = h3.h3_to_geo_boundary(hex_id)
            poly = Polygon([(lon, lat) for lat, lon in boundary])
            records.append({
                "hex_id": hex_id,
                "geometry": poly,
                "centroid_lon": poly.centroid.x,
                "centroid_lat": poly.centroid.y,
            })

        gdf = gpd.GeoDataFrame(records, crs="EPSG:4326")
        logger.info("Built hex grid: %d cells at resolution %d", len(gdf), self.h3_resolution)
        return gdf

    # -------------------- Feature extraction --------------------
    def compute_population_feature(
        self, grid: gpd.GeoDataFrame, population_gdf: Optional[gpd.GeoDataFrame]
    ) -> pd.Series:
        if population_gdf is None or population_gdf.empty:
            city_center = grid.geometry.unary_union.centroid
            dists = grid.geometry.centroid.distance(city_center)
            mock = np.exp(-dists / max(dists.max(), 1e-9) * 2.5) * 10000
            # add noise so it's not too clean
            rng = np.random.RandomState(0)
            mock = mock * (0.7 + 0.6 * rng.random(len(mock)))
            return pd.Series(mock.values, index=grid["hex_id"])

        joined = gpd.sjoin(population_gdf, grid, how="inner", predicate="within")
        return joined.groupby("hex_id")["population"].sum().reindex(
            grid["hex_id"], fill_value=0
        )

    def compute_poi_features(
        self, grid: gpd.GeoDataFrame, pois_gdf: Optional[gpd.GeoDataFrame], store_type: str
    ) -> Tuple[pd.Series, pd.Series]:
        synergy_tags = SYNERGY_MAP.get(store_type, {}).get("synergy", [])
        competitor_tags = SYNERGY_MAP.get(store_type, {}).get("competitor", [])

        if pois_gdf is None or pois_gdf.empty:
            rng = np.random.RandomState(1)
            # mock: synergy higher near center, competition spread more evenly
            n = len(grid)
            center = grid.geometry.unary_union.centroid
            d = grid.geometry.centroid.distance(center).values
            d_norm = d / max(d.max(), 1e-9)
            synergy = (1 - d_norm) * rng.uniform(5, 30, n)
            comp = rng.uniform(0, 15, n)
            return (pd.Series(synergy, index=grid["hex_id"]),
                    pd.Series(comp, index=grid["hex_id"]))

        grid_proj = grid.to_crs(epsg=3857)
        grid_proj["geometry"] = grid_proj.geometry.buffer(200)
        buffered = grid_proj.to_crs(epsg=4326)

        joined = gpd.sjoin(pois_gdf, buffered, how="inner", predicate="within")
        synergy = (joined[joined["poi_type"].isin(synergy_tags)]
                   .groupby("hex_id").size().reindex(grid["hex_id"], fill_value=0))
        comp = (joined[joined["poi_type"].isin(competitor_tags)]
                .groupby("hex_id").size().reindex(grid["hex_id"], fill_value=0))
        return synergy, comp

    def compute_connectivity_feature(
        self, grid: gpd.GeoDataFrame, road_gdf: Optional[gpd.GeoDataFrame]
    ) -> pd.Series:
        if road_gdf is None or road_gdf.empty:
            rng = np.random.RandomState(2)
            # mock: mild radial pattern + noise
            center = grid.geometry.unary_union.centroid
            d = grid.geometry.centroid.distance(center).values
            d_norm = d / max(d.max(), 1e-9)
            vals = (1 - 0.6 * d_norm) * rng.uniform(0.5, 1.5, len(grid))
            return pd.Series(vals, index=grid["hex_id"])

        roads_proj = road_gdf.to_crs(epsg=3857)
        grid_proj = grid.to_crs(epsg=3857)
        weights = {"motorway": 3.0, "trunk": 2.5, "primary": 2.0,
                   "secondary": 1.5, "tertiary": 1.0, "residential": 0.5}
        roads_proj["weight"] = roads_proj["highway"].map(weights).fillna(0.3)
        joined = gpd.sjoin(roads_proj, grid_proj, how="inner", predicate="intersects")
        joined["wl"] = joined.geometry.length * joined["weight"]
        return joined.groupby("hex_id")["wl"].sum().reindex(grid["hex_id"], fill_value=0)

    def compute_commercial_feature(
        self, grid: gpd.GeoDataFrame, pois_gdf: Optional[gpd.GeoDataFrame]
    ) -> pd.Series:
        if pois_gdf is None or pois_gdf.empty:
            rng = np.random.RandomState(3)
            center = grid.geometry.unary_union.centroid
            d = grid.geometry.centroid.distance(center).values
            d_norm = d / max(d.max(), 1e-9)
            vals = (1 - 0.7 * d_norm) * rng.uniform(0, 20, len(grid))
            return pd.Series(vals, index=grid["hex_id"])

        comm_tags = {"shop", "marketplace", "mall", "supermarket", "retail", "commercial"}
        comm = pois_gdf[pois_gdf["poi_type"].isin(comm_tags)]
        if comm.empty:
            return pd.Series(0, index=grid["hex_id"])
        joined = gpd.sjoin(comm, grid, how="inner", predicate="within")
        return joined.groupby("hex_id").size().reindex(grid["hex_id"], fill_value=0)

    # -------------------- Spatial smoothing --------------------
    def _spatial_smooth(self, grid: gpd.GeoDataFrame, scores: np.ndarray,
                        k_ring: int = 1, alpha: float = 0.6) -> np.ndarray:
        """
        Smooth scores using H3 k-ring neighbors. Each cell = alpha*self + (1-alpha)*mean(neighbors).
        Prevents isolated 'hot' cells with no corroboration from nearby areas.
        """
        hex_to_idx = {h: i for i, h in enumerate(grid["hex_id"].values)}
        smoothed = scores.copy()
        for i, hex_id in enumerate(grid["hex_id"].values):
            try:
                neighbors = h3.grid_disk(hex_id, k_ring)
            except AttributeError:
                neighbors = h3.k_ring(hex_id, k_ring)
            neighbor_scores = [scores[hex_to_idx[n]] for n in neighbors
                               if n in hex_to_idx and n != hex_id]
            if neighbor_scores:
                smoothed[i] = alpha * scores[i] + (1 - alpha) * np.mean(neighbor_scores)
        return smoothed

    # -------------------- Main pipeline --------------------
    def score_city(
        self,
        bounds: CityBounds,
        store_type: str,
        pois_gdf: Optional[gpd.GeoDataFrame] = None,
        roads_gdf: Optional[gpd.GeoDataFrame] = None,
        population_gdf: Optional[gpd.GeoDataFrame] = None,
    ) -> Dict:
        if store_type not in STORE_TYPE_WEIGHTS:
            raise ValueError(f"Unknown store_type '{store_type}'. "
                             f"Valid: {list(STORE_TYPE_WEIGHTS.keys())}")

        grid = self.build_hex_grid(bounds)
        if len(grid) == 0:
            raise ValueError("Grid is empty — city bbox may be too small for this H3 resolution")

        # Extract raw features
        pop = self.compute_population_feature(grid, population_gdf)
        synergy, competitors = self.compute_poi_features(grid, pois_gdf, store_type)
        connectivity = self.compute_connectivity_feature(grid, roads_gdf)
        commercial = self.compute_commercial_feature(grid, pois_gdf)

        features_df = pd.DataFrame({
            "population": pop,
            "poi_synergy": synergy,
            "competitor_raw": competitors,
            "connectivity": connectivity,
            "commercial": commercial,
        }).fillna(0)

        # Per-feature min-max normalize to [0, 1]
        def _norm(s: pd.Series) -> pd.Series:
            lo, hi = s.min(), s.max()
            return (s - lo) / (hi - lo) if hi > lo else pd.Series(0.5, index=s.index)

        norm = pd.DataFrame({c: _norm(features_df[c]) for c in features_df.columns})
        norm["competitor_penalty"] = 1.0 - norm["competitor_raw"]

        # ML prediction
        model = self._get_model(store_type)
        X = norm[FEATURE_COLS].values
        raw_scores = model.predict(X)

        # Spatial smoothing
        smoothed = self._spatial_smooth(grid, raw_scores, k_ring=1, alpha=0.65)
        # Re-normalize smoothed scores to fill [0, 1] range for better visualization
        if smoothed.max() > smoothed.min():
            smoothed = (smoothed - smoothed.min()) / (smoothed.max() - smoothed.min())

        # Attach to grid
        grid["suitability_score"] = smoothed
        for c in FEATURE_COLS:
            grid[c] = norm[c].values

        # Convert to GeoJSON
        import json
        geojson = json.loads(grid[
            ["hex_id", "geometry", "suitability_score"] + FEATURE_COLS
        ].to_json())

        return {
            "geojson": geojson,
            "feature_importances": model.feature_importances(),
            "n_cells": len(grid),
        }
