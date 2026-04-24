import { useState } from "react";
import AnalysisPanel from "./components/AnalysisPanel.jsx";
import SiteMap from "./components/SiteMap.jsx";
import ResultsLegend from "./components/ResultsLegend.jsx";

export default function App() {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  return (
    <main className="relative h-screen w-screen overflow-hidden bg-slate-950 text-slate-100">
      <SiteMap result={result} loading={loading} />
      <AnalysisPanel
        onResult={setResult}
        loading={loading}
        setLoading={setLoading}
      />
      {result && <ResultsLegend result={result} />}
      <div className="pointer-events-none absolute bottom-4 right-4 text-xs text-slate-400/70">
        SiteIQ · Predictive Retail Intelligence
      </div>
    </main>
  );
}
