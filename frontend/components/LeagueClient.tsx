"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { fetchJson } from "../lib/api";
import type {
  PublicAgentRecord,
  LeaderboardResponse,
  SeasonRecord,
  PublicTournamentRecord
} from "../lib/types";

function randomSeed(): number {
  return Math.floor(Math.random() * 1_000_000_000);
}

function formatIso(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return date.toLocaleString();
}

export function LeagueClient() {
  const [seasons, setSeasons] = useState<SeasonRecord[]>([]);
  const [activeSeasonId, setActiveSeasonId] = useState<string | null>(null);
  const [leaderboard, setLeaderboard] = useState<LeaderboardResponse | null>(null);
  const [tournaments, setTournaments] = useState<PublicTournamentRecord[]>([]);
  const [agents, setAgents] = useState<PublicAgentRecord[]>([]);

  const [seasonName, setSeasonName] = useState<string>("Season 1");
  const [initialRating, setInitialRating] = useState<number>(1200);
  const [kFactor, setKFactor] = useState<number>(32);
  const [activateOnCreate, setActivateOnCreate] = useState<boolean>(true);

  const [tournamentName, setTournamentName] = useState<string>("Weekly Cup");
  const [tournamentSeed, setTournamentSeed] = useState<number>(randomSeed);
  const [gamesPerMatchup, setGamesPerMatchup] = useState<number>(3);
  const [selectedParticipants, setSelectedParticipants] = useState<Set<string>>(new Set());

  const [error, setError] = useState<string | null>(null);

  const fetchOverview = useCallback(async () => {
    try {
      const [seasonData, agentData] = await Promise.all([
        fetchJson<SeasonRecord[]>("/seasons"),
        fetchJson<PublicAgentRecord[]>("/agents")
      ]);
      setSeasons(seasonData);
      setAgents(agentData);

      const active = seasonData.find((season) => season.status === "active") ?? null;
      setActiveSeasonId(active?.season_id ?? null);

      if (!active) {
        setLeaderboard(null);
        setTournaments([]);
        return;
      }

      const [board, tourns] = await Promise.all([
        fetchJson<LeaderboardResponse>(`/seasons/${active.season_id}/leaderboard`),
        fetchJson<PublicTournamentRecord[]>(`/tournaments?season_id=${active.season_id}`)
      ]);
      setLeaderboard(board);
      setTournaments(tourns);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load league data");
    }
  }, []);

  useEffect(() => {
    fetchOverview();
    const interval = setInterval(fetchOverview, 5000);
    return () => clearInterval(interval);
  }, [fetchOverview]);

  const activeSeason = useMemo(
    () => seasons.find((season) => season.season_id === activeSeasonId) ?? null,
    [activeSeasonId, seasons]
  );

  const submitCreateSeason = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      setError(null);
      try {
        await fetchJson<SeasonRecord>("/seasons", {
          method: "POST",
          body: JSON.stringify({
            name: seasonName,
            initial_rating: initialRating,
            k_factor: kFactor,
            activate: activateOnCreate
          })
        });
        await fetchOverview();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to create season");
      }
    },
    [activateOnCreate, fetchOverview, initialRating, kFactor, seasonName]
  );

  const activateSeason = useCallback(
    async (seasonId: string) => {
      setError(null);
      try {
        await fetchJson<SeasonRecord>(`/seasons/${seasonId}/activate`, { method: "POST" });
        await fetchOverview();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to activate season");
      }
    },
    [fetchOverview]
  );

  const toggleParticipant = useCallback((agentId: string) => {
    setSelectedParticipants((prev) => {
      const next = new Set(prev);
      if (next.has(agentId)) {
        next.delete(agentId);
      } else {
        next.add(agentId);
      }
      return next;
    });
  }, []);

  const submitCreateTournament = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (!activeSeasonId) {
        setError("Activate a season before creating a tournament.");
        return;
      }
      if (selectedParticipants.size < 2) {
        setError("Select at least two agents for the tournament.");
        return;
      }

      setError(null);
      try {
        await fetchJson<PublicTournamentRecord>("/tournaments", {
          method: "POST",
          body: JSON.stringify({
            season_id: activeSeasonId,
            name: tournamentName,
            seed: tournamentSeed,
            games_per_matchup: gamesPerMatchup,
            participant_agent_ids: Array.from(selectedParticipants).sort()
          })
        });
        setTournamentSeed(randomSeed());
        await fetchOverview();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to create tournament");
      }
    },
    [activeSeasonId, fetchOverview, gamesPerMatchup, selectedParticipants, tournamentName, tournamentSeed]
  );

  return (
    <main className="page-shell">
      <section className="card">
        <p className="muted">
          <Link href="/">← Back to matches</Link>
        </p>
        <h1>League Mode</h1>
        <p className="muted">Create seasons, track ratings, and run deterministic tournaments.</p>
        {error ? <p className="error-text">{error}</p> : null}
      </section>

      <section className="card">
        <h2>Create Season</h2>
        <form className="create-form" onSubmit={submitCreateSeason}>
          <input
            value={seasonName}
            onChange={(event) => setSeasonName(event.target.value)}
            placeholder="Season name"
          />
          <input
            type="number"
            value={initialRating}
            onChange={(event) => setInitialRating(Number(event.target.value))}
            placeholder="Initial rating"
          />
          <input
            type="number"
            value={kFactor}
            onChange={(event) => setKFactor(Number(event.target.value))}
            placeholder="K-factor"
          />
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={activateOnCreate}
              onChange={(event) => setActivateOnCreate(event.target.checked)}
            />
            Activate
          </label>
          <button type="submit">Create Season</button>
        </form>
      </section>

      <section className="card">
        <h2>Seasons</h2>
        {seasons.length === 0 ? <p className="muted">No seasons created yet.</p> : null}
        {seasons.length > 0 ? (
          <div className="table-wrap">
            <table className="matches-table">
              <thead>
                <tr>
                  <th>Season</th>
                  <th>Status</th>
                  <th>Initial</th>
                  <th>K</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {seasons.map((season) => (
                  <tr key={season.season_id}>
                    <td>
                      <Link href={`/league/seasons/${season.season_id}`}>{season.name}</Link>
                    </td>
                    <td>{season.status}</td>
                    <td>{season.initial_rating}</td>
                    <td>{season.k_factor}</td>
                    <td>{formatIso(season.created_at)}</td>
                    <td className="actions-cell">
                      {season.status !== "active" ? (
                        <button
                          type="button"
                          className="secondary-btn"
                          onClick={() => activateSeason(season.season_id)}
                        >
                          Activate
                        </button>
                      ) : (
                        <span className="alive-badge">active</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>

      <section className="card">
        <h2>Active Leaderboard</h2>
        {!activeSeason ? <p className="muted">No active season.</p> : null}
        {activeSeason ? (
          <>
            <p className="muted">
              Active season: <Link href={`/league/seasons/${activeSeason.season_id}`}>{activeSeason.name}</Link>
            </p>
            {leaderboard && leaderboard.entries.length > 0 ? (
              <div className="table-wrap">
                <table className="matches-table">
                  <thead>
                    <tr>
                      <th>Rank</th>
                      <th>Agent</th>
                      <th>Rating</th>
                      <th>Games</th>
                      <th>W</th>
                      <th>L</th>
                    </tr>
                  </thead>
                  <tbody>
                    {leaderboard.entries.map((entry) => (
                      <tr key={entry.agent_id}>
                        <td>{entry.rank}</td>
                        <td>
                          <Link href={`/league/seasons/${leaderboard.season_id}/agents/${entry.agent_id}`}>
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
            ) : (
              <p className="muted">No leaderboard entries yet.</p>
            )}
          </>
        ) : null}
      </section>

      <section className="card">
        <h2>Create Tournament</h2>
        {!activeSeason ? <p className="muted">Activate a season first.</p> : null}
        {activeSeason ? (
          <form className="league-form-grid" onSubmit={submitCreateTournament}>
            <label>
              Name
              <input
                value={tournamentName}
                onChange={(event) => setTournamentName(event.target.value)}
                placeholder="Tournament name"
              />
            </label>
            <label>
              Seed
              <input
                type="number"
                value={tournamentSeed}
                onChange={(event) => setTournamentSeed(Number(event.target.value))}
              />
            </label>
            <label>
              Games/Matchup
              <input
                type="number"
                min={1}
                value={gamesPerMatchup}
                onChange={(event) => setGamesPerMatchup(Number(event.target.value))}
              />
            </label>
            <div>
              <p className="muted">Participants</p>
              <div className="checkbox-grid">
                {agents.map((agent) => (
                  <label key={agent.agent_id} className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={selectedParticipants.has(agent.agent_id)}
                      onChange={() => toggleParticipant(agent.agent_id)}
                    />
                    {agent.name} ({agent.version})
                  </label>
                ))}
              </div>
            </div>
            <button type="submit">Create Tournament</button>
          </form>
        ) : null}
      </section>

      <section className="card">
        <h2>Tournaments</h2>
        {tournaments.length === 0 ? <p className="muted">No tournaments in active season yet.</p> : null}
        {tournaments.length > 0 ? (
          <div className="table-wrap">
            <table className="matches-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Status</th>
                  <th>Champion</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {tournaments.map((tournament) => (
                  <tr key={tournament.tournament_id}>
                    <td>
                      <Link href={`/league/tournaments/${tournament.tournament_id}`}>
                        {tournament.name}
                      </Link>
                    </td>
                    <td>{tournament.status}</td>
                    <td>{tournament.champion_agent_id ?? "-"}</td>
                    <td>{formatIso(tournament.updated_at)}</td>
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
