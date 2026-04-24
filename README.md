# SiteIQ — Predictive Retail Site Selection

ML-powered geospatial web app that scores locations in any city for retail
suitability. Gradient Boosting model + H3 hex grid + Mapbox choropleth.

![stack](https://img.shields.io/badge/stack-FastAPI%20%7C%20React%20%7C%20Mapbox-emerald)

## Features

- **ML Scoring** — Gradient Boosting Regressor (sklearn) trained on synthetic
  data encoding domain heuristics + non-linear interactions
- **Spatial smoothing** — H3 k-ring neighbor averaging for coherent hot zones
- **Live OSM data** — POIs, roads via OSMnx/Overpass (toggleable)
- **Mock fallback** — works instantly without OSM or real demographics
- **Premium UI** — glass-morphism panels, dark Mapbox theme, animated legend

## Project Structure

```
siteiq/
├── backend/
│   ├── main.py                  # FastAPI app
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── scoring/
│   │   ├── __init__.py
│   │   └── engine.py            # ScoringEngine + MLScoringModel
│   └── data/
│       ├── __init__.py
│       └── osm_client.py        # OSMnx wrapper
└── frontend/
    ├── index.html
    ├── package.json
    ├── vite.config.js
    ├── tailwind.config.js
    ├── postcss.config.js
    ├── .env.example
    └── src/
        ├── main.jsx
        ├── App.jsx
        ├── index.css
        └── components/
            ├── AnalysisPanel.jsx
            ├── SiteMap.jsx
            └── ResultsLegend.jsx
```

---

## Quick Start (5 minutes)

### Prerequisites

- Python **3.10+**
- Node.js **18+**
- A free **Mapbox** token — https://account.mapbox.com/access-tokens/

### 1. Backend Setup

```bash
cd backend
python -m venv venv
# macOS/Linux
source venv/bin/activate
# Windows
# venv\Scripts\activate

pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Backend runs at `http://localhost:8000`. Try `http://localhost:8000/docs` for
auto-generated API docs.

**⚠️ Windows GeoPandas/GDAL issues?** Use Docker instead:

```bash
cd backend
docker build -t siteiq-api .
docker run -p 8000:8000 siteiq-api
```

### 2. Frontend Setup

In a **new terminal**:

```bash
cd frontend
npm install

# Copy env template and add your Mapbox token
cp .env.example .env.local
# Edit .env.local — paste your token after VITE_MAPBOX_TOKEN=

npm run dev
```

Frontend runs at `http://localhost:3000`.

### 3. Try It

1. Open `http://localhost:3000`
2. Pick a store type (e.g. Restaurant)
3. Enter company name: `Acme Coffee`
4. Enter city: `Austin` (or `Mumbai`, `Bangalore`, `New York`, `London`)
5. Leave **"Use live OSM data" OFF** for the first run (fast, mock data, ~2s)
6. Click **Run Predictive Analysis**

You should see a choropleth heatmap on the map with suitability scores.
Yellow = prime locations, dark blue = poor locations. Click any hex for details.

Once mock mode works, toggle OSM ON and try again — first call per city takes
30–60s (OSM fetch). Results are dramatically more realistic with real road
networks and POIs.

---

## How the Scoring Works

### Features extracted per hex cell

| Feature | Source | Interpretation |
|---|---|---|
| `population` | Census/WorldPop (mocked) | Target customer density |
| `poi_synergy` | OSM amenities | Complementary businesses nearby |
| `competitor_penalty` | OSM amenities | 1 − competitor count (inverted) |
| `connectivity` | OSM road network | Weighted road km (motorway > residential) |
| `commercial` | OSM shops/retail | Foot-traffic proxy |

### Model

A `GradientBoostingRegressor` (150 trees, depth 4, lr 0.05) is trained per
store type on 5000 synthetic samples. Labels come from:

```
y = Σ wᵢ·xᵢ                                      # weighted sum
  + 0.15·pop·connectivity                         # interaction
  + 0.10·synergy·commercial                       # interaction
  + 0.08·√(low_competition·population)            # interaction
  − 0.12·(1−low_competition)·(1−synergy)          # penalty
  + N(0, 0.03)                                    # noise
```

This captures non-linear synergies that a plain weighted sum misses.
**In production**, replace synthetic labels with real store revenue data and
retrain.

### Spatial smoothing

After prediction, each cell score is blended with its H3 k=1 neighbors:
```
smoothed = 0.65·self + 0.35·mean(neighbors)
```
This removes isolated hot cells that aren't supported by surrounding context.

---

## API Reference

### `POST /api/v1/analyze`

```json
{
  "store_type": "restaurant",
  "company_name": "Acme Coffee",
  "city": "Austin",
  "resolution": 8,
  "use_osm": false
}
```

Returns GeoJSON FeatureCollection with per-cell scores + feature importances.

### `GET /api/v1/store-types`
Lists supported store types and their weight profiles.

### `GET /api/v1/health`
Health check.

---

## Deployment

### Frontend → Vercel

```bash
cd frontend
npm i -g vercel
vercel --prod
```
Set env vars in Vercel dashboard: `VITE_API_URL`, `VITE_MAPBOX_TOKEN`.

### Backend → Render

The included `Dockerfile` works out of the box. On Render:
1. New → Web Service → Docker
2. Point to your repo's `backend/` directory
3. Use **Standard** plan or higher (GeoPandas needs ≥2GB RAM)
4. Health check path: `/api/v1/health`

---

## Troubleshooting

- **"Mapbox token missing"** — create `frontend/.env.local` with your token and restart `npm run dev`
- **"Could not geocode city"** — use `City, Country` format, or pick from the hardcoded fallback list (Austin, New York, London, Mumbai, Delhi, Bangalore, Pilani)
- **OSM fetch is slow** — normal. First call per city can take 60s. Add Redis caching for production.
- **GeoPandas install fails on Windows** — use the Docker route, or install via conda: `conda install -c conda-forge geopandas osmnx`
- **CORS error** — backend allows all origins by default; if you customized, make sure `http://localhost:3000` is in the allow list

---

## Next Steps / Extensions

1. Swap synthetic labels for real store revenue when available
2. Add Redis caching for OSM responses (24h TTL per city)
3. Wire in WorldPop or Census ACS for real population data
4. Add async job queue (Celery/RQ) for large cities
5. Add user auth (Clerk/Auth0) for SaaS deployment
6. Add XGBoost/LightGBM as alternative models, A/B test against GBR

---

## License

MIT — do whatever you want.
