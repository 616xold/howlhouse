"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { fetchJson } from "../lib/api";
import { formatDateTime, formatStatusLabel, formatShortId } from "../lib/format";
import type { PublicTournamentRecord } from "../lib/types";

interface TournamentDetailClientProps {
  tournamentId: string;
}

export function TournamentDetailClient({ tournamentId }: TournamentDetailClientProps) {
  const [tournament, setTournament] = useState<PublicTournamentRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState<boolean>(false);

  const load = useCallback(async () => {
    try {
      const data = await fetchJson<PublicTournamentRecord>(`/tournaments/${tournamentId}`);
      setTournament(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load tournament");
    }
  }, [tournamentId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (tournament?.status !== "running") {
      return;
    }
    const interval = setInterval(() => {
      void load();
    }, 2500);
    return () => clearInterval(interval);
  }, [load, tournament?.status]);

  const runTournament = useCallback(async () => {
    setRunning(true);
    setError(null);
    try {
      const updated = await fetchJson<PublicTournamentRecord>(`/tournaments/${tournamentId}/run?sync=false`, {
        method: "POST"
      });
      setTournament(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start tournament");
    } finally {
      setRunning(false);
    }
  }, [tournamentId]);

  const canRun = useMemo(
    () => tournament?.status === "created" || tournament?.status === "failed",
    [tournament?.status]
  );

  return (
    <main className="page-shell page-stack">
      <section className="page-banner detail-banner">
        <div className="section-heading">
          <p className="breadcrumb">
            <Link href="/league">League</Link>
            <span>/</span>
            <span>{tournament?.name ?? formatShortId(tournamentId, 10, 8)}</span>
          </p>
          <span className="eyebrow">Tournament bracket</span>
          <h1>{tournament?.name ?? "Tournament bracket"}</h1>
          <p className="section-copy">
            Follow the bracket, jump to completed game viewers, and keep tournament execution tied to the same backend job flow.
          </p>
        </div>

        {tournament ? (
          <div className="feature-strip">
            <span className={`status-pill status-${tournament.status}`}>{formatStatusLabel(tournament.status)}</span>
            <span className="meta-pill">Seed {tournament.seed}</span>
            <span className="meta-pill">{tournament.bracket.rounds.length} rounds</span>
          </div>
        ) : null}

        {tournament ? (
          <div className="metrics-grid metrics-grid-compact">
            <article className="stat-card">
              <span className="stat-label">Status</span>
              <strong className="stat-value">{formatStatusLabel(tournament.status)}</strong>
              <span className="stat-meta">{formatDateTime(tournament.updated_at)}</span>
            </article>
            <article className="stat-card">
              <span className="stat-label">Champion</span>
              <strong className="stat-value">{tournament.champion_agent_id ?? "TBD"}</strong>
              <span className="stat-meta">Resolved from the bracket record</span>
            </article>
            <article className="stat-card">
              <span className="stat-label">Rounds</span>
              <strong className="stat-value">{tournament.bracket.rounds.length}</strong>
              <span className="stat-meta">Seed {tournament.seed}</span>
            </article>
          </div>
        ) : null}
      </section>

      {canRun ? (
        <section className="panel panel-strong">
          <div className="section-heading section-heading-row">
            <div>
              <span className="eyebrow">Execution</span>
              <h2>Run this tournament</h2>
            </div>
            <button type="button" className="button-primary" onClick={() => void runTournament()} disabled={running}>
              {running ? "Starting..." : "Run tournament"}
            </button>
          </div>
        </section>
      ) : null}

      {error ? (
        <div className="message-banner message-banner-error" role="alert">
          {error}
        </div>
      ) : null}

      {!tournament ? (
        <section className="panel skeleton-card">
          <div className="skeleton-line skeleton-line-short" />
          <div className="skeleton-line" />
          <div className="skeleton-line" />
        </section>
      ) : null}

      {tournament ? (
        <section className="panel panel-strong">
          <div className="section-heading">
            <span className="eyebrow">Bracket</span>
            <h2>Round-by-round view</h2>
          </div>

          <div className="bracket-wrap">
            {tournament.bracket.rounds.map((round) => (
              <section className="round-column" key={`round-${round.round}`}>
                <div className="section-heading">
                  <span className="eyebrow">Round {round.round}</span>
                  <h3>{round.matchups.length} matchup(s)</h3>
                </div>

                <div className="matchup-stack">
                  {round.matchups.map((matchup) => (
                    <article key={matchup.matchup_id} className="matchup-card">
                      <div className="agent-card-top">
                        <div>
                          <strong>{matchup.agent_a ?? "TBD"}</strong>
                          <p className="muted">vs {matchup.agent_b ?? "BYE"}</p>
                        </div>
                        <span className="meta-pill">
                          Winner {matchup.winner_agent_id ?? "TBD"}
                        </span>
                      </div>

                      <p className="mono-small">{formatShortId(matchup.matchup_id, 10, 8)}</p>

                      {matchup.games.length > 0 ? (
                        <div className="game-chip-grid">
                          {matchup.games.map((game) => (
                            <div key={`${matchup.matchup_id}-g${game.game_index}`} className="game-chip">
                              <span>Game {game.game_index}</span>
                              <span className="muted">{game.winner_agent_id ?? "TBD"}</span>
                              {game.match_id ? (
                                <Link href={`/matches/${game.match_id}`} className="button-link button-link-subtle">
                                  Open match
                                </Link>
                              ) : null}
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="muted">No games recorded for this matchup yet.</p>
                      )}
                    </article>
                  ))}
                </div>
              </section>
            ))}
          </div>
        </section>
      ) : null}
    </main>
  );
}
