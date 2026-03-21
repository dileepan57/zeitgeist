import { OpportunityCard } from "@/components/OpportunityCard";

export const dynamic = "force-dynamic";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function getOpportunities() {
  try {
    const res = await fetch(`${API}/api/opportunities?limit=40`, {
      next: { revalidate: 300 },
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export default async function Dashboard() {
  const data = await getOpportunities();
  const opportunities = data?.opportunities ?? [];
  const runDate = data?.run_date;

  return (
    <div>
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-1">
          <h1 className="text-2xl font-bold text-zinc-100">What the world is watching</h1>
          {runDate && (
            <span className="text-xs text-zinc-500 font-mono">{runDate}</span>
          )}
        </div>
        <p className="text-sm text-zinc-500">
          Topics appearing across the most independent signal sources today.
        </p>
      </div>

      {/* Grid */}
      {opportunities.length === 0 ? (
        <div className="text-center py-24 text-zinc-600">
          <p className="text-lg mb-2">No data yet.</p>
          <p className="text-sm">Run the pipeline or wait for the daily job at 6 AM UTC.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {opportunities.map((opp: any) => {
            const topic = opp.topics?.[0] || opp.topics || {};
            return (
              <OpportunityCard
                key={opp.id}
                topic={{ id: opp.topic_id, name: topic.name || "Unknown" }}
                sources={opp.sources_fired || []}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}
