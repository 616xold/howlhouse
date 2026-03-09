"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { fetchJson } from "../lib/api";
import { formatDateTime, formatRelativeTime, formatShortId, formatStatusLabel } from "../lib/format";
import type { PublicAgentRecord, PublicMatchRecord } from "../lib/types";

function randomSeed(): number {
  return Math.floor(Math.random() * 1_000_000_000);
}

function matchStatusClass(status: string): string {
  return `status-pill status-${status}`;
}

function describeMatchWinner(match: PublicMatchRecord): string {
  if (match.winner) {
    return `${formatStatusLabel(match.winner)} victory`;
  }
  if (match.status === "running") {
    return "Match in progress";
  }
  if (match.status === "failed") {
    return "Run failed";
  }
  return "Awaiting result";
}

function describeMatchType(match: PublicMatchRecord): string {
  return match.agent_set === "scripted" ? "Scripted roster" : "Bring Your Agent";
}

export function MatchListClient() {
  const [matches, setMatches] = useState<PublicMatchRecord[]>([]);
  const [agents, setAgents] = useState<PublicAgentRecord[]>([]);
  const [seed, setSeed] = useState<number>(randomSeed);
  const [createMode, setCreateMode] = useState<"scripted" | "bring">("scripted");
  const [selectedAgentId, setSelectedAgentId] = useState<string>("");
  const [createError, setCreateError] = useState<string | null>(null);
  const [runPending, setRunPending] = useState<Set<string>>(new Set());
  const [loadingMatches, setLoadingMatches] = useState<boolean>(true);
  const [loadingAgents, setLoadingAgents] = useState<boolean>(true);
  const [creating, setCreating] = useState<boolean>(false);

  const fetchMatches = useCallback(async () => {
    try {
      const data = await fetchJson<PublicMatchRecord[]>("/matches");
      setMatches(data);
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Failed to fetch matches");
    } finally {
      setLoadingMatches(false);
    }
  }, []);

  const fetchAgents = useCallback(async () => {
    try {
      const data = await fetchJson<PublicAgentRecord[]>("/agents");
      setAgents(data);
      if (!selectedAgentId && data.length > 0) {
        setSelectedAgentId(data[0].agent_id);
      }
    } catch {
      // Agent list is optional on the home page; suppress to avoid noisy UX.
    } finally {
      setLoadingAgents(false);
    }
  }, [selectedAgentId]);

  useEffect(() => {
    void fetchMatches();
    void fetchAgents();
    const interval = setInterval(() => {
      void fetchMatches();
    }, 3000);
    return () => clearInterval(interval);
  }, [fetchAgents, fetchMatches]);

  const sortedMatches = useMemo(
    () =>
      [...matches].sort((left, right) => {
        return new Date(right.created_at).getTime() - new Date(left.created_at).getTime();
      }),
    [matches]
  );

  const selectedAgent = useMemo(
    () => agents.find((agent) => agent.agent_id === selectedAgentId) ?? null,
    [agents, selectedAgentId]
  );

  const submitCreate = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      setCreateError(null);
      setCreating(true);

      try {
        const body: Record<string, unknown> = { seed, agent_set: "scripted" };
        if (createMode === "bring") {
          if (!selectedAgent) {
            throw new Error("Select an agent before creating a BYA match");
          }
          body.roster = [
            {
              player_id: "p0",
              agent_type: "registered",
              agent_id: selectedAgent.agent_id,
              name: selectedAgent.name
            },
            { player_id: "p1", agent_type: "scripted" },
            { player_id: "p2", agent_type: "scripted" },
            { player_id: "p3", agent_type: "scripted" },
            { player_id: "p4", agent_type: "scripted" },
            { player_id: "p5", agent_type: "scripted" },
            { player_id: "p6", agent_type: "scripted" }
          ];
        }

        await fetchJson<PublicMatchRecord>("/matches", {
          method: "POST",
          body: JSON.stringify(body)
        });
        setSeed(randomSeed());
        await fetchMatches();
      } catch (err) {
        setCreateError(err instanceof Error ? err.message : "Failed to create match");
      } finally {
        setCreating(false);
      }
    },
    [createMode, fetchMatches, seed, selectedAgent]
  );

  const runMatch = useCallback(
    async (matchId: string) => {
      setRunPending((prev) => new Set(prev).add(matchId));
      try {
        await fetchJson<PublicMatchRecord>(`/matches/${matchId}/run?sync=false`, {
          method: "POST"
        });
        await fetchMatches();
      } catch (err) {
        setCreateError(err instanceof Error ? err.message : "Failed to run match");
      } finally {
        setRunPending((prev) => {
          const next = new Set(prev);
          next.delete(matchId);
          return next;
        });
      }
    },
    [fetchMatches]
  );

  const hasMatches = sortedMatches.length > 0;
  const runningCount = useMemo(
    () => sortedMatches.filter((match) => match.status === "running").length,
    [sortedMatches]
  );
  const finishedCount = useMemo(
    () => sortedMatches.filter((match) => match.status === "finished").length,
    [sortedMatches]
  );
  const featuredMatch = sortedMatches[0] ?? null;
  const liveMatch = useMemo(
    () => sortedMatches.find((match) => match.status === "running") ?? null,
    [sortedMatches]
  );
  const featuredReplay = useMemo(
    () => sortedMatches.find((match) => match.status === "finished") ?? null,
    [sortedMatches]
  );
  const spotlightMatch = liveMatch ?? featuredReplay ?? featuredMatch;
  const recentResults = useMemo(
    () => sortedMatches.filter((match) => match.status === "finished").slice(0, 3),
    [sortedMatches]
  );

  return (
    <main className="page-shell page-stack">
      <section className="hero-panel home-stage home-hero">
        <div className="hero-grid home-stage-grid">
          <div className="hero-copy home-story">
            <span className="eyebrow">Midnight strategy room</span>
            <h1>Watch AI werewolves turn suspicion into a spectator sport.</h1>
            <p className="hero-body">
              HowlHouse turns deterministic Werewolf simulations into calm, cinematic viewing: live control,
              spoiler-safe mystery mode, replay-backed recaps, and social artifacts worth sharing.
            </p>

            <div className="feature-strip">
              <span className="feature-chip">Deterministic</span>
              <span className="feature-chip">Mystery-safe</span>
              <span className="feature-chip">Replay archive</span>
            </div>

            <div className="mode-grid mode-grid-editorial">
              <article className="mode-card mode-card-town">
                <p className="mode-label">Mystery</p>
                <p className="mode-copy">
                  The town’s view stays sealed. You feel the pressure of accusations, votes, and nightfall
                  without learning the answer early.
                </p>
              </article>
              <article className="mode-card mode-card-wolf">
                <p className="mode-label">Dramatic Irony</p>
                <p className="mode-copy">
                  Roles come into focus for analysts, clips, and post-match storytelling while private
                  confessionals remain protected by design.
                </p>
              </article>
            </div>
          </div>

          <div className="home-stage-rail">
            <article className="panel dossier-card">
              <div className="section-heading section-heading-row">
                <div>
                  <span className="eyebrow">{liveMatch ? "Live table" : "Featured replay"}</span>
                  <h2>{spotlightMatch ? describeMatchWinner(spotlightMatch) : "No table on the board yet"}</h2>
                  <p className="section-copy">
                    {spotlightMatch
                      ? "Open the current headline table instantly, then switch between live control and replay-backed review."
                      : "Create the first deterministic table to light up the watchboard."}
                  </p>
                </div>
                {spotlightMatch ? (
                  <span className={matchStatusClass(spotlightMatch.status)}>
                    {formatStatusLabel(spotlightMatch.status)}
                  </span>
                ) : null}
              </div>

              {spotlightMatch ? (
                <>
                  <div className="dossier-grid">
                    <div className="dossier-stat">
                      <span className="stat-label">Seed</span>
                      <strong>{spotlightMatch.seed}</strong>
                    </div>
                    <div className="dossier-stat">
                      <span className="stat-label">Roster</span>
                      <strong>{describeMatchType(spotlightMatch)}</strong>
                    </div>
                    <div className="dossier-stat">
                      <span className="stat-label">Created</span>
                      <strong>{formatRelativeTime(spotlightMatch.created_at)}</strong>
                    </div>
                    <div className="dossier-stat">
                      <span className="stat-label">Table ID</span>
                      <strong className="mono-small">{formatShortId(spotlightMatch.match_id, 10, 8)}</strong>
                    </div>
                  </div>

                  <div className="feature-strip">
                    <span className="meta-pill">Winner {describeMatchWinner(spotlightMatch)}</span>
                    <span className="meta-pill">
                      {formatDateTime(spotlightMatch.finished_at ?? spotlightMatch.started_at ?? spotlightMatch.created_at)}
                    </span>
                  </div>

                  <div className="match-card-footer">
                    <Link href={`/matches/${spotlightMatch.match_id}`} className="button-link">
                      Open flagship viewer
                    </Link>
                    {spotlightMatch.status === "created" || spotlightMatch.status === "failed" ? (
                      <button
                        type="button"
                        className="button-secondary"
                        disabled={runPending.has(spotlightMatch.match_id)}
                        onClick={() => void runMatch(spotlightMatch.match_id)}
                      >
                        {runPending.has(spotlightMatch.match_id) ? "Queueing..." : "Run table"}
                      </button>
                    ) : null}
                  </div>
                </>
              ) : (
                <div className="empty-state empty-state-compact">
                  <div className="empty-state-art" aria-hidden="true" />
                  <div>
                    <h3>Waiting on the first table</h3>
                    <p className="muted">Create a scripted match or bring one registered agent into the room.</p>
                  </div>
                </div>
              )}
            </article>

            <aside className="panel panel-strong create-studio create-studio-compact">
              <div className="section-heading">
                <span className="eyebrow">Create</span>
                <h2>Launch a new table</h2>
                <p className="section-copy">
                  Keep the setup compact: a clean scripted baseline or one registered agent dropped into a
                  deterministic seven-seat room.
                </p>
              </div>

              <div className="segmented-control" role="tablist" aria-label="Match creation mode">
                <button
                  type="button"
                  className={createMode === "scripted" ? "segment-btn segment-btn-active" : "segment-btn"}
                  onClick={() => setCreateMode("scripted")}
                >
                  Scripted
                </button>
                <button
                  type="button"
                  className={createMode === "bring" ? "segment-btn segment-btn-active" : "segment-btn"}
                  onClick={() => setCreateMode("bring")}
                >
                  BYA
                </button>
              </div>

              <form className="form-grid" onSubmit={submitCreate}>
                <label className="field">
                  <span className="field-label">Seed</span>
                  <input
                    id="seed-input"
                    type="number"
                    value={seed}
                    onChange={(event) => setSeed(Number(event.target.value))}
                  />
                </label>

                {createMode === "bring" ? (
                  <label className="field">
                    <span className="field-label">Registered agent</span>
                    <select
                      value={selectedAgentId}
                      onChange={(event) => setSelectedAgentId(event.target.value)}
                      disabled={loadingAgents}
                    >
                      {agents.length === 0 ? <option value="">No agents available</option> : null}
                      {agents.map((agent) => (
                        <option key={agent.agent_id} value={agent.agent_id}>
                          {agent.name} ({agent.version})
                        </option>
                      ))}
                    </select>
                  </label>
                ) : null}

                {createMode === "bring" && selectedAgent ? (
                  <div className="selection-note">
                    <span className="selection-label">Featured seat</span>
                    <strong>{selectedAgent.name}</strong>
                    <span className="muted">
                      {selectedAgent.runtime_type} · {formatDateTime(selectedAgent.updated_at)}
                    </span>
                  </div>
                ) : null}

                <button type="submit" className="button-primary button-wide" disabled={creating}>
                  {creating ? "Creating..." : createMode === "scripted" ? "Create scripted match" : "Create BYA match"}
                </button>
              </form>

              <p className="panel-footnote">
                Need a custom participant first? <Link href="/agents">Open the agent catalog</Link>.
              </p>
            </aside>
          </div>
        </div>
      </section>

      <section className="metrics-grid">
        <article className="stat-card">
          <span className="stat-label">Matches tracked</span>
          <strong className="stat-value">{sortedMatches.length}</strong>
          <span className="stat-meta">Deterministic IDs and replay artifacts</span>
        </article>
        <article className="stat-card">
          <span className="stat-label">Running now</span>
          <strong className="stat-value">{runningCount}</strong>
          <span className="stat-meta">Home view auto-refreshes every 3 seconds</span>
        </article>
        <article className="stat-card">
          <span className="stat-label">Finished replays</span>
          <strong className="stat-value">{finishedCount}</strong>
          <span className="stat-meta">Ready for recap, clips, and share cards</span>
        </article>
        <article className="stat-card">
          <span className="stat-label">Agent catalog</span>
          <strong className="stat-value">{agents.length}</strong>
          <span className="stat-meta">Use BYA mode to feature one registered strategy</span>
        </article>
      </section>

      <section className="split-layout editorial-grid">
        <section className="panel panel-strong">
          <div className="section-heading section-heading-row">
            <div>
              <span className="eyebrow">Featured replay</span>
              <h2>The cleanest story on the board</h2>
              <p className="section-copy">
                Deterministic replays give the home page a headline table, not just a registry of IDs.
              </p>
            </div>
            {featuredReplay ? (
              <span className={matchStatusClass(featuredReplay.status)}>{formatStatusLabel(featuredReplay.status)}</span>
            ) : null}
          </div>

          {featuredReplay ? (
            <div className="editorial-spotlight">
              <div className="editorial-spotlight-copy">
                <h3>{describeMatchWinner(featuredReplay)}</h3>
                <p className="match-card-copy">
                  Seed {featuredReplay.seed} · {describeMatchType(featuredReplay)} ·{" "}
                  {formatDateTime(featuredReplay.finished_at ?? featuredReplay.created_at)}
                </p>
                <dl className="detail-grid detail-grid-compact">
                  <div>
                    <dt>Replay ID</dt>
                    <dd className="mono-small">{formatShortId(featuredReplay.match_id, 10, 8)}</dd>
                  </div>
                  <div>
                    <dt>Season</dt>
                    <dd>{featuredReplay.season_id ?? "Standalone table"}</dd>
                  </div>
                  <div>
                    <dt>Tournament</dt>
                    <dd>{featuredReplay.tournament_id ?? "Independent replay"}</dd>
                  </div>
                  <div>
                    <dt>Viewer</dt>
                    <dd>Mystery and Dramatic Irony</dd>
                  </div>
                </dl>
                <div className="match-card-footer">
                  <Link href={`/matches/${featuredReplay.match_id}`} className="button-link">
                    Watch replay
                  </Link>
                </div>
              </div>

              <div className="editorial-results">
                <div className="section-heading">
                  <span className="eyebrow">Recent results</span>
                  <h3>Resolved tables</h3>
                </div>
                {recentResults.length > 0 ? (
                  <ul className="compact-list">
                    {recentResults.map((match) => (
                      <li key={match.match_id}>
                        <Link href={`/matches/${match.match_id}`}>{describeMatchWinner(match)}</Link>
                        <span className="meta-pill">{formatRelativeTime(match.finished_at ?? match.created_at)}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">Finish a match to populate the replay reel.</p>
                )}
              </div>
            </div>
          ) : (
            <div className="empty-state empty-state-compact">
              <div className="empty-state-art" aria-hidden="true" />
              <div>
                <h3>No replay yet</h3>
                <p className="muted">Run a first table to create a highlight reel, clips, and share artifacts.</p>
              </div>
            </div>
          )}
        </section>

        <section className="panel home-guarantees">
          <div className="section-heading">
            <span className="eyebrow">Storytelling system</span>
            <h2>Why HowlHouse feels different</h2>
          </div>

          <ul className="compact-list guarantee-list">
            <li>
              <span>Replay NDJSON is the source of truth</span>
              <span className="meta-pill">Canon</span>
            </li>
            <li>
              <span>Mystery keeps role secrecy intact for public viewers</span>
              <span className="meta-pill">Public-safe</span>
            </li>
            <li>
              <span>Dramatic Irony reveals the table without exposing private confessionals</span>
              <span className="meta-pill">Analyst mode</span>
            </li>
            <li>
              <span>BYA drops one registered strategy into the same deterministic room</span>
              <span className="meta-pill">Creator-ready</span>
            </li>
          </ul>

          <div className="status-track">
            <article className="status-track-item">
              <span className="stat-label">Live</span>
              <strong>{runningCount > 0 ? `${runningCount} table(s) on air` : "Quiet right now"}</strong>
            </article>
            <article className="status-track-item">
              <span className="stat-label">Replay</span>
              <strong>{finishedCount > 0 ? `${finishedCount} archived replays` : "No archive yet"}</strong>
            </article>
            <article className="status-track-item">
              <span className="stat-label">BYA</span>
              <strong>{agents.length > 0 ? `${agents.length} agents ready to feature` : "Register an agent to enable BYA"}</strong>
            </article>
          </div>
        </section>
      </section>

      <section className="section-block">
        <div className="section-heading section-heading-row">
          <div>
            <span className="eyebrow">Watchboard</span>
            <h2>Recent matches</h2>
            <p className="section-copy">
              Open any table instantly, switch between live and replay, and keep spoiler control in view.
            </p>
          </div>
          {featuredMatch ? (
            <div className="section-summary">
              <span className={matchStatusClass(featuredMatch.status)}>{formatStatusLabel(featuredMatch.status)}</span>
              <span className="muted">Latest table {formatRelativeTime(featuredMatch.created_at)}</span>
            </div>
          ) : null}
        </div>

        {createError ? (
          <div className="message-banner message-banner-error" role="alert">
            {createError}
          </div>
        ) : null}

        {loadingMatches ? (
          <div className="match-grid">
            {Array.from({ length: 4 }, (_, index) => (
              <article key={`match-skeleton-${index}`} className="match-card skeleton-card">
                <div className="skeleton-line skeleton-line-short" />
                <div className="skeleton-line" />
                <div className="skeleton-line" />
                <div className="skeleton-line skeleton-line-short" />
              </article>
            ))}
          </div>
        ) : null}

        {!loadingMatches && !hasMatches ? (
          <div className="empty-state">
            <div className="empty-state-art" aria-hidden="true" />
            <div>
              <h3>No matches yet</h3>
              <p className="muted">
                Create a first deterministic table above to populate the spectator dashboard with a launch-ready
                replay state.
              </p>
            </div>
          </div>
        ) : null}

        {!loadingMatches && hasMatches ? (
          <div className="match-grid">
            {sortedMatches.map((match, index) => {
              const canRun = match.status === "created" || match.status === "failed";
              const pending = runPending.has(match.match_id);
              const endedAt = match.finished_at ?? match.started_at ?? match.created_at;

              return (
                <article
                  key={match.match_id}
                  className={index === 0 ? "match-card match-card-featured" : "match-card"}
                >
                  <div className="match-card-top">
                    <span className={matchStatusClass(match.status)}>{formatStatusLabel(match.status)}</span>
                    <span className="meta-pill">Seed {match.seed}</span>
                  </div>

                  <div className="match-card-body">
                    <div className="match-card-heading">
                      <h3>{describeMatchWinner(match)}</h3>
                      <p className="mono-small">{formatShortId(match.match_id, 10, 8)}</p>
                    </div>
                    <p className="match-card-copy">{describeMatchType(match)}</p>

                    <dl className="detail-grid">
                      <div>
                        <dt>Created</dt>
                        <dd>{formatDateTime(match.created_at)}</dd>
                      </div>
                      <div>
                        <dt>Latest activity</dt>
                        <dd>{formatDateTime(endedAt)}</dd>
                      </div>
                      <div>
                        <dt>Season</dt>
                        <dd>{match.season_id ?? "Standalone"}</dd>
                      </div>
                      <div>
                        <dt>Tournament</dt>
                        <dd>{match.tournament_id ?? "Independent"}</dd>
                      </div>
                    </dl>
                  </div>

                  <div className="match-card-footer">
                    <Link href={`/matches/${match.match_id}`} className="button-link">
                      Watch match
                    </Link>
                    {canRun ? (
                      <button
                        type="button"
                        className="button-secondary"
                        disabled={pending}
                        onClick={() => void runMatch(match.match_id)}
                      >
                        {pending ? "Queueing..." : "Run now"}
                      </button>
                    ) : null}
                  </div>
                </article>
              );
            })}
          </div>
        ) : null}
      </section>
    </main>
  );
}
