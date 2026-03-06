"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { fetchJson } from "../lib/api";
import type { PublicAgentRecord } from "../lib/types";

interface AgentDetailClientProps {
  agentId: string;
}

export function AgentDetailClient({ agentId }: AgentDetailClientProps) {
  const [agent, setAgent] = useState<PublicAgentRecord | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const data = await fetchJson<PublicAgentRecord>(`/agents/${agentId}`);
        setAgent(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load agent");
      }
    }
    load();
  }, [agentId]);

  return (
    <main className="page-shell">
      <section className="card">
        <p className="muted">
          <Link href="/agents">← Back to agents</Link>
        </p>
        <h1>{agentId}</h1>
        {error ? <p className="error-text">{error}</p> : null}
        {!agent && !error ? <p className="muted">Loading agent details...</p> : null}

        {agent ? (
          <div className="summary-block">
            <p>
              <strong>Name:</strong> {agent.name}
            </p>
            <p>
              <strong>Version:</strong> {agent.version}
            </p>
            <p>
              <strong>Runtime:</strong> {agent.runtime_type}
            </p>
            <h3>HowlHouse Strategy</h3>
            <pre className="narration-block">{agent.strategy_text ?? ""}</pre>
          </div>
        ) : null}
      </section>
    </main>
  );
}
