const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function getTopic(id: string) {
  try {
    const res = await fetch(`${API}/api/topics/${id}`, { next: { revalidate: 60 } });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

const CATEGORY_COLORS: Record<string, string> = {
  media: "text-blue-400",
  demand: "text-yellow-400",
  behavior: "text-orange-400",
  builder: "text-violet-400",
  community: "text-emerald-400",
  money: "text-green-400",
};

export default async function TopicPage({ params }: { params: { id: string } }) {
  const data = await getTopic(params.id);

  if (!data?.topic) {
    return <div className="text-zinc-500 py-24 text-center">Topic not found.</div>;
  }

  const { topic, scores, signals, syntheses, outcomes } = data;
  const latestScore = scores?.[0];
  const latestSynthesis = syntheses?.[0];

  return (
    <div className="max-w-4xl">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-zinc-100 capitalize mb-1">{topic.name}</h1>
        <div className="flex gap-3 text-sm text-zinc-500">
          <span>First seen: {topic.first_seen}</span>
          {latestScore && (
            <>
              <span>·</span>
              <span className={`timeline-${latestScore.timeline_position} px-2 py-0.5 rounded text-xs`}>
                {latestScore.timeline_position}
              </span>
              <span>·</span>
              <span>Score: <span className="text-zinc-300 font-mono">{(latestScore.opportunity_score * 100).toFixed(1)}</span></span>
            </>
          )}
        </div>
      </div>

      {/* Score breakdown */}
      {latestScore && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
          {[
            { label: "Independence", value: latestScore.independence_score },
            { label: "Demand", value: latestScore.demand_score },
            { label: "Frustration", value: latestScore.frustration_score },
            { label: "Supply Gap", value: latestScore.supply_gap_score },
          ].map(({ label, value }) => (
            <div key={label} className="bg-zinc-900 border border-zinc-800 rounded-lg p-3">
              <div className="text-xs text-zinc-500 mb-1">{label}</div>
              <div className="text-xl font-bold font-mono text-zinc-100">
                {((value || 0) * 100).toFixed(0)}
                <span className="text-sm text-zinc-500">%</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Signals fired */}
      {latestScore?.sources_fired?.length > 0 && (
        <div className="mb-8">
          <h2 className="text-sm font-semibold text-zinc-400 mb-3 uppercase tracking-wider">Signals Fired</h2>
          <div className="flex flex-wrap gap-2">
            {latestScore.sources_fired.map((source: string) => (
              <span key={source} className="text-xs bg-zinc-800 border border-zinc-700 px-2 py-1 rounded font-mono text-zinc-300">
                {source}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Opportunity brief */}
      {latestSynthesis?.opportunity_brief && (
        <div className="mb-8">
          <h2 className="text-sm font-semibold text-zinc-400 mb-3 uppercase tracking-wider">Opportunity Brief</h2>
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 text-sm text-zinc-300 leading-relaxed whitespace-pre-wrap">
            {latestSynthesis.opportunity_brief}
          </div>
        </div>
      )}

      {/* Gap analysis */}
      {latestSynthesis?.gap_analysis && (
        <div className="mb-8">
          <h2 className="text-sm font-semibold text-zinc-400 mb-3 uppercase tracking-wider">Gap Analysis</h2>
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-5 text-sm text-zinc-400 leading-relaxed whitespace-pre-wrap">
            {latestSynthesis.gap_analysis}
          </div>
        </div>
      )}

      {/* App fit */}
      {latestSynthesis?.app_fit_score > 0.4 && (
        <div className="mb-8 border border-violet-800 bg-violet-950/30 rounded-lg p-5">
          <h2 className="text-sm font-semibold text-violet-400 mb-2 uppercase tracking-wider">
            App Opportunity — Fit Score {(latestSynthesis.app_fit_score * 100).toFixed(0)}%
          </h2>
          <p className="text-sm text-violet-200">{latestSynthesis.app_concept}</p>
        </div>
      )}

      {/* Outcome tagging */}
      <div className="mb-8">
        <h2 className="text-sm font-semibold text-zinc-400 mb-3 uppercase tracking-wider">Track Outcome</h2>
        <p className="text-xs text-zinc-600 mb-2">Mark what happened with this opportunity to improve future predictions.</p>
        <div className="flex gap-2 flex-wrap">
          {["REAL_MARKET", "FIZZLED", "EMERGING", "MISSED"].map((type) => (
            <button key={type} className="text-xs px-3 py-1.5 border border-zinc-700 text-zinc-400 rounded hover:border-zinc-500 hover:text-zinc-200 transition-colors">
              {type.replace("_", " ")}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
