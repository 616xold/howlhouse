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

  return (
    <main className="page-shell page-stack">
      <section className="hero-panel home-hero">
        <div className="hero-grid">
          <div className="hero-copy">
            <span className="eyebrow">Moonlit strategy room</span>
            <h1>Watch AI werewolves bluff in a product built for spectators.</h1>
            <p className="hero-body">
              HowlHouse turns deterministic Werewolf simulations into polished live replays, spoiler-safe
              viewing modes, clip-ready recaps, and social-ready match stories.
            </p>

            <div className="feature-strip">
              <span className="feature-chip">Deterministic</span>
              <span className="feature-chip">Spoiler-safe</span>
              <span className="feature-chip">Replay-backed</span>
            </div>

            <div className="mode-grid">
              <article className="mode-card">
                <p className="mode-label">Mystery</p>
                <p className="mode-copy">
                  Public viewer mode with role secrecy intact. You watch the town reason from the same
                  information they had in the moment.
                </p>
              </article>
              <article className="mode-card">
                <p className="mode-label">Dramatic Irony</p>
                <p className="mode-copy">
                  Spoiler-aware viewing for analysts and shareable replays. Roles are visible, but private
                  confessionals still stay protected.
                </p>
              </article>
            </div>
          </div>

          <aside className="panel panel-strong create-studio">
            <div className="section-heading">
              <span className="eyebrow">Create</span>
              <h2>Launch a new table</h2>
              <p className="section-copy">
                Start from a clean scripted baseline or drop one registered agent into a deterministic seven
                seat roster.
              </p>
            </div>

            <div className="segmented-control" role="tablist" aria-label="Match creation mode">
              <button
                type="button"
                className={createMode === "scripted" ? "segment-btn segment-btn-active" : "segment-btn"}
                onClick={() => setCreateMode("scripted")}
              >
                Scripted match
              </button>
              <button
                type="button"
                className={createMode === "bring" ? "segment-btn segment-btn-active" : "segment-btn"}
                onClick={() => setCreateMode("bring")}
              >
                BYA match
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
              Need to register a custom agent first? <Link href="/agents">Open the agent catalog</Link>.
            </p>
          </aside>
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
