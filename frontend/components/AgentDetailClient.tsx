"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { fetchJson } from "../lib/api";
import { formatDateTime, formatShortId, summarizeText } from "../lib/format";
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
    void load();
  }, [agentId]);

  const strategySummary = useMemo(
    () => summarizeText(agent?.strategy_text, "No strategy summary provided."),
    [agent?.strategy_text]
  );

  return (
    <main className="page-shell page-stack">
      <section className="page-banner">
        <div className="section-heading">
          <p className="breadcrumb">
            <Link href="/agents">Agents</Link>
            <span>/</span>
            <span>{formatShortId(agentId, 10, 8)}</span>
          </p>
          <span className="eyebrow">Profile</span>
          <h1>{agent?.name ?? "Agent profile"}</h1>
          <p className="section-copy">{strategySummary}</p>
        </div>

        {agent ? (
          <div className="metrics-grid metrics-grid-compact">
            <article className="stat-card">
              <span className="stat-label">Version</span>
              <strong className="stat-value">{agent.version}</strong>
              <span className="stat-meta">Published package version</span>
            </article>
            <article className="stat-card">
              <span className="stat-label">Runtime</span>
              <strong className="stat-value">{agent.runtime_type}</strong>
              <span className="stat-meta">Execution sandbox</span>
            </article>
            <article className="stat-card">
              <span className="stat-label">Updated</span>
              <strong className="stat-value">{formatDateTime(agent.updated_at)}</strong>
              <span className="stat-meta">Latest catalog timestamp</span>
            </article>
          </div>
        ) : null}
      </section>

      {error ? (
        <div className="message-banner message-banner-error" role="alert">
          {error}
        </div>
      ) : null}

      {!agent && !error ? (
        <section className="panel skeleton-card">
          <div className="skeleton-line skeleton-line-short" />
          <div className="skeleton-line" />
          <div className="skeleton-line" />
          <div className="skeleton-line skeleton-line-short" />
        </section>
      ) : null}

      {agent ? (
        <section className="split-layout">
          <section className="panel">
            <div className="section-heading">
              <span className="eyebrow">Metadata</span>
              <h2>Registry details</h2>
            </div>
            <dl className="detail-grid">
              <div>
                <dt>Agent ID</dt>
                <dd className="mono-small">{agent.agent_id}</dd>
              </div>
              <div>
                <dt>Created</dt>
                <dd>{formatDateTime(agent.created_at)}</dd>
              </div>
              <div>
                <dt>Updated</dt>
                <dd>{formatDateTime(agent.updated_at)}</dd>
              </div>
              <div>
                <dt>Visibility</dt>
                <dd>{agent.hidden_at ? "Hidden" : "Visible"}</dd>
              </div>
            </dl>
          </section>

          <section className="panel panel-strong">
            <div className="section-heading">
              <span className="eyebrow">Strategy</span>
              <h2>HowlHouse Strategy</h2>
            </div>
            <pre className="narration-block strategy-block">{agent.strategy_text ?? ""}</pre>
          </section>
        </section>
      ) : null}
    </main>
  );
}
