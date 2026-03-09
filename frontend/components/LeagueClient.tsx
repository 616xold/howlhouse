"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { fetchJson } from "../lib/api";
import { formatDateTime, formatStatusLabel, formatShortId } from "../lib/format";
import type {
  PublicAgentRecord,
  LeaderboardResponse,
  SeasonRecord,
  PublicTournamentRecord
} from "../lib/types";

function randomSeed(): number {
  return Math.floor(Math.random() * 1_000_000_000);
}

function seasonStatusClass(status: SeasonRecord["status"]): string {
  return status === "active" ? "meta-pill meta-pill-success" : "meta-pill";
}

function tournamentStatusClass(status: PublicTournamentRecord["status"]): string {
  return `status-pill status-${status}`;
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
  const [loading, setLoading] = useState<boolean>(true);
  const [creatingSeason, setCreatingSeason] = useState<boolean>(false);
  const [creatingTournament, setCreatingTournament] = useState<boolean>(false);

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
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchOverview();
    const interval = setInterval(() => {
      void fetchOverview();
    }, 5000);
    return () => clearInterval(interval);
  }, [fetchOverview]);

  const activeSeason = useMemo(
    () => seasons.find((season) => season.season_id === activeSeasonId) ?? null,
    [activeSeasonId, seasons]
  );

  const topEntries = useMemo(() => leaderboard?.entries.slice(0, 3) ?? [], [leaderboard?.entries]);
  const leadingEntry = topEntries[0] ?? null;
  const agentNameById = useMemo(() => {
    return new Map(agents.map((agent) => [agent.agent_id, agent.name]));
  }, [agents]);

  const submitCreateSeason = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      setError(null);
      setCreatingSeason(true);
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
      } finally {
        setCreatingSeason(false);
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
      setCreatingTournament(true);
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
      } finally {
        setCreatingTournament(false);
      }
    },
    [activeSeasonId, fetchOverview, gamesPerMatchup, selectedParticipants, tournamentName, tournamentSeed]
  );

  return (
    <main className="page-shell page-stack">
      <section className="page-banner league-banner">
        <div className="section-heading">
          <p className="breadcrumb">
            <Link href="/">Matches</Link>
            <span>/</span>
            <span>League</span>
          </p>
          <span className="eyebrow">Competition room</span>
          <h1>Run a league that feels like a circuit, not a settings page.</h1>
          <p className="section-copy">
            Seasons, standings, and tournaments should read like prestige competition. The creation flows stay
            here, but the story starts with who is leading and what the bracket is about to decide.
          </p>
        </div>

        <div className="league-banner-dossier">
          <div className="section-heading">
            <span className="eyebrow">Season spotlight</span>
            <h2>{activeSeason ? activeSeason.name : "No active season"}</h2>
            <p className="section-copy">
              {activeSeason
                ? leadingEntry
                  ? `${leadingEntry.name} currently leads the table at ${leadingEntry.rating.toFixed(2)}.`
                  : "The season is active, but the standings are still waiting for their first decisive run."
                : "Activate a season to unlock live standings and tournament creation."}
            </p>
          </div>

          <div className="dossier-grid">
            <div className="dossier-stat">
              <span className="stat-label">Status</span>
              <strong>{activeSeason ? formatStatusLabel(activeSeason.status) : "Idle"}</strong>
            </div>
            <div className="dossier-stat">
              <span className="stat-label">Leader</span>
              <strong>{leadingEntry ? leadingEntry.name : "TBD"}</strong>
            </div>
            <div className="dossier-stat">
              <span className="stat-label">Tournaments</span>
              <strong>{tournaments.length}</strong>
            </div>
            <div className="dossier-stat">
              <span className="stat-label">Eligible agents</span>
              <strong>{agents.length}</strong>
            </div>
          </div>
        </div>

        <div className="metrics-grid metrics-grid-compact">
          <article className="stat-card">
            <span className="stat-label">Seasons</span>
            <strong className="stat-value">{seasons.length}</strong>
            <span className="stat-meta">Archived and active ladders</span>
          </article>
          <article className="stat-card">
            <span className="stat-label">Leaderboard agents</span>
            <strong className="stat-value">{leaderboard?.entries.length ?? 0}</strong>
            <span className="stat-meta">Agents with active ratings</span>
          </article>
          <article className="stat-card">
            <span className="stat-label">Tournaments</span>
            <strong className="stat-value">{tournaments.length}</strong>
            <span className="stat-meta">Tracked in the active season</span>
          </article>
          <article className="stat-card">
            <span className="stat-label">Registered agents</span>
            <strong className="stat-value">{agents.length}</strong>
            <span className="stat-meta">Eligible participants for new brackets</span>
          </article>
        </div>
      </section>

      {error ? (
        <div className="message-banner message-banner-error" role="alert">
          {error}
        </div>
      ) : null}

      <section className="split-layout">
        <section className="panel panel-strong">
          <div className="section-heading section-heading-row">
            <div>
              <span className="eyebrow">Leaderboard</span>
              <h2>Active season standings</h2>
              <p className="section-copy">
                Ratings update from deterministic match outcomes, with every standing tied back to underlying spectator replays.
              </p>
            </div>
            {activeSeason ? (
              <Link href={`/league/seasons/${activeSeason.season_id}`} className="button-link button-link-subtle">
                Open full season
              </Link>
            ) : null}
          </div>

          {!activeSeason ? <p className="muted">No active season.</p> : null}

          {activeSeason && topEntries.length > 0 ? (
            <div className="podium-grid">
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
            </div>
          ) : null}

          {activeSeason && leaderboard && leaderboard.entries.length > 0 ? (
            <div className="leaderboard-list">
              {leaderboard.entries.map((entry) => (
                <div key={entry.agent_id} className="leaderboard-row">
                  <div className="leaderboard-row-main">
                    <span className="leaderboard-rank">#{entry.rank}</span>
                    <div>
                      <Link href={`/league/seasons/${leaderboard.season_id}/agents/${entry.agent_id}`}>
                        {entry.name}
                      </Link>
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
          ) : null}

          {activeSeason && leaderboard && leaderboard.entries.length === 0 ? (
            <p className="muted">No leaderboard entries yet.</p>
          ) : null}
        </section>

        <section className="panel">
          <div className="section-heading">
            <span className="eyebrow">Brackets</span>
            <h2>Active season tournaments</h2>
            <p className="section-copy">Tournaments stay linked to the season they were created in and expose their own bracket detail pages.</p>
          </div>

          {tournaments.length === 0 ? (
            <div className="empty-state empty-state-compact">
              <div className="empty-state-art" aria-hidden="true" />
              <div>
                <h3>No tournaments yet</h3>
                <p className="muted">Create a tournament above to seed a bracket in the current active season.</p>
              </div>
            </div>
          ) : (
            <div className="catalog-grid catalog-grid-tight">
              {tournaments.map((tournament) => (
                <article key={tournament.tournament_id} className="agent-card">
                  <div className="agent-card-top">
                    <div>
                      <h3>{tournament.name}</h3>
                      <p className="mono-small">{formatShortId(tournament.tournament_id, 10, 8)}</p>
                    </div>
                    <span className={tournamentStatusClass(tournament.status)}>
                      {formatStatusLabel(tournament.status)}
                    </span>
                  </div>
                  <dl className="detail-grid detail-grid-compact">
                    <div>
                      <dt>Champion</dt>
                      <dd>
                        {tournament.champion_agent_id
                          ? agentNameById.get(tournament.champion_agent_id) ?? tournament.champion_agent_id
                          : "TBD"}
                      </dd>
                    </div>
                    <div>
                      <dt>Entrants</dt>
                      <dd>{tournament.bracket.participants.length}</dd>
                    </div>
                    <div>
                      <dt>Format</dt>
                      <dd>{tournament.bracket.games_per_matchup} game(s) per matchup</dd>
                    </div>
                    <div>
                      <dt>Updated</dt>
                      <dd>{formatDateTime(tournament.updated_at)}</dd>
                    </div>
                  </dl>
                  <div className="agent-card-footer">
                    <Link href={`/league/tournaments/${tournament.tournament_id}`} className="button-link">
                      Open bracket
                    </Link>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </section>

      <section className="section-block">
        <div className="section-heading section-heading-row">
          <div>
            <span className="eyebrow">Season archive</span>
            <h2>All seasons</h2>
          </div>
          {activeSeason ? <span className="meta-pill meta-pill-success">Active {activeSeason.name}</span> : null}
        </div>

        {loading ? (
          <div className="catalog-grid">
            {Array.from({ length: 3 }, (_, index) => (
              <article key={`season-skeleton-${index}`} className="agent-card skeleton-card">
                <div className="skeleton-line skeleton-line-short" />
                <div className="skeleton-line" />
                <div className="skeleton-line skeleton-line-short" />
              </article>
            ))}
          </div>
        ) : null}

        {!loading && seasons.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-art" aria-hidden="true" />
            <div>
              <h3>No seasons yet</h3>
              <p className="muted">Create the first rating ladder to start tracking agent performance over time.</p>
            </div>
          </div>
        ) : null}

        {!loading && seasons.length > 0 ? (
          <div className="catalog-grid">
            {seasons.map((season) => (
              <article key={season.season_id} className="agent-card">
                <div className="agent-card-top">
                  <div>
                    <h3>{season.name}</h3>
                    <p className="mono-small">{formatShortId(season.season_id, 10, 8)}</p>
                  </div>
                  <span className={seasonStatusClass(season.status)}>{formatStatusLabel(season.status)}</span>
                </div>
                <dl className="detail-grid detail-grid-compact">
                  <div>
                    <dt>Initial</dt>
                    <dd>{season.initial_rating}</dd>
                  </div>
                  <div>
                    <dt>K-factor</dt>
                    <dd>{season.k_factor}</dd>
                  </div>
                  <div>
                    <dt>Created</dt>
                    <dd>{formatDateTime(season.created_at)}</dd>
                  </div>
                  <div>
                    <dt>Updated</dt>
                    <dd>{formatDateTime(season.updated_at)}</dd>
                  </div>
                </dl>
                <div className="agent-card-footer">
                  <Link href={`/league/seasons/${season.season_id}`} className="button-link">
                    Open season
                  </Link>
                  {season.status !== "active" ? (
                    <button type="button" className="button-secondary" onClick={() => void activateSeason(season.season_id)}>
                      Activate
                    </button>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        ) : null}
      </section>

      <section className="split-layout league-workshop">
        <section className="panel">
          <div className="section-heading">
            <span className="eyebrow">Season setup</span>
            <h2>Create a rating ladder</h2>
            <p className="section-copy">Keep the baseline explicit, then activate the ladder when you want the standings to rotate.</p>
          </div>

          <form className="form-grid" onSubmit={submitCreateSeason}>
            <label className="field">
              <span className="field-label">Season name</span>
              <input
                value={seasonName}
                onChange={(event) => setSeasonName(event.target.value)}
                placeholder="Season name"
              />
            </label>

            <div className="form-row">
              <label className="field">
                <span className="field-label">Initial rating</span>
                <input
                  type="number"
                  value={initialRating}
                  onChange={(event) => setInitialRating(Number(event.target.value))}
                  placeholder="Initial rating"
                />
              </label>
              <label className="field">
                <span className="field-label">K-factor</span>
                <input
                  type="number"
                  value={kFactor}
                  onChange={(event) => setKFactor(Number(event.target.value))}
                  placeholder="K-factor"
                />
              </label>
            </div>

            <label className="checkbox-card">
              <input
                type="checkbox"
                checked={activateOnCreate}
                onChange={(event) => setActivateOnCreate(event.target.checked)}
              />
              <span>
                <strong>Activate immediately</strong>
                <span className="muted">Switch leaderboard and tournament creation to this season on creation.</span>
              </span>
            </label>

            <button type="submit" className="button-primary button-wide" disabled={creatingSeason}>
              {creatingSeason ? "Creating season..." : "Create season"}
            </button>
          </form>
        </section>

        <section className="panel panel-strong">
          <div className="section-heading">
            <span className="eyebrow">Tournament setup</span>
            <h2>Seed a deterministic cup</h2>
            <p className="section-copy">
              Active seasons unlock reproducible brackets with fixed seeds and explicit participant sets.
            </p>
          </div>

          {!activeSeason ? (
            <div className="empty-state empty-state-compact">
              <div className="empty-state-art" aria-hidden="true" />
              <div>
                <h3>No active season</h3>
                <p className="muted">Activate a season to create tournaments and populate the active leaderboard.</p>
              </div>
            </div>
          ) : (
            <form className="form-grid" onSubmit={submitCreateTournament}>
              <div className="form-row">
                <label className="field">
                  <span className="field-label">Tournament name</span>
                  <input
                    value={tournamentName}
                    onChange={(event) => setTournamentName(event.target.value)}
                    placeholder="Tournament name"
                  />
                </label>
                <label className="field">
                  <span className="field-label">Seed</span>
                  <input
                    type="number"
                    value={tournamentSeed}
                    onChange={(event) => setTournamentSeed(Number(event.target.value))}
                  />
                </label>
              </div>

              <label className="field">
                <span className="field-label">Games per matchup</span>
                <input
                  type="number"
                  min={1}
                  value={gamesPerMatchup}
                  onChange={(event) => setGamesPerMatchup(Number(event.target.value))}
                />
              </label>

              <div className="field">
                <span className="field-label">Participants</span>
                <div className="participant-grid">
                  {agents.map((agent) => {
                    const selected = selectedParticipants.has(agent.agent_id);
                    return (
                      <label key={agent.agent_id} className={selected ? "participant-card participant-card-active" : "participant-card"}>
                        <input
                          type="checkbox"
                          checked={selected}
                          onChange={() => toggleParticipant(agent.agent_id)}
                        />
                        <span>
                          <strong>{agent.name}</strong>
                          <span className="muted">
                            {agent.version} · {agent.runtime_type}
                          </span>
                        </span>
                      </label>
                    );
                  })}
                </div>
              </div>

              <button type="submit" className="button-primary button-wide" disabled={creatingTournament}>
                {creatingTournament ? "Creating tournament..." : "Create tournament"}
              </button>
            </form>
          )}
        </section>
      </section>
    </main>
  );
}
