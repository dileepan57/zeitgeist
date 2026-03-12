import Link from "next/link";
import clsx from "clsx";

interface OpportunityCardProps {
  topic: { id: string; name: string };
  score: number;
  timelinePosition: string;
  categories: string[];
  frustrationScore: number;
  supplyGapScore: number;
  appFitScore?: number;
  appConcept?: string;
  opportunityBrief?: string;
}

const TIMELINE_LABELS: Record<string, string> = {
  EMERGING: "Emerging",
  CRYSTALLIZING: "Crystallizing",
  MAINSTREAM: "Mainstream",
  PEAKING: "Peaking",
  DECLINING: "Declining",
};

export function OpportunityCard({
  topic,
  score,
  timelinePosition,
  categories,
  frustrationScore,
  supplyGapScore,
  appFitScore,
  appConcept,
  opportunityBrief,
}: OpportunityCardProps) {
  return (
    <Link href={`/topic/${topic.id}`}>
      <div className="border border-zinc-800 rounded-lg p-5 hover:border-zinc-600 transition-colors cursor-pointer bg-zinc-900/50">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 mb-3">
          <h3 className="text-zinc-100 font-semibold text-base capitalize leading-tight">
            {topic.name}
          </h3>
          <div className="flex items-center gap-2 flex-shrink-0">
            <span className={clsx("text-xs px-2 py-0.5 rounded-full font-medium", `timeline-${timelinePosition}`)}>
              {TIMELINE_LABELS[timelinePosition] || timelinePosition}
            </span>
            <span className="text-zinc-400 text-sm font-mono font-bold">
              {(score * 100).toFixed(0)}
            </span>
          </div>
        </div>

        {/* Signal categories */}
        <div className="flex flex-wrap gap-1.5 mb-3">
          {categories.map((c) => (
            <span key={c} className="text-xs bg-zinc-800 text-zinc-400 px-2 py-0.5 rounded">
              {c}
            </span>
          ))}
        </div>

        {/* Metrics */}
        <div className="flex gap-4 text-xs text-zinc-500 mb-3">
          <span>
            Frustration{" "}
            <span className={clsx("font-mono", frustrationScore > 0.6 ? "text-red-400" : "text-zinc-400")}>
              {(frustrationScore * 100).toFixed(0)}%
            </span>
          </span>
          <span>
            Gap{" "}
            <span className={clsx("font-mono", supplyGapScore > 0.6 ? "text-emerald-400" : "text-zinc-400")}>
              {(supplyGapScore * 100).toFixed(0)}%
            </span>
          </span>
          {appFitScore !== undefined && appFitScore > 0 && (
            <span>
              App Fit{" "}
              <span className={clsx("font-mono", appFitScore > 0.6 ? "text-violet-400" : "text-zinc-400")}>
                {(appFitScore * 100).toFixed(0)}%
              </span>
            </span>
          )}
        </div>

        {/* App concept */}
        {appConcept && (
          <p className="text-xs text-violet-300 mb-2 border-l-2 border-violet-700 pl-2">
            App: {appConcept}
          </p>
        )}

        {/* Brief preview */}
        {opportunityBrief && (
          <p className="text-xs text-zinc-500 line-clamp-2 leading-relaxed">
            {opportunityBrief.replace(/\*\*/g, "").slice(0, 200)}...
          </p>
        )}
      </div>
    </Link>
  );
}
