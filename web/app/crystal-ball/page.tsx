import Link from "next/link";

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

async function getSignalHistory() {
  try {
    const res = await fetch(`${API}/api/reflection/history`, { next: { revalidate: 3600 } });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

async function getMisses() {
  try {
    const res = await fetch(`${API}/api/reflection/misses`, { next: { revalidate: 3600 } });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

async function getEvals() {
  try {
    const res = await fetch(`${API}/api/evals`, { next: { revalidate: 3600 } });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export default async function CrystalBall() {
  const [data, signalHistory, misses, evals] = await Promise.all([
    getReflection(),
    getSignalHistory(),
    getMisses(),
    getEvals(),
  ]);

  const sources = signalHistory?.sources || [];
  const bySource = signalHistory?.by_source || {};
  const topSources = sources.slice(0, 4);

  return (
    <div className="max-w-4xl">
      <div className="mb-8 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-zinc-100 mb-1">Crystal Ball</h1>
          <p className="text-sm text-zinc-500">
            Self-reflection: how well is Zeitgeist predicting real opportunities?
            Improves weekly as outcomes are tracked.
          </p>
        </div>
        <Link
          href="/evals"
          className="text-xs text-zinc-500 hover:text-zinc-300 border border-zinc-800 rounded px-3 py-1.5 transition-colors"
        >
          Full Evals →
        </Link>
      </div>

      {/* Eval health snapshot */}
      {evals && (
        <div className="mb-8 bg-zinc-900 border border-zinc-800 rounded-lg p-4">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider">Eval Health</h2>
            <Link href="/evals" className="text-xs text-zinc-600 hover:text-zinc-400">view all</Link>
          </div>
          <div className="flex gap-6">
            <div>
              <div className="text-xs text-zinc-500">Passing</div>
              <div className="text-2xl font-bold font-mono text-emerald-400">{evals.passed}</div>
            </div>
            <div>
              <div className="text-xs text-zinc-500">Failing</div>
              <div className="text-2xl font-bold font-mono text-red-400">{evals.failed}</div>
            </div>
            <div>
              <div className="text-xs text-zinc-500">Total</div>
              <div className="text-2xl font-bold font-mono text-zinc-300">{evals.total}</div>
            </div>
          </div>
        </div>
      )}

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

      {/* Miss rate */}
      {misses && (
        <div className="mb-8">
          <h2 className="text-sm font-semibold text-zinc-400 mb-3 uppercase tracking-wider">Miss Rate</h2>
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
              <div className="text-xs text-zinc-500 mb-1">Explicit Misses</div>
              <div className="text-2xl font-bold font-mono text-red-400">{misses.total_explicit_misses}</div>
              <p className="text-xs text-zinc-600 mt-1">Topics manually tagged as missed</p>
            </div>
            <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
              <div className="text-xs text-zinc-500 mb-1">Underconfident Real Markets</div>
              <div className="text-2xl font-bold font-mono text-amber-400">{misses.total_underconfident}</div>
              <p className="text-xs text-zinc-600 mt-1">Real markets recommended with confidence &lt; 0.4</p>
            </div>
          </div>
          {(misses.total_explicit_misses > 0 || misses.total_underconfident > 0) && (
            <div className="mt-2">
              <Link href="/evals" className="text-xs text-zinc-500 hover:text-zinc-300">
                View miss details in Evals →
              </Link>
            </div>
          )}
        </div>
      )}

      {/* Signal performance with weekly trend */}
      {data?.signal_performance?.length > 0 && (
        <div className="mb-8">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider">Signal Performance</h2>
            {sources.length > 0 && (
              <Link href="/evals" className="text-xs text-zinc-600 hover:text-zinc-400">
                view history →
              </Link>
            )}
          </div>
          <div className="border border-zinc-800 rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-zinc-900 text-zinc-500 text-xs uppercase">
                <tr>
                  <th className="text-left px-4 py-2">Source</th>
                  <th className="text-right px-4 py-2">Precision</th>
                  <th className="text-right px-4 py-2">Recall</th>
                  <th className="text-right px-4 py-2">Lead Time</th>
                  <th className="text-right px-4 py-2">Trend</th>
                </tr>
              </thead>
              <tbody>
                {data.signal_performance.map((sp: any) => {
                  const sourceHistory: any[] = bySource[sp.signal_source] || [];
                  const prevPrecision = sourceHistory.length >= 2 ? sourceHistory[sourceHistory.length - 2]?.precision : null;
                  const delta = prevPrecision !== null && sp.precision !== null ? sp.precision - prevPrecision : null;
                  return (
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
                      <td className="px-4 py-2 text-right text-xs font-mono">
                        {delta !== null ? (
                          <span className={delta >= 0 ? "text-emerald-400" : "text-red-400"}>
                            {delta >= 0 ? "+" : ""}{(delta * 100).toFixed(1)}%
                          </span>
                        ) : (
                          <span className="text-zinc-600">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
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
          <div className="mt-2">
            <Link href="/evals" className="text-xs text-zinc-500 hover:text-zinc-300">
              View all knowledge versions →
            </Link>
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
