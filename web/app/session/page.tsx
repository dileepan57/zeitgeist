"use client";

import { useState, useEffect } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function SessionPage() {
  const [sessionData, setSessionData] = useState<any>(null);
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedAppId, setSelectedAppId] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API}/api/session/today`)
      .then((r) => r.json())
      .then(setSessionData)
      .catch(console.error);
  }, []);

  const sendMessage = async () => {
    if (!message.trim() || loading) return;
    const userMsg = message;
    setMessage("");
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setLoading(true);

    try {
      const res = await fetch(`${API}/api/session/message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userMsg, app_id: selectedAppId }),
      });
      const data = await res.json();
      setMessages((prev) => [...prev, { role: "assistant", content: data.reply }]);
    } catch {
      setMessages((prev) => [...prev, { role: "assistant", content: "Error — API may be offline." }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-4xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-zinc-100 mb-1">Daily Session</h1>
        <p className="text-sm text-zinc-500">Your collaborative build agent. Ask it to scaffold code, design an app, write store copy, or plan your day.</p>
      </div>

      {/* Today's brief */}
      {sessionData && (
        <div className="mb-6 grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Top opportunities */}
          {sessionData.top_app_opportunities?.length > 0 && (
            <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 md:col-span-2">
              <div className="text-xs text-zinc-500 uppercase tracking-wider mb-3">Top App Opportunities Today</div>
              {sessionData.top_app_opportunities.map((opp: any, i: number) => (
                <div key={i} className="mb-3 last:mb-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-semibold text-zinc-200 capitalize">{opp.topic}</span>
                    <span className="text-xs bg-violet-900/40 text-violet-300 border border-violet-700 px-1.5 py-0.5 rounded">
                      App Fit {(opp.app_fit_score * 100).toFixed(0)}%
                    </span>
                  </div>
                  {opp.app_concept && (
                    <p className="text-xs text-zinc-500">{opp.app_concept}</p>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Active builds */}
          {sessionData.active_builds?.length > 0 && (
            <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
              <div className="text-xs text-zinc-500 uppercase tracking-wider mb-3">Active Builds</div>
              {sessionData.active_builds.map((app: any) => (
                <button
                  key={app.id}
                  onClick={() => setSelectedAppId(selectedAppId === app.id ? null : app.id)}
                  className={`w-full text-left mb-2 last:mb-0 text-sm rounded px-2 py-1 ${
                    selectedAppId === app.id ? "bg-zinc-700 text-zinc-100" : "text-zinc-300 hover:bg-zinc-800"
                  }`}
                >
                  {app.name}
                  <span className="text-xs text-zinc-500 ml-2">{app.status}</span>
                </button>
              ))}
              {selectedAppId && (
                <p className="text-xs text-violet-400 mt-2">Context: {sessionData.active_builds.find((a: any) => a.id === selectedAppId)?.name}</p>
              )}
            </div>
          )}
        </div>
      )}

      {/* Chat */}
      <div className="border border-zinc-800 rounded-lg overflow-hidden">
        <div className="h-96 overflow-y-auto p-4 space-y-4 bg-zinc-950">
          {messages.length === 0 && (
            <p className="text-zinc-600 text-sm text-center mt-16">
              Start by asking: "What should I build today?" or "Scaffold a React Native app for [opportunity]"
            </p>
          )}
          {messages.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[85%] rounded-lg px-4 py-2.5 text-sm whitespace-pre-wrap ${
                msg.role === "user"
                  ? "bg-zinc-700 text-zinc-100"
                  : "bg-zinc-900 border border-zinc-800 text-zinc-300"
              }`}>
                {msg.content}
              </div>
            </div>
          ))}
          {loading && (
            <div className="flex justify-start">
              <div className="bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-2.5 text-sm text-zinc-500">
                Thinking...
              </div>
            </div>
          )}
        </div>
        <div className="border-t border-zinc-800 p-3 flex gap-2">
          <input
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && sendMessage()}
            placeholder="Ask the build agent..."
            className="flex-1 bg-zinc-900 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-zinc-500"
          />
          <button
            onClick={sendMessage}
            disabled={loading || !message.trim()}
            className="px-4 py-2 bg-zinc-700 hover:bg-zinc-600 disabled:opacity-40 text-zinc-100 text-sm rounded transition-colors"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
