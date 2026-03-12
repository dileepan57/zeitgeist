const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function getApps() {
  try {
    const res = await fetch(`${API}/api/apps`, { next: { revalidate: 60 } });
    if (!res.ok) return [];
    const data = await res.json();
    return data.apps || [];
  } catch {
    return [];
  }
}

const STATUS_STYLES: Record<string, string> = {
  IDEATING: "text-zinc-400 bg-zinc-900 border-zinc-700",
  BUILDING: "text-yellow-400 bg-yellow-950/30 border-yellow-800",
  SUBMITTED: "text-blue-400 bg-blue-950/30 border-blue-800",
  LIVE: "text-emerald-400 bg-emerald-950/30 border-emerald-800",
  PAUSED: "text-zinc-500 bg-zinc-900 border-zinc-700",
};

export default async function Builds() {
  const apps = await getApps();

  return (
    <div className="max-w-4xl">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-zinc-100 mb-1">App Builds</h1>
          <p className="text-sm text-zinc-500">All active and past app projects. Start new ones from the Daily Session.</p>
        </div>
      </div>

      {apps.length === 0 ? (
        <div className="text-center py-24 text-zinc-600">
          <p className="text-lg mb-2">No apps yet.</p>
          <p className="text-sm">Go to Daily Session and ask the agent to start a new app based on today's top opportunity.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {apps.map((app: any) => {
            const latestRevenue = app.app_revenue?.[0];
            const pendingTasks = (app.app_tasks || []).filter((t: any) => t.status === "PENDING").length;

            return (
              <div key={app.id} className="border border-zinc-800 rounded-lg p-5 bg-zinc-900/50">
                <div className="flex items-start justify-between mb-3">
                  <h3 className="text-zinc-100 font-semibold">{app.name}</h3>
                  <span className={`text-xs px-2 py-0.5 rounded border ${STATUS_STYLES[app.status] || STATUS_STYLES.IDEATING}`}>
                    {app.status}
                  </span>
                </div>

                {latestRevenue && (
                  <div className="flex gap-4 text-sm mb-3">
                    <div>
                      <span className="text-zinc-500 text-xs">Free users</span>
                      <div className="text-zinc-200 font-mono font-bold">{latestRevenue.free_users || 0}</div>
                    </div>
                    <div>
                      <span className="text-zinc-500 text-xs">Paid users</span>
                      <div className="text-zinc-200 font-mono font-bold">{latestRevenue.paid_users || 0}</div>
                    </div>
                    <div>
                      <span className="text-zinc-500 text-xs">MRR</span>
                      <div className="text-emerald-400 font-mono font-bold">${latestRevenue.mrr || 0}</div>
                    </div>
                  </div>
                )}

                <div className="flex gap-2 mt-3">
                  {pendingTasks > 0 && (
                    <span className="text-xs bg-yellow-950/40 text-yellow-400 border border-yellow-800 px-2 py-0.5 rounded">
                      {pendingTasks} task{pendingTasks > 1 ? "s" : ""} to review
                    </span>
                  )}
                  {app.status === "LIVE" && !latestRevenue?.paid_users && (
                    <span className="text-xs bg-emerald-950/40 text-emerald-400 border border-emerald-800 px-2 py-0.5 rounded">
                      Consider going paid
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
