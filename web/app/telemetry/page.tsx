const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function getTelemetry() {
  try {
    const res = await fetch(`${API}/api/telemetry`, { next: { revalidate: 300 } });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

function HealthBadge({ health }: { health: string }) {
  const colors: Record<string, string> = {
    green: "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30",
    yellow: "bg-yellow-500/20 text-yellow-400 border border-yellow-500/30",
    red: "bg-red-500/20 text-red-400 border border-red-500/30",
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded font-mono ${colors[health] || colors.red}`}>
      {health}
    </span>
  );
}

export default async function TelemetryPage() {
  const data = await getTelemetry();

  return (
    <div className="max-w-5xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-zinc-100 mb-1">Telemetry</h1>
        <p className="text-sm text-zinc-500">
          System health, collector performance, Claude API usage, and scoring metrics.
        </p>
      </div>

      {/* Claude Cost Summary */}
      {data?.claude_cost && (
        <div className="mb-8">
          <h2 className="text-sm font-semibold text-zinc-400 mb-3 uppercase tracking-wider">Claude API (Last 30 Days)</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
            <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-3">
              <div className="text-xs text-zinc-500 mb-1">Total Cost</div>
              <div className="text-2xl font-bold font-mono text-zinc-100">
                ${data.claude_cost.total_cost_usd?.toFixed(2) ?? "—"}
              </div>
            </div>
            <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-3">
              <div className="text-xs text-zinc-500 mb-1">API Calls</div>
              <div className="text-2xl font-bold font-mono text-zinc-100">
                {data.claude_cost.total_calls ?? "—"}
              </div>
            </div>
            <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-3">
              <div className="text-xs text-zinc-500 mb-1">Total Tokens</div>
              <div className="text-2xl font-bold font-mono text-zinc-100">
                {data.claude_cost.total_tokens ? `${(data.claude_cost.total_tokens / 1000).toFixed(0)}k` : "—"}
              </div>
            </div>
            <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-3">
              <div className="text-xs text-zinc-500 mb-1">Error Calls</div>
              <div className={`text-2xl font-bold font-mono ${data.claude_cost.error_calls > 0 ? "text-red-400" : "text-zinc-100"}`}>
                {data.claude_cost.error_calls ?? 0}
              </div>
            </div>
          </div>

          {/* By call type */}
          {data.claude_cost.by_call_type && Object.keys(data.claude_cost.by_call_type).length > 0 && (
            <div className="border border-zinc-800 rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-zinc-900 text-zinc-500 text-xs uppercase">
                  <tr>
                    <th className="text-left px-4 py-2">Call Type</th>
                    <th className="text-right px-4 py-2">Calls</th>
                    <th className="text-right px-4 py-2">Tokens</th>
                    <th className="text-right px-4 py-2">Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(data.claude_cost.by_call_type as Record<string, any>).map(([type, stats]) => (
                    <tr key={type} className="border-t border-zinc-800">
                      <td className="px-4 py-2 font-mono text-zinc-300">{type}</td>
                      <td className="px-4 py-2 text-right font-mono text-zinc-400">{stats.calls}</td>
                      <td className="px-4 py-2 text-right font-mono text-zinc-400">{(stats.tokens / 1000).toFixed(1)}k</td>
                      <td className="px-4 py-2 text-right font-mono text-zinc-400">${stats.cost_usd.toFixed(4)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Scoring Metrics */}
      {data?.scoring_metrics && Object.keys(data.scoring_metrics).length > 0 && (
        <div className="mb-8">
          <h2 className="text-sm font-semibold text-zinc-400 mb-3 uppercase tracking-wider">Scoring Distribution</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
            <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-3">
              <div className="text-xs text-zinc-500 mb-1">Avg Opp Score</div>
              <div className="text-xl font-bold font-mono text-zinc-100">
                {data.scoring_metrics.avg_opportunity_score?.toFixed(3) ?? "—"}
              </div>
            </div>
            <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-3">
              <div className="text-xs text-zinc-500 mb-1">Median</div>
              <div className="text-xl font-bold font-mono text-zinc-100">
                {data.scoring_metrics.median_opportunity_score?.toFixed(3) ?? "—"}
              </div>
            </div>
            <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-3">
              <div className="text-xs text-zinc-500 mb-1">P90</div>
              <div className="text-xl font-bold font-mono text-zinc-100">
                {data.scoring_metrics.p90_opportunity_score?.toFixed(3) ?? "—"}
              </div>
            </div>
            <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-3">
              <div className="text-xs text-zinc-500 mb-1">Sample Size</div>
              <div className="text-xl font-bold font-mono text-zinc-100">
                {data.scoring_metrics.sample_size ?? "—"}
              </div>
            </div>
          </div>
          {data.scoring_metrics.timeline_distribution && (
            <div className="flex flex-wrap gap-2">
              {Object.entries(data.scoring_metrics.timeline_distribution as Record<string, number>).map(([pos, count]) => (
                <span key={pos} className="text-xs font-mono bg-zinc-900 border border-zinc-800 rounded px-2 py-1">
                  <span className="text-zinc-500">{pos}</span>
                  <span className="ml-1 text-zinc-300">{count}</span>
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Collector Health Grid */}
      {data?.collector_health?.length > 0 && (
        <div className="mb-8">
          <h2 className="text-sm font-semibold text-zinc-400 mb-3 uppercase tracking-wider">Collector Health (Last 7 Days)</h2>
          <div className="border border-zinc-800 rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-zinc-900 text-zinc-500 text-xs uppercase">
                <tr>
                  <th className="text-left px-4 py-2">Collector</th>
                  <th className="text-right px-4 py-2">Status</th>
                  <th className="text-right px-4 py-2">Success Rate</th>
                  <th className="text-right px-4 py-2">Avg Items</th>
                  <th className="text-right px-4 py-2">Avg Duration</th>
                  <th className="text-right px-4 py-2">Runs</th>
                </tr>
              </thead>
              <tbody>
                {(data.collector_health as any[]).map((c) => (
                  <tr key={c.collector_name} className="border-t border-zinc-800 hover:bg-zinc-900/50">
                    <td className="px-4 py-2 font-mono text-zinc-300">{c.collector_name}</td>
                    <td className="px-4 py-2 text-right">
                      <HealthBadge health={c.health} />
                    </td>
                    <td className="px-4 py-2 text-right font-mono text-zinc-400">
                      {c.success_rate_pct}%
                    </td>
                    <td className="px-4 py-2 text-right font-mono text-zinc-400">
                      {c.avg_items?.toFixed(0) ?? "—"}
                    </td>
                    <td className="px-4 py-2 text-right font-mono text-zinc-400">
                      {c.avg_duration_ms ? `${(c.avg_duration_ms / 1000).toFixed(1)}s` : "—"}
                    </td>
                    <td className="px-4 py-2 text-right font-mono text-zinc-400">
                      {c.total_runs}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Recent Runs */}
      {data?.recent_runs?.length > 0 && (
        <div className="mb-8">
          <h2 className="text-sm font-semibold text-zinc-400 mb-3 uppercase tracking-wider">Recent Pipeline Runs</h2>
          <div className="space-y-2">
            {(data.recent_runs as any[]).map((run) => (
              <div key={run.id} className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-mono text-sm text-zinc-300">{run.run_date}</span>
                  <div className="flex items-center gap-3">
                    <span className={`text-xs font-mono ${run.status === "complete" ? "text-emerald-400" : run.status === "running" ? "text-yellow-400" : "text-red-400"}`}>
                      {run.status}
                    </span>
                    <span className="text-xs text-zinc-500">{run.topics_scored} topics</span>
                    {run.total_duration_ms && (
                      <span className="text-xs text-zinc-500">{(run.total_duration_ms / 1000).toFixed(0)}s total</span>
                    )}
                  </div>
                </div>
                {run.collectors?.length > 0 && (
                  <div className="text-xs text-zinc-600">
                    {run.collector_successes}/{run.total_collectors} collectors succeeded
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {!data && (
        <div className="text-center py-16 text-zinc-600">
          <p className="text-lg mb-2">No telemetry data yet</p>
          <p className="text-sm">Telemetry is collected automatically on each pipeline run.</p>
        </div>
      )}
    </div>
  );
}
