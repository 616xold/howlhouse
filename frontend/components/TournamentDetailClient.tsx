"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { fetchJson } from "../lib/api";
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
    load();
  }, [load]);

  useEffect(() => {
    if (tournament?.status !== "running") {
      return;
    }
    const interval = setInterval(load, 2500);
    return () => clearInterval(interval);
  }, [load, tournament?.status]);

  const runTournament = useCallback(async () => {
    setRunning(true);
    setError(null);
    try {
      const updated = await fetchJson<PublicTournamentRecord>(
        `/tournaments/${tournamentId}/run?sync=false`,
        {
          method: "POST"
        }
      );
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
    <main className="page-shell">
      <section className="card">
        <p className="muted">
          <Link href="/league">← Back to league</Link>
        </p>
        <h1>{tournament?.name ?? tournamentId}</h1>
        <p className="muted">
          status: {tournament?.status ?? "loading"} · champion: {tournament?.champion_agent_id ?? "-"}
        </p>
        {canRun ? (
          <button type="button" onClick={runTournament} disabled={running}>
            {running ? "Starting..." : "Run Tournament"}
          </button>
        ) : null}
        {error ? <p className="error-text">{error}</p> : null}
      </section>

      <section className="card">
        <h2>Bracket</h2>
        {!tournament ? <p className="muted">Loading bracket...</p> : null}
        {tournament ? (
          <div className="bracket-wrap">
            {tournament.bracket.rounds.map((round) => (
              <section className="round-column" key={`round-${round.round}`}>
                <h3>Round {round.round}</h3>
                <ul className="compact-list">
                  {round.matchups.map((matchup) => (
                    <li key={matchup.matchup_id} className="matchup-card">
                      <p className="mono-small">{matchup.matchup_id}</p>
                      <p>
                        {matchup.agent_a ?? "TBD"} vs {matchup.agent_b ?? "BYE"}
                      </p>
                      <p className="muted">winner: {matchup.winner_agent_id ?? "TBD"}</p>
                      {matchup.games.length > 0 ? (
                        <ul className="compact-list">
                          {matchup.games.map((game) => (
                            <li key={`${matchup.matchup_id}-g${game.game_index}`}>
                              game {game.game_index}: {game.winner_agent_id ?? "TBD"}
                              {game.match_id ? (
                                <>
                                  {" "}
                                  <Link href={`/matches/${game.match_id}`}>{game.match_id}</Link>
                                </>
                              ) : null}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="muted">No games recorded for this matchup.</p>
                      )}
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        ) : null}
      </section>
    </main>
  );
}
