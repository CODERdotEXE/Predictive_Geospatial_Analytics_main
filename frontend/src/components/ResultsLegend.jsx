import { motion } from "framer-motion";
import { TrendingUp, BarChart3 } from "lucide-react";

export default function ResultsLegend({ result }) {
  const topCells = [...result.geojson.features]
    .sort(
      (a, b) => b.properties.suitability_score - a.properties.suitability_score
    )
    .slice(0, 5);

  const importances = result.feature_importances || {};
  const importanceEntries = Object.entries(importances).sort(
    (a, b) => b[1] - a[1]
  );

  const featureLabels = {
    population: "Population",
    poi_synergy: "POI Synergy",
    competitor_penalty: "Low Competition",
    connectivity: "Connectivity",
    commercial: "Commercial",
  };

  return (
    <motion.div
      initial={{ y: 100, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.5, delay: 0.2 }}
      className="absolute right-6 top-6 z-10 w-[320px] rounded-2xl border border-white/10 bg-slate-900/70 p-5 shadow-2xl backdrop-blur-xl"
    >
      <div className="mb-4">
        <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
          <BarChart3 className="h-4 w-4 text-emerald-400" />
          Suitability Scale
        </h3>
        <div className="mb-1 h-2 w-full rounded-full bg-gradient-to-r from-[#0f172a] via-[#1e40af] via-[#0891b2] via-[#10b981] to-[#fbbf24]" />
        <div className="flex justify-between text-[10px] text-slate-400">
          <span>Low</span>
          <span>Moderate</span>
          <span>High</span>
          <span>Prime</span>
        </div>
      </div>

      <div className="mb-4 border-t border-white/5 pt-4">
        <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
          <TrendingUp className="h-4 w-4 text-emerald-400" />
          Top 5 Zones
        </h3>
        <ul className="space-y-1.5">
          {topCells.map((f, i) => {
            const p = f.properties;
            return (
              <li
                key={i}
                className="flex items-center justify-between text-xs"
              >
                <span className="text-slate-400">
                  #{i + 1} · Zone {p.hex_id?.slice(-5)}
                </span>
                <span className="font-mono font-semibold text-emerald-300">
                  {(p.suitability_score * 100).toFixed(1)}
                </span>
              </li>
            );
          })}
        </ul>
      </div>

      {importanceEntries.length > 0 && (
        <div className="border-t border-white/5 pt-4">
          <h3 className="mb-2 text-sm font-semibold">Model Feature Importance</h3>
          <ul className="space-y-2">
            {importanceEntries.map(([feat, val]) => (
              <li key={feat} className="text-xs">
                <div className="mb-0.5 flex justify-between">
                  <span className="text-slate-400">
                    {featureLabels[feat] || feat}
                  </span>
                  <span className="font-mono text-slate-300">
                    {(val * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="h-1 w-full overflow-hidden rounded-full bg-white/5">
                  <div
                    className="h-full bg-gradient-to-r from-emerald-500 to-teal-400"
                    style={{ width: `${val * 100}%` }}
                  />
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-4 border-t border-white/5 pt-3 text-[10px] text-slate-500">
        {result.n_cells} cells analyzed · {result.city}
      </div>
    </motion.div>
  );
}
