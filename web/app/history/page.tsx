const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function getRuns() {
  try {
    const res = await fetch(`${API}/api/runs?limit=30`, { next: { revalidate: 300 } });
    if (!res.ok) return [];
    const data = await res.json();
    return data.runs || [];
  } catch {
    return [];
  }
}

export default async function History() {
  const runs = await getRuns();

  return (
    <div className="max-w-2xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-zinc-100 mb-1">History</h1>
        <p className="text-sm text-zinc-500">All pipeline runs. Click a date to see that day's opportunities.</p>
      </div>

      {runs.length === 0 ? (
        <div className="text-center py-24 text-zinc-600">No runs yet.</div>
      ) : (
        <div className="space-y-2">
          {runs.map((run: any) => (
            <a key={run.id} href={`/?date=${run.run_date}`} className="flex items-center justify-between border border-zinc-800 rounded-lg px-4 py-3 hover:border-zinc-600 transition-colors bg-zinc-900/50">
              <div>
                <span className="text-zinc-200 font-mono">{run.run_date}</span>
                {run.topics_scored > 0 && (
                  <span className="text-zinc-500 text-sm ml-3">{run.topics_scored} topics scored</span>
                )}
              </div>
              <span className={`text-xs px-2 py-0.5 rounded ${
                run.status === "complete" ? "text-emerald-400 bg-emerald-950/50 border border-emerald-800" :
                run.status === "running" ? "text-yellow-400 bg-yellow-950/50 border border-yellow-800" :
                "text-red-400 bg-red-950/50 border border-red-800"
              }`}>
                {run.status}
              </span>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
