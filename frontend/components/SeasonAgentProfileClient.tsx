"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { fetchJson } from "../lib/api";
import { formatShortId } from "../lib/format";
import type { AgentSeasonProfile } from "../lib/types";

interface SeasonAgentProfileClientProps {
  seasonId: string;
  agentId: string;
}

export function SeasonAgentProfileClient({ seasonId, agentId }: SeasonAgentProfileClientProps) {
  const [profile, setProfile] = useState<AgentSeasonProfile | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const data = await fetchJson<AgentSeasonProfile>(`/seasons/${seasonId}/agents/${agentId}`);
        setProfile(data);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load agent profile");
      }
    }

    void load();
  }, [agentId, seasonId]);

  return (
    <main className="page-shell page-stack">
      <section className="page-banner detail-banner">
        <div className="section-heading">
          <p className="breadcrumb">
            <Link href={`/league/seasons/${seasonId}`}>Season</Link>
            <span>/</span>
            <span>{profile?.name ?? formatShortId(agentId, 10, 8)}</span>
          </p>
          <span className="eyebrow">Season agent profile</span>
          <h1>{profile?.name ?? "Agent profile"}</h1>
          <p className="section-copy">
            Review how this agent performed within the selected season and jump back into the underlying match replays.
          </p>
        </div>

        {profile ? (
          <div className="feature-strip">
            <span className="meta-pill">{profile.version}</span>
            <span className="meta-pill meta-pill-accent">{profile.rating.toFixed(2)} rating</span>
            <span className="meta-pill">
              {profile.wins}W / {profile.losses}L
            </span>
          </div>
        ) : null}

        {profile ? (
          <div className="metrics-grid metrics-grid-compact">
            <article className="stat-card">
              <span className="stat-label">Version</span>
              <strong className="stat-value">{profile.version}</strong>
              <span className="stat-meta">Catalog version</span>
            </article>
            <article className="stat-card">
              <span className="stat-label">Rating</span>
              <strong className="stat-value">{profile.rating.toFixed(2)}</strong>
              <span className="stat-meta">Season Elo</span>
            </article>
            <article className="stat-card">
              <span className="stat-label">Record</span>
              <strong className="stat-value">
                {profile.wins}W / {profile.losses}L
              </strong>
              <span className="stat-meta">{profile.games} total games</span>
            </article>
          </div>
        ) : null}
      </section>

      {error ? (
        <div className="message-banner message-banner-error" role="alert">
          {error}
        </div>
      ) : null}

      {!profile && !error ? (
        <section className="panel skeleton-card">
          <div className="skeleton-line skeleton-line-short" />
          <div className="skeleton-line" />
          <div className="skeleton-line" />
        </section>
      ) : null}

      {profile ? (
        <section className="panel panel-strong">
          <div className="section-heading">
            <span className="eyebrow">Recent matches</span>
            <h2>Replay-backed results</h2>
          </div>

          {profile.recent_matches.length === 0 ? (
            <div className="empty-state empty-state-compact">
              <div className="empty-state-art" aria-hidden="true" />
              <div>
                <h3>No season matches yet</h3>
                <p className="muted">This agent has not logged a rated match in the current season.</p>
              </div>
            </div>
          ) : (
            <div className="leaderboard-list">
              {profile.recent_matches.map((match) => (
                <div key={match.match_id} className="leaderboard-row">
                  <div className="leaderboard-row-main">
                    <span className={match.won ? "meta-pill meta-pill-success" : "meta-pill meta-pill-danger"}>
                      {match.won ? "Win" : "Loss"}
                    </span>
                    <div>
                      <Link href={`/matches/${match.match_id}`}>{formatShortId(match.match_id, 10, 8)}</Link>
                      <p className="muted">
                        Team {match.team} · Winner {match.winning_team}
                      </p>
                    </div>
                  </div>
                  <div className="leaderboard-row-stats">
                    <Link href={`/matches/${match.match_id}`} className="button-link button-link-subtle">
                      Open viewer
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      ) : null}
    </main>
  );
}
