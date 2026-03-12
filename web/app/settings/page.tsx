"use client";

import { useState, useEffect } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Settings() {
  const [thesis, setThesis] = useState({
    build_profile: "",
    domains: [] as string[],
    skills: [] as string[],
    past_projects: "",
    avoid_domains: [] as string[],
  });
  const [saved, setSaved] = useState(false);
  const [domainInput, setDomainInput] = useState("");
  const [skillInput, setSkillInput] = useState("");

  useEffect(() => {
    fetch(`${API}/api/thesis`)
      .then((r) => r.json())
      .then((data) => {
        if (data && Object.keys(data).length > 0) {
          setThesis({
            build_profile: data.build_profile || "",
            domains: data.domains || [],
            skills: data.skills || [],
            past_projects: data.past_projects || "",
            avoid_domains: data.avoid_domains || [],
          });
        }
      })
      .catch(console.error);
  }, []);

  const save = async () => {
    await fetch(`${API}/api/thesis`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(thesis),
    });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const addTag = (field: "domains" | "skills" | "avoid_domains", value: string) => {
    if (!value.trim()) return;
    setThesis((prev) => ({ ...prev, [field]: [...prev[field], value.trim()] }));
    if (field === "domains") setDomainInput("");
    if (field === "skills") setSkillInput("");
  };

  const removeTag = (field: "domains" | "skills" | "avoid_domains", idx: number) => {
    setThesis((prev) => ({ ...prev, [field]: prev[field].filter((_, i) => i !== idx) }));
  };

  const TagInput = ({ label, field, value, setValue }: any) => (
    <div className="mb-6">
      <label className="block text-xs text-zinc-400 uppercase tracking-wider mb-2">{label}</label>
      <div className="flex gap-2 mb-2 flex-wrap">
        {thesis[field as "domains" | "skills" | "avoid_domains"].map((tag: string, i: number) => (
          <span key={i} className="flex items-center gap-1 bg-zinc-800 border border-zinc-700 text-zinc-300 text-xs px-2 py-1 rounded">
            {tag}
            <button onClick={() => removeTag(field, i)} className="text-zinc-500 hover:text-zinc-200 ml-1">×</button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && addTag(field, value)}
          placeholder={`Add ${label.toLowerCase()} and press Enter`}
          className="flex-1 bg-zinc-900 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-zinc-500"
        />
      </div>
    </div>
  );

  return (
    <div className="max-w-2xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-zinc-100 mb-1">Your Build Thesis</h1>
        <p className="text-sm text-zinc-500">
          This context is injected into every opportunity analysis and build agent session.
          The more specific, the better the signal-to-noise ratio for you personally.
        </p>
      </div>

      <div className="mb-6">
        <label className="block text-xs text-zinc-400 uppercase tracking-wider mb-2">Builder Profile</label>
        <textarea
          value={thesis.build_profile}
          onChange={(e) => setThesis((p) => ({ ...p, build_profile: e.target.value }))}
          rows={3}
          placeholder="e.g. Solo developer building consumer mobile apps. 5 years React Native experience. Prefer B2C over B2B."
          className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 resize-none"
        />
      </div>

      <TagInput label="Domains of Interest" field="domains" value={domainInput} setValue={setDomainInput} />
      <TagInput label="Skills" field="skills" value={skillInput} setValue={setSkillInput} />

      <div className="mb-6">
        <label className="block text-xs text-zinc-400 uppercase tracking-wider mb-2">Past Projects</label>
        <textarea
          value={thesis.past_projects}
          onChange={(e) => setThesis((p) => ({ ...p, past_projects: e.target.value }))}
          rows={3}
          placeholder="e.g. Built a Pomodoro app (2K downloads), a journaling app (abandoned), a recipe finder..."
          className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 resize-none"
        />
      </div>

      <button
        onClick={save}
        className="px-5 py-2.5 bg-zinc-100 text-zinc-900 font-semibold text-sm rounded hover:bg-zinc-200 transition-colors"
      >
        {saved ? "Saved!" : "Save Thesis"}
      </button>
    </div>
  );
}
