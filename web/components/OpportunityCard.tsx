import Link from "next/link";

const SOURCE_LABELS: Record<string, string> = {
  wikipedia: "Wikipedia",
  google_trends: "Google Trends",
  reddit: "Reddit",
  gdelt: "News",
  youtube: "YouTube",
  github_trending: "GitHub",
  arxiv: "ArXiv",
  itunes: "Podcasts",
  producthunt: "Product Hunt",
  markets: "Markets",
  app_store: "App Store",
  amazon_movers: "Amazon",
  job_postings: "Job Postings",
  discord: "Discord",
  stackoverflow: "Stack Overflow",
  substack: "Substack",
  federal_register: "Federal Register",
  uspto: "Patents",
  sbir: "Gov Grants",
  kickstarter: "Kickstarter",
  crunchbase: "Crunchbase",
  xiaohongshu: "Xiaohongshu",
};

interface AttentionCardProps {
  topic: { id: string; name: string };
  sources: string[];
}

export function OpportunityCard({ topic, sources }: AttentionCardProps) {
  return (
    <Link href={`/topic/${topic.id}`}>
      <div className="border border-zinc-800 rounded-lg p-4 hover:border-zinc-600 transition-colors cursor-pointer bg-zinc-900/40">
        <h3 className="text-zinc-100 font-semibold text-base mb-3 leading-snug">
          {topic.name}
        </h3>
        <div className="flex flex-wrap gap-1.5">
          {sources.map((s) => (
            <span
              key={s}
              className="text-xs bg-zinc-800 text-zinc-300 px-2 py-0.5 rounded"
            >
              {SOURCE_LABELS[s] || s}
            </span>
          ))}
        </div>
      </div>
    </Link>
  );
}
