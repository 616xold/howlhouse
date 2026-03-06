"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { fetchJson } from "../lib/api";
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

    load();
  }, [agentId, seasonId]);

  return (
    <main className="page-shell">
      <section className="card">
        <p className="muted">
          <Link href={`/league/seasons/${seasonId}`}>← Back to season</Link>
        </p>
        <h1>{profile?.name ?? agentId}</h1>
        <p className="muted">Agent ID: {agentId}</p>
        {error ? <p className="error-text">{error}</p> : null}
        {!profile && !error ? <p className="muted">Loading profile...</p> : null}

        {profile ? (
          <div className="summary-block">
            <p>
              <strong>Version:</strong> {profile.version}
            </p>
            <p>
              <strong>Rating:</strong> {profile.rating.toFixed(2)}
            </p>
            <p>
              <strong>Games:</strong> {profile.games} ({profile.wins}W / {profile.losses}L)
            </p>
          </div>
        ) : null}
      </section>

      {profile ? (
        <section className="card">
          <h2>Recent Matches</h2>
          {profile.recent_matches.length === 0 ? <p className="muted">No season matches yet.</p> : null}
          {profile.recent_matches.length > 0 ? (
            <ul className="compact-list">
              {profile.recent_matches.map((match) => (
                <li key={match.match_id}>
                  <Link href={`/matches/${match.match_id}`}>{match.match_id}</Link> · team {match.team} ·
                  result {match.won ? "win" : "loss"} (winner {match.winning_team})
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}
    </main>
  );
}
