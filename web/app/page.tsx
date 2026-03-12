import { OpportunityCard } from "@/components/OpportunityCard";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function getOpportunities() {
  try {
    const res = await fetch(`${API}/api/opportunities?limit=20`, {
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
          <h1 className="text-2xl font-bold text-zinc-100">Today's Opportunities</h1>
          {runDate && (
            <span className="text-xs text-zinc-500 font-mono">{runDate}</span>
          )}
        </div>
        <p className="text-sm text-zinc-500">
          Topics scoring highest on demand × frustration × supply gap across all signals.
        </p>
      </div>

      {/* Timeline filter pills */}
      <div className="flex gap-2 mb-6 flex-wrap">
        {["All", "CRYSTALLIZING", "EMERGING", "MAINSTREAM", "DECLINING"].map((t) => (
          <span key={t} className={`text-xs px-3 py-1 rounded-full border cursor-pointer ${
            t === "All"
              ? "border-zinc-600 text-zinc-300 bg-zinc-800"
              : `timeline-${t}`
          }`}>
            {t === "All" ? "All" : t.charAt(0) + t.slice(1).toLowerCase()}
          </span>
        ))}
      </div>

      {/* Grid */}
      {opportunities.length === 0 ? (
        <div className="text-center py-24 text-zinc-600">
          <p className="text-lg mb-2">No data yet.</p>
          <p className="text-sm">Run the pipeline or wait for the daily job at 6 AM UTC.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {opportunities.map((opp: any) => {
            const topic = opp.topics?.[0] || opp.topics || {};
            const synthesis = opp.topic_syntheses?.[0] || opp.topic_syntheses || {};
            return (
              <OpportunityCard
                key={opp.id}
                topic={{ id: opp.topic_id, name: topic.name || "Unknown" }}
                score={opp.opportunity_score || 0}
                timelinePosition={opp.timeline_position || "NONE"}
                categories={opp.categories_fired || []}
                frustrationScore={opp.frustration_score || 0}
                supplyGapScore={opp.supply_gap_score || 0}
                appFitScore={synthesis.app_fit_score}
                appConcept={synthesis.app_concept}
                opportunityBrief={synthesis.opportunity_brief}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}
