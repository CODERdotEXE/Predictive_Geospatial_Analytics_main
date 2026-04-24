import { useEffect, useRef } from "react";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN;

export default function SiteMap({ result, loading }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    if (!MAPBOX_TOKEN) {
      console.warn("No Mapbox token set. Set VITE_MAPBOX_TOKEN in .env.local");
      return;
    }

    mapboxgl.accessToken = MAPBOX_TOKEN;
    mapRef.current = new mapboxgl.Map({
      container: containerRef.current,
      // style: "mapbox://styles/mapbox/standard-satellite",
      style: "mapbox://styles/mapbox/satellite-streets-v12",
      center: [77.2090, 28.6139],
      zoom: 10,
      attributionControl: false,
    });
    mapRef.current.addControl(new mapboxgl.NavigationControl(), "bottom-right");
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !result) return;

    const apply = () => {
      const SOURCE = "suitability-src";
      const FILL = "suitability-fill";
      const OUTLINE = "suitability-outline";

      if (map.getLayer(OUTLINE)) map.removeLayer(OUTLINE);
      if (map.getLayer(FILL)) map.removeLayer(FILL);
      if (map.getSource(SOURCE)) map.removeSource(SOURCE);

      map.addSource(SOURCE, { type: "geojson", data: result.geojson });

      map.addLayer({
        id: FILL,
        type: "fill",
        source: SOURCE,
        paint: {
          "fill-color": [
            "interpolate", ["linear"], ["get", "suitability_score"],
            0.0, "#0f172a",
            0.25, "#1e40af",
            0.5, "#0891b2",
            0.75, "#10b981",
            1.0, "#fbbe24",
          ],
          "fill-opacity": 0.5,
        },
      });

      map.addLayer({
        id: OUTLINE,
        type: "line",
        source: SOURCE,
        paint: {
          "line-color": "rgba(255,255,255,0.15)",
          "line-width": 0.5,
        },
      });

      const b = result.bounds;
      map.fitBounds(
        [[b.min_lon, b.min_lat], [b.max_lon, b.max_lat]],
        { padding: 80, duration: 1200 }
      );

      map.on("click", FILL, (e) => {
        const f = e.features?.[0];
        if (!f) return;
        const p = f.properties;
        new mapboxgl.Popup()
          .setLngLat(e.lngLat)
          .setHTML(`
            <div style="font-family:system-ui;padding:4px 6px;min-width:160px;">
              <div style="font-weight:600;font-size:13px;margin-bottom:6px;color:#34d399;">
                Suitability: ${(p.suitability_score * 100).toFixed(1)}
              </div>
              <div style="font-size:11px;color:#94a3b8;line-height:1.7;">
                <div>Population: ${(p.population * 100).toFixed(0)}</div>
                <div>POI Synergy: ${(p.poi_synergy * 100).toFixed(0)}</div>
                <div>Low Competition: ${(p.competitor_penalty * 100).toFixed(0)}</div>
                <div>Connectivity: ${(p.connectivity * 100).toFixed(0)}</div>
                <div>Commercial: ${(p.commercial * 100).toFixed(0)}</div>
              </div>
            </div>
          `)
          .addTo(map);
      });

      map.on("mouseenter", FILL, () => (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", FILL, () => (map.getCanvas().style.cursor = ""));
    };

    if (map.loaded()) apply();
    else map.once("load", apply);
  }, [result]);

  return (
    <>
      <div ref={containerRef} className="absolute inset-0" />
      {!MAPBOX_TOKEN && (
        <div className="absolute inset-0 flex items-center justify-center bg-slate-950">
          <div className="max-w-md rounded-xl border border-amber-400/30 bg-amber-500/10 p-6 text-center text-amber-200">
            <p className="mb-2 font-semibold">Mapbox token missing</p>
            <p className="text-sm">
              Create <code className="rounded bg-black/30 px-1">frontend/.env.local</code> with
              <br />
              <code className="mt-2 inline-block rounded bg-black/30 px-1">
                VITE_MAPBOX_TOKEN=pk.your_token
              </code>
            </p>
          </div>
        </div>
      )}
      {loading && (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-slate-950/40 backdrop-blur-sm">
          <div className="rounded-xl border border-white/10 bg-slate-900/90 px-6 py-4 shadow-2xl">
            <div className="flex items-center gap-3">
              <div className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
              <span className="text-sm text-slate-300">
                Crunching geospatial features…
              </span>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
