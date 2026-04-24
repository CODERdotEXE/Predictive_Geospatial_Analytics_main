import { useState } from "react";
import { motion } from "framer-motion";
import { Store, Building2, MapPin, Sparkles, Loader2, Zap } from "lucide-react";

const STORE_TYPES = [
  { value: "restaurant", label: "Restaurant", icon: "🍽️" },
  { value: "cafe", label: "Café", icon: "☕" },
  { value: "theater", label: "Theater", icon: "🎭" },
  { value: "mall", label: "Mall", icon: "🏬" },
  { value: "grocery", label: "Grocery", icon: "🛒" },
];

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export default function AnalysisPanel({ onResult, loading, setLoading }) {
  const [storeType, setStoreType] = useState("restaurant");
  const [companyName, setCompanyName] = useState("");
  const [city, setCity] = useState("");
  const [useOsm, setUseOsm] = useState(false); // default off = fast demo
  const [error, setError] = useState(null);

  const handleSubmit = async () => {
    if (!companyName.trim() || !city.trim()) {
      setError("Please fill in all fields.");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/v1/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          store_type: storeType,
          company_name: companyName,
          city,
          resolution: 8,
          use_osm: useOsm,
        }),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `HTTP ${res.status}`);
      }
      const data = await res.json();
      onResult(data);
    } catch (e) {
      setError(e.message || "Analysis failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <motion.aside
      initial={{ x: -400, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ duration: 0.5, ease: "easeOut" }}
      className="absolute left-6 top-6 z-10 w-[380px] rounded-2xl border border-white/10 bg-slate-900/70 p-6 shadow-2xl backdrop-blur-xl"
    >
      <header className="mb-6">
        <div className="mb-2 flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-emerald-400" />
          <h1 className="text-xl font-semibold tracking-tight">SiteIQ</h1>
        </div>
        <p className="text-sm text-slate-400">
          ML-powered retail site selection using geospatial intelligence.
        </p>
      </header>

      <label className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-slate-400">
        <Store className="h-3.5 w-3.5" /> Store Type
      </label>
      <div className="mb-5 grid grid-cols-3 gap-2">
        {STORE_TYPES.map((t) => (
          <button
            key={t.value}
            onClick={() => setStoreType(t.value)}
            className={`rounded-lg border px-3 py-2.5 text-xs font-medium transition ${
              storeType === t.value
                ? "border-emerald-400/50 bg-emerald-400/10 text-emerald-300"
                : "border-white/5 bg-white/[0.02] text-slate-300 hover:border-white/20"
            }`}
          >
            <div className="text-lg leading-none">{t.icon}</div>
            <div className="mt-1">{t.label}</div>
          </button>
        ))}
      </div>

      <label className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-slate-400">
        <Building2 className="h-3.5 w-3.5" /> Company Name
      </label>
      <input
        value={companyName}
        onChange={(e) => setCompanyName(e.target.value)}
        placeholder="Acme Coffee Co."
        className="mb-4 w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2.5 text-sm placeholder:text-slate-500 focus:border-emerald-400/50 focus:outline-none focus:ring-2 focus:ring-emerald-400/20"
      />

      <label className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-slate-400">
        <MapPin className="h-3.5 w-3.5" /> Target City
      </label>
      <input
        value={city}
        onChange={(e) => setCity(e.target.value)}
        placeholder="Austin, Texas, USA"
        className="mb-4 w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2.5 text-sm placeholder:text-slate-500 focus:border-emerald-400/50 focus:outline-none focus:ring-2 focus:ring-emerald-400/20"
      />

      <label className="mb-5 flex cursor-pointer items-center justify-between rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2.5">
        <div className="flex items-center gap-2 text-xs text-slate-300">
          <Zap className="h-3.5 w-3.5 text-amber-400" />
          <span>Use live OSM data</span>
          <span className="text-slate-500">(slower)</span>
        </div>
        <input
          type="checkbox"
          checked={useOsm}
          onChange={(e) => setUseOsm(e.target.checked)}
          className="h-4 w-4 accent-emerald-400"
        />
      </label>

      {error && (
        <div className="mb-3 rounded-lg border border-red-400/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          {error}
        </div>
      )}

      <button
        onClick={handleSubmit}
        disabled={loading}
        className="group relative w-full overflow-hidden rounded-lg bg-gradient-to-r from-emerald-500 to-teal-500 px-4 py-3 text-sm font-semibold text-slate-950 shadow-lg shadow-emerald-500/20 transition hover:shadow-emerald-500/40 disabled:opacity-60"
      >
        {loading ? (
          <span className="flex items-center justify-center gap-2">
            <Loader2 className="h-4 w-4 animate-spin" /> Analyzing…
          </span>
        ) : (
          "Run Predictive Analysis"
        )}
      </button>

      <p className="mt-3 text-center text-[10px] text-slate-500">
        Try: Austin, New York, London, Mumbai, Bangalore
      </p>
    </motion.aside>
  );
}
