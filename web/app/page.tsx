import { AttentionTable } from "@/components/AttentionTable";

export const dynamic = "force-dynamic";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function getOpportunities() {
  try {
    const res = await fetch(`${API}/api/opportunities?limit=40`);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export default async function Dashboard() {
  const data = await getOpportunities();
  const topics = data?.opportunities ?? [];
  const runDate = data?.run_date;

  return (
    <div>
      <div className="mb-8">
        <div className="flex items-center justify-between mb-1">
          <h1 className="text-2xl font-bold text-zinc-100">What the world is watching</h1>
          {runDate && (
            <span className="text-xs text-zinc-500 font-mono">{runDate}</span>
          )}
        </div>
        <p className="text-sm text-zinc-500">
          Topics ranked by how many independent sources are covering them today.
        </p>
      </div>

      {topics.length === 0 ? (
        <div className="text-center py-24 text-zinc-600">
          <p className="text-lg mb-2">No data yet.</p>
          <p className="text-sm">Run the pipeline or wait for the daily job at 6 AM UTC.</p>
        </div>
      ) : (
        <AttentionTable topics={topics} />
      )}
    </div>
  );
}
