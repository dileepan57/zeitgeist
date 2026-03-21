import Link from "next/link";

const SOURCE_CONFIG: Record<string, { label: string; unit: string }> = {
  wikipedia:       { label: "Wikipedia",    unit: "views"     },
  youtube:         { label: "YouTube",      unit: "videos"    },
  github_trending: { label: "GitHub",       unit: "repos"     },
  stackoverflow:   { label: "Stack Overflow", unit: "questions" },
  gdelt:           { label: "News",         unit: "articles"  },
  reddit:          { label: "Reddit",       unit: "posts"     },
  google_trends:   { label: "Google",       unit: ""          },
  itunes:          { label: "Podcasts",     unit: "eps"       },
  producthunt:     { label: "Product Hunt", unit: "launches"  },
  arxiv:           { label: "ArXiv",        unit: "papers"    },
  job_postings:    { label: "Jobs",         unit: "postings"  },
  markets:         { label: "Markets",      unit: ""          },
  app_store:       { label: "App Store",    unit: "apps"      },
  kickstarter:     { label: "Kickstarter",  unit: ""          },
  discord:         { label: "Discord",      unit: ""          },
};

// Preferred display order for source columns
const SOURCE_ORDER = [
  "wikipedia", "youtube", "github_trending", "stackoverflow",
  "gdelt", "reddit", "google_trends", "itunes", "producthunt",
  "arxiv", "job_postings", "markets", "app_store", "kickstarter", "discord",
];

function formatValue(value: number, source: string): string {
  if (source === "wikipedia") {
    if (value >= 1_000_000) return (value / 1_000_000).toFixed(1) + "M";
    if (value >= 1_000)     return Math.round(value / 1_000) + "K";
  }
  return value?.toLocaleString() ?? "—";
}

interface Topic {
  id: string;
  topic_id: string;
  topics: { name: string } | { name: string }[];
  description: string;
  signals_by_source: Record<string, number>;
}

interface AttentionTableProps {
  topics: Topic[];
}

export function AttentionTable({ topics }: AttentionTableProps) {
  // Determine which source columns to show (only those present in the data)
  const activeSources = SOURCE_ORDER.filter((s) =>
    topics.some((t) => s in (t.signals_by_source || {}))
  );

  function topicName(t: Topic): string {
    if (!t.topics) return "Unknown";
    if (Array.isArray(t.topics)) return t.topics[0]?.name ?? "Unknown";
    return (t.topics as { name: string }).name ?? "Unknown";
  }

  function deriveDescription(t: Topic): string {
    const sources = Object.keys(t.signals_by_source || {});
    if (!sources.length) return "";
    const labels = sources
      .filter((s) => SOURCE_CONFIG[s])
      .map((s) => SOURCE_CONFIG[s].label);
    return labels.length ? `Trending on ${labels.join(", ")}` : "";
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b border-zinc-800">
            <th className="text-left pb-3 pr-3 text-zinc-600 font-normal text-xs w-6">#</th>
            <th className="text-left pb-3 pr-6 text-zinc-500 font-medium text-xs">Topic</th>
            <th className="text-left pb-3 pr-6 text-zinc-500 font-medium text-xs min-w-[280px]">
              What's happening
            </th>
            {activeSources.map((source) => (
              <th
                key={source}
                className="text-right pb-3 px-3 text-zinc-500 font-medium text-xs whitespace-nowrap"
              >
                {SOURCE_CONFIG[source]?.label || source}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {topics.map((topic, i) => {
            const name = topicName(topic);
            const desc = topic.description || deriveDescription(topic);
            return (
              <tr
                key={topic.id}
                className="border-b border-zinc-900 hover:bg-zinc-900/40 transition-colors"
              >
                <td className="py-3 pr-3 text-zinc-700 font-mono text-xs align-top">
                  {i + 1}
                </td>
                <td className="py-3 pr-6 align-top">
                  <Link
                    href={`/topic/${topic.topic_id}`}
                    className="text-zinc-100 font-medium hover:text-white leading-snug"
                  >
                    {name}
                  </Link>
                </td>
                <td className="py-3 pr-6 text-zinc-500 text-xs align-top leading-relaxed">
                  {desc || "—"}
                </td>
                {activeSources.map((source) => {
                  const val = topic.signals_by_source?.[source];
                  return (
                    <td
                      key={source}
                      className="py-3 px-3 text-right font-mono text-xs text-zinc-400 align-top whitespace-nowrap"
                    >
                      {val != null ? (
                        <>
                          <span className="text-zinc-300">{formatValue(val, source)}</span>
                          {SOURCE_CONFIG[source]?.unit && (
                            <span className="text-zinc-600 ml-1">
                              {SOURCE_CONFIG[source].unit}
                            </span>
                          )}
                        </>
                      ) : (
                        <span className="text-zinc-800">—</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
