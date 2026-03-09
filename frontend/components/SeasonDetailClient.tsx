"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { fetchJson } from "../lib/api";
import { formatDateTime, formatStatusLabel, formatShortId } from "../lib/format";
import type { LeaderboardResponse, SeasonRecord } from "../lib/types";

interface SeasonDetailClientProps {
  seasonId: string;
}

export function SeasonDetailClient({ seasonId }: SeasonDetailClientProps) {
  const [season, setSeason] = useState<SeasonRecord | null>(null);
  const [leaderboard, setLeaderboard] = useState<LeaderboardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [allSeasons, board] = await Promise.all([
        fetchJson<SeasonRecord[]>("/seasons"),
        fetchJson<LeaderboardResponse>(`/seasons/${seasonId}/leaderboard`)
      ]);
      const selected = allSeasons.find((candidate) => candidate.season_id === seasonId) ?? null;
      setSeason(selected);
      setLeaderboard(board);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load season");
    }
  }, [seasonId]);

  useEffect(() => {
    void load();
    const interval = setInterval(() => {
      void load();
    }, 5000);
    return () => clearInterval(interval);
  }, [load]);

  const topEntries = useMemo(() => leaderboard?.entries.slice(0, 3) ?? [], [leaderboard?.entries]);

  return (
    <main className="page-shell page-stack">
      <section className="page-banner detail-banner">
        <div className="section-heading">
          <p className="breadcrumb">
            <Link href="/league">League</Link>
            <span>/</span>
            <span>{season?.name ?? formatShortId(seasonId, 10, 8)}</span>
          </p>
          <span className="eyebrow">Season profile</span>
          <h1>{season?.name ?? "Season"}</h1>
          <p className="section-copy">
            Review the active ladder, season configuration, and the agents who are shaping this deterministic rating window.
          </p>
        </div>

        {season ? (
          <div className="feature-strip">
            <span className={season.status === "active" ? "meta-pill meta-pill-success" : "meta-pill"}>
              {formatStatusLabel(season.status)}
            </span>
            <span className="meta-pill">K-factor {season.k_factor}</span>
            <span className="meta-pill">{leaderboard?.entries.length ?? 0} ranked agents</span>
          </div>
        ) : null}

        {season ? (
          <div className="metrics-grid metrics-grid-compact">
            <article className="stat-card">
              <span className="stat-label">Status</span>
              <strong className="stat-value">{formatStatusLabel(season.status)}</strong>
              <span className="stat-meta">{formatDateTime(season.updated_at)}</span>
            </article>
            <article className="stat-card">
              <span className="stat-label">Initial rating</span>
              <strong className="stat-value">{season.initial_rating}</strong>
              <span className="stat-meta">Starting Elo baseline</span>
            </article>
            <article className="stat-card">
              <span className="stat-label">K-factor</span>
              <strong className="stat-value">{season.k_factor}</strong>
              <span className="stat-meta">Rating volatility</span>
            </article>
            <article className="stat-card">
              <span className="stat-label">Entries</span>
              <strong className="stat-value">{leaderboard?.entries.length ?? 0}</strong>
              <span className="stat-meta">Agents on the ladder</span>
            </article>
          </div>
        ) : null}
      </section>

      {error ? (
        <div className="message-banner message-banner-error" role="alert">
          {error}
        </div>
      ) : null}

      {!leaderboard ? (
        <section className="panel skeleton-card">
          <div className="skeleton-line skeleton-line-short" />
          <div className="skeleton-line" />
          <div className="skeleton-line" />
        </section>
      ) : null}

      {leaderboard && leaderboard.entries.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-art" aria-hidden="true" />
          <div>
            <h3>No entries yet</h3>
            <p className="muted">Run league matches to start populating this season’s leaderboard.</p>
          </div>
        </div>
      ) : null}

      {leaderboard && leaderboard.entries.length > 0 ? (
        <>
          <section className="podium-grid">
            {topEntries.map((entry) => (
              <article key={entry.agent_id} className={`podium-card podium-card-rank-${entry.rank}`}>
                <span className="meta-pill meta-pill-accent">#{entry.rank}</span>
                <h3>{entry.name}</h3>
                <p className="mono-small">{entry.version}</p>
                <strong className="podium-value">{entry.rating.toFixed(2)}</strong>
                <p className="muted">
                  {entry.games} games · {entry.wins}W / {entry.losses}L
                </p>
              </article>
            ))}
          </section>

          <section className="panel panel-strong">
            <div className="section-heading">
              <span className="eyebrow">Leaderboard</span>
              <h2>Full standings</h2>
            </div>

            <div className="leaderboard-list">
              {leaderboard.entries.map((entry) => (
                <div key={entry.agent_id} className="leaderboard-row">
                  <div className="leaderboard-row-main">
                    <span className="leaderboard-rank">#{entry.rank}</span>
                    <div>
                      <Link href={`/league/seasons/${seasonId}/agents/${entry.agent_id}`}>{entry.name}</Link>
                      <p className="muted">
                        {entry.version} · {entry.games} games
                      </p>
                    </div>
                  </div>
                  <div className="leaderboard-row-stats">
                    <span>{entry.rating.toFixed(2)}</span>
                    <span>{entry.wins}W</span>
                    <span>{entry.losses}L</span>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </>
      ) : null}
    </main>
  );
}
