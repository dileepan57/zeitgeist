const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function getEvals() {
  try {
    const res = await fetch(`${API}/api/evals`, { next: { revalidate: 3600 } });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

async function getEvalHistory() {
  try {
    const res = await fetch(`${API}/api/evals/history`, { next: { revalidate: 3600 } });
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

async function getKnowledgeHistory() {
  try {
    const res = await fetch(`${API}/api/reflection/knowledge/history`, { next: { revalidate: 3600 } });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

function PassBadge({ passed }: { passed: boolean | null }) {
  if (passed === null || passed === undefined) {
    return <span className="px-2 py-0.5 rounded text-xs bg-zinc-800 text-zinc-500">NO DATA</span>;
  }
  return passed ? (
    <span className="px-2 py-0.5 rounded text-xs bg-emerald-950 text-emerald-400 border border-emerald-900">PASS</span>
  ) : (
    <span className="px-2 py-0.5 rounded text-xs bg-red-950 text-red-400 border border-red-900">FAIL</span>
  );
}

function MetricBar({ value, threshold, max = 1 }: { value: number | null; threshold: number | null; max?: number }) {
  if (value === null || value === undefined) return <div className="h-2 bg-zinc-800 rounded" />;
  const pct = Math.min((value / max) * 100, 100);
  const thresholdPct = threshold !== null ? Math.min((threshold / max) * 100, 100) : null;
  const isGood = threshold !== null ? value >= threshold : true;
  return (
    <div className="relative h-2 bg-zinc-800 rounded overflow-hidden">
      <div
        className={`h-full rounded transition-all ${isGood ? "bg-emerald-500" : "bg-red-500"}`}
        style={{ width: `${pct}%` }}
      />
      {thresholdPct !== null && (
        <div
          className="absolute top-0 h-full w-px bg-zinc-500"
          style={{ left: `${thresholdPct}%` }}
          title={`Threshold: ${threshold}`}
        />
      )}
    </div>
  );
}

export default async function EvalsPage() {
  const [evals, evalHistory, signalHistory, misses, knowledgeHistory] = await Promise.all([
    getEvals(),
    getEvalHistory(),
    getSignalHistory(),
    getMisses(),
    getKnowledgeHistory(),
  ]);

  const evalRows = evals?.evals || [];
  const totalPassed = evals?.passed || 0;
  const totalFailed = evals?.failed || 0;
  const historyRows = evalHistory?.results || [];
  const sources = signalHistory?.sources || [];
  const bySource = signalHistory?.by_source || {};

  return (
    <div className="max-w-5xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-zinc-100 mb-1">Evals</h1>
        <p className="text-sm text-zinc-500">
          System quality metrics: scoring consistency, calibration, signal performance trends, misses, and LLM output quality.
        </p>
      </div>

      {/* Eval summary strip */}
      <div className="grid grid-cols-3 gap-3 mb-8">
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
          <div className="text-xs text-zinc-500 mb-1">Evals Passing</div>
          <div className="text-3xl font-bold font-mono text-emerald-400">{totalPassed}</div>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
          <div className="text-xs text-zinc-500 mb-1">Evals Failing</div>
          <div className="text-3xl font-bold font-mono text-red-400">{totalFailed}</div>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
          <div className="text-xs text-zinc-500 mb-1">Total Misses Tracked</div>
          <div className="text-3xl font-bold font-mono text-zinc-100">
            {misses?.total_explicit_misses ?? "—"}
          </div>
        </div>
      </div>

      {/* Current eval results */}
      <div className="mb-8">
        <h2 className="text-sm font-semibold text-zinc-400 mb-3 uppercase tracking-wider">Current Eval Results</h2>
        {evalRows.length === 0 ? (
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 text-center text-zinc-600 text-sm">
            No eval results yet. Trigger a run via <code className="text-zinc-500">POST /api/evals/run</code> or wait for the weekly Sunday job.
          </div>
        ) : (
          <div className="border border-zinc-800 rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-zinc-900 text-zinc-500 text-xs uppercase">
                <tr>
                  <th className="text-left px-4 py-2">Eval</th>
                  <th className="text-left px-4 py-2">Metric</th>
                  <th className="text-right px-4 py-2">Value</th>
                  <th className="text-right px-4 py-2">Threshold</th>
                  <th className="px-4 py-2 text-center">Status</th>
                  <th className="text-right px-4 py-2">Date</th>
                </tr>
              </thead>
              <tbody>
                {evalRows.map((row: any, i: number) => (
                  <tr key={i} className="border-t border-zinc-800 hover:bg-zinc-900/50">
                    <td className="px-4 py-3 font-mono text-zinc-200">{row.eval_name}</td>
                    <td className="px-4 py-3 text-zinc-500">{row.metric_name}</td>
                    <td className="px-4 py-3 text-right">
                      <div className="font-mono text-zinc-300 mb-1">
                        {row.metric_value !== null ? Number(row.metric_value).toFixed(4) : "—"}
                      </div>
                      <MetricBar value={row.metric_value} threshold={row.threshold} />
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-zinc-500">
                      {row.threshold ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <PassBadge passed={row.passed} />
                    </td>
                    <td className="px-4 py-3 text-right text-zinc-600 text-xs">{row.run_date}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Signal precision/recall trends */}
      {sources.length > 0 && (
        <div className="mb-8">
          <h2 className="text-sm font-semibold text-zinc-400 mb-3 uppercase tracking-wider">
            Signal Performance Trends (Weekly Snapshots)
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {sources.slice(0, 8).map((source: string) => {
              const history: any[] = bySource[source] || [];
              const latest = history[history.length - 1];
              const earliest = history[0];
              const precisionDelta =
                latest && earliest && latest.precision !== null && earliest.precision !== null
                  ? latest.precision - earliest.precision
                  : null;
              return (
                <div key={source} className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
                  <div className="flex items-center justify-between mb-3">
                    <span className="font-mono text-sm text-zinc-200">{source}</span>
                    {precisionDelta !== null && (
                      <span className={`text-xs font-mono ${precisionDelta >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                        {precisionDelta >= 0 ? "+" : ""}{(precisionDelta * 100).toFixed(1)}% precision
                      </span>
                    )}
                  </div>
                  <div className="flex gap-4 text-xs text-zinc-500">
                    <div>
                      <span className="text-zinc-600">Precision: </span>
                      <span className="font-mono text-zinc-300">
                        {latest?.precision !== null ? `${(latest.precision * 100).toFixed(0)}%` : "—"}
                      </span>
                    </div>
                    <div>
                      <span className="text-zinc-600">Recall: </span>
                      <span className="font-mono text-zinc-300">
                        {latest?.recall !== null ? `${(latest.recall * 100).toFixed(0)}%` : "—"}
                      </span>
                    </div>
                    <div>
                      <span className="text-zinc-600">Snapshots: </span>
                      <span className="font-mono text-zinc-300">{history.length}</span>
                    </div>
                  </div>
                  {/* Mini sparkline: precision over time */}
                  {history.length > 1 && (
                    <div className="mt-3 flex items-end gap-0.5 h-8">
                      {history.map((h: any, idx: number) => {
                        const pct = h.precision !== null ? Math.round(h.precision * 100) : 0;
                        return (
                          <div
                            key={idx}
                            className="flex-1 bg-blue-600 rounded-sm opacity-80"
                            style={{ height: `${Math.max(pct, 4)}%` }}
                            title={`${h.date}: ${pct}%`}
                          />
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Miss analysis */}
      <div className="mb-8">
        <h2 className="text-sm font-semibold text-zinc-400 mb-3 uppercase tracking-wider">Miss Analysis</h2>
        {(misses?.total_explicit_misses || 0) === 0 && (misses?.total_underconfident || 0) === 0 ? (
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 text-sm text-zinc-600 text-center">
            No misses tracked yet. Tag outcomes on topic pages to surface misses.
          </div>
        ) : (
          <div className="space-y-3">
            {misses?.explicit_misses?.slice(0, 5).map((m: any, i: number) => (
              <div key={i} className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="font-mono text-sm text-zinc-200 mb-1">
                      {m.recommendations?.topics?.name || "Unknown topic"}
                    </div>
                    {m.user_note && <p className="text-xs text-zinc-500">{m.user_note}</p>}
                  </div>
                  <span className="text-xs text-zinc-600 whitespace-nowrap">{m.outcome_date}</span>
                </div>
              </div>
            ))}
            {(misses?.total_underconfident || 0) > 0 && (
              <div className="bg-zinc-900 border border-amber-900/30 rounded-lg p-4">
                <div className="text-xs text-amber-500 mb-1">Underconfident Real Markets</div>
                <p className="text-sm text-zinc-400">
                  {misses.total_underconfident} topics became confirmed real markets but were recommended with confidence &lt; 0.4.
                  Consider recalibrating the scoring weights.
                </p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Eval history (last 10 runs per eval) */}
      {historyRows.length > 0 && (
        <div className="mb-8">
          <h2 className="text-sm font-semibold text-zinc-400 mb-3 uppercase tracking-wider">Eval History</h2>
          <div className="border border-zinc-800 rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-zinc-900 text-zinc-500 text-xs uppercase">
                <tr>
                  <th className="text-left px-4 py-2">Date</th>
                  <th className="text-left px-4 py-2">Eval</th>
                  <th className="text-left px-4 py-2">Metric</th>
                  <th className="text-right px-4 py-2">Value</th>
                  <th className="text-center px-4 py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {historyRows.slice(0, 20).map((row: any, i: number) => (
                  <tr key={i} className="border-t border-zinc-800 hover:bg-zinc-900/50">
                    <td className="px-4 py-2 text-zinc-600 text-xs">{row.run_date}</td>
                    <td className="px-4 py-2 font-mono text-zinc-300">{row.eval_name}</td>
                    <td className="px-4 py-2 text-zinc-500">{row.metric_name}</td>
                    <td className="px-4 py-2 text-right font-mono text-zinc-400">
                      {row.metric_value !== null ? Number(row.metric_value).toFixed(4) : "—"}
                    </td>
                    <td className="px-4 py-2 text-center">
                      <PassBadge passed={row.passed} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Knowledge version history */}
      {(knowledgeHistory?.versions || []).length > 0 && (
        <div className="mb-8">
          <h2 className="text-sm font-semibold text-zinc-400 mb-3 uppercase tracking-wider">
            Institutional Knowledge History ({knowledgeHistory.total} versions)
          </h2>
          <div className="space-y-3">
            {knowledgeHistory.versions.slice(0, 3).map((v: any) => (
              <div key={v.id} className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-mono text-zinc-200">Version {v.version}</span>
                  <span className="text-xs text-zinc-600">{v.created_at?.slice(0, 10)}</span>
                </div>
                {v.performance_summary && (
                  <p className="text-xs text-zinc-500 mb-2">{v.performance_summary}</p>
                )}
                {v.knowledge_brief && (
                  <p className="text-xs text-zinc-400 line-clamp-3">{v.knowledge_brief}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
