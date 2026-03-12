import Link from "next/link";

const links = [
  { href: "/", label: "Opportunities" },
  { href: "/history", label: "History" },
  { href: "/builds", label: "Builds" },
  { href: "/session", label: "Daily Session" },
  { href: "/crystal-ball", label: "Crystal Ball" },
  { href: "/settings", label: "Settings" },
];

export function Nav() {
  return (
    <nav className="border-b border-zinc-800 px-4 py-3">
      <div className="max-w-6xl mx-auto flex items-center gap-8">
        <span className="text-zinc-100 font-bold tracking-tight text-lg">
          ZEITGEIST
        </span>
        <div className="flex gap-6 text-sm text-zinc-400">
          {links.map((l) => (
            <Link key={l.href} href={l.href} className="hover:text-zinc-100 transition-colors">
              {l.label}
            </Link>
          ))}
        </div>
      </div>
    </nav>
  );
}
