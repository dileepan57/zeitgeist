const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function getReflection() {
  try {
    const res = await fetch(`${API}/api/reflection`, { next: { revalidate: 3600 } });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export default async function CrystalBall() {
  const data = await getReflection();

  return (
    <div className="max-w-4xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-zinc-100 mb-1">Crystal Ball</h1>
        <p className="text-sm text-zinc-500">
          Self-reflection: how well is Zeitgeist predicting real opportunities?
          Improves weekly as outcomes are tracked.
        </p>
      </div>

      {/* Outcome summary */}
      {data?.outcome_summary && (
        <div className="mb-8">
          <h2 className="text-sm font-semibold text-zinc-400 mb-3 uppercase tracking-wider">Outcome Summary</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {Object.entries(data.outcome_summary).map(([type, count]) => (
              <div key={type} className="bg-zinc-900 border border-zinc-800 rounded-lg p-3">
                <div className="text-xs text-zinc-500 mb-1">{type.replace("_", " ")}</div>
                <div className="text-2xl font-bold font-mono text-zinc-100">{count as number}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Signal performance */}
      {data?.signal_performance?.length > 0 && (
        <div className="mb-8">
          <h2 className="text-sm font-semibold text-zinc-400 mb-3 uppercase tracking-wider">Signal Performance</h2>
          <div className="border border-zinc-800 rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-zinc-900 text-zinc-500 text-xs uppercase">
                <tr>
                  <th className="text-left px-4 py-2">Source</th>
                  <th className="text-right px-4 py-2">Precision</th>
                  <th className="text-right px-4 py-2">Recall</th>
                  <th className="text-right px-4 py-2">Lead Time</th>
                </tr>
              </thead>
              <tbody>
                {data.signal_performance.map((sp: any) => (
                  <tr key={sp.signal_source} className="border-t border-zinc-800 hover:bg-zinc-900/50">
                    <td className="px-4 py-2 font-mono text-zinc-300">{sp.signal_source}</td>
                    <td className="px-4 py-2 text-right font-mono text-zinc-400">
                      {sp.precision !== null ? `${(sp.precision * 100).toFixed(0)}%` : "—"}
                    </td>
                    <td className="px-4 py-2 text-right font-mono text-zinc-400">
                      {sp.recall !== null ? `${(sp.recall * 100).toFixed(0)}%` : "—"}
                    </td>
                    <td className="px-4 py-2 text-right font-mono text-zinc-400">
                      {sp.avg_lead_time_days ? `${sp.avg_lead_time_days}d` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Institutional knowledge */}
      {data?.current_knowledge?.knowledge_brief ? (
        <div className="mb-8">
          <h2 className="text-sm font-semibold text-zinc-400 mb-3 uppercase tracking-wider">
            Institutional Knowledge v{data.current_knowledge.version}
          </h2>
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 text-sm text-zinc-300 leading-relaxed whitespace-pre-wrap">
            {data.current_knowledge.knowledge_brief}
          </div>
        </div>
      ) : (
        <div className="text-center py-16 text-zinc-600">
          <p className="text-lg mb-2">Building knowledge base...</p>
          <p className="text-sm">Tag outcomes on topic pages to start calibrating the system.</p>
        </div>
      )}
    </div>
  );
}
