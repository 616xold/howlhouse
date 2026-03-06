"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { fetchJson } from "../lib/api";
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
    load();
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, [load]);

  return (
    <main className="page-shell">
      <section className="card">
        <p className="muted">
          <Link href="/league">← Back to league</Link>
        </p>
        <h1>{season?.name ?? seasonId}</h1>
        {season ? (
          <p className="muted">
            status: {season.status} · initial rating: {season.initial_rating} · k-factor: {season.k_factor}
          </p>
        ) : null}
        {error ? <p className="error-text">{error}</p> : null}
      </section>

      <section className="card">
        <h2>Leaderboard</h2>
        {!leaderboard ? <p className="muted">Loading leaderboard...</p> : null}
        {leaderboard && leaderboard.entries.length === 0 ? (
          <p className="muted">No entries yet.</p>
        ) : null}
        {leaderboard && leaderboard.entries.length > 0 ? (
          <div className="table-wrap">
            <table className="matches-table">
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Agent</th>
                  <th>Rating</th>
                  <th>Games</th>
                  <th>Wins</th>
                  <th>Losses</th>
                </tr>
              </thead>
              <tbody>
                {leaderboard.entries.map((entry) => (
                  <tr key={entry.agent_id}>
                    <td>{entry.rank}</td>
                    <td>
                      <Link href={`/league/seasons/${seasonId}/agents/${entry.agent_id}`}>
                        {entry.name}
                      </Link>
                    </td>
                    <td>{entry.rating.toFixed(2)}</td>
                    <td>{entry.games}</td>
                    <td>{entry.wins}</td>
                    <td>{entry.losses}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </main>
  );
}
