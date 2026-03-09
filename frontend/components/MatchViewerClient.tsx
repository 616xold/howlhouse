"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { apiUrl, fetchJson } from "../lib/api";
import { formatDateTime, formatEventClock, formatShortId, formatStatusLabel, getInitials } from "../lib/format";
import { useMatchEvents } from "../lib/useMatchEvents";
import type {
  MatchEventMode,
  PublicMatchRecord,
  RecapPayload,
  ReplayEvent,
  RosterEntry,
  VisibilityMode
} from "../lib/types";
import { PredictionWidget } from "./PredictionWidget";

function asRecord(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object") {
    return value as Record<string, unknown>;
  }
  return {};
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function asNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function formatPhaseLabel(phaseRaw: string, day: number, roundRaw: string): string {
  if (phaseRaw === "game_over") {
    return "Game Over";
  }
  if (day <= 0) {
    return formatStatusLabel(phaseRaw);
  }
  const phase = formatStatusLabel(phaseRaw);
  const round = roundRaw ? ` · ${formatStatusLabel(roundRaw)}` : "";
  return `Day ${day} · ${phase}${round}`;
}

function withHighlightClass(baseClass: string, eventId: string, highlightedEventId: string | null): string {
  return highlightedEventId === eventId ? `${baseClass} timeline-card-highlight` : baseClass;
}

function playerName(playerNameById: Map<string, string>, playerId: string): string {
  return playerNameById.get(playerId) ?? playerId;
}

function timelineVariant(type: string): string {
  if (type === "public_message") {
    return "timeline-card timeline-card-public";
  }
  if (type === "match_created") {
    return "timeline-card timeline-card-setup";
  }
  if (type === "vote_cast") {
    return "timeline-card timeline-card-vote";
  }
  if (type === "roles_assigned") {
    return "timeline-card timeline-card-reveal";
  }
  if (type === "player_killed" || type === "player_eliminated") {
    return "timeline-card timeline-card-danger";
  }
  if (type === "match_ended") {
    return "timeline-card timeline-card-resolution";
  }
  if (type === "vote_result") {
    return "timeline-card timeline-card-verdict";
  }
  return "timeline-card";
}

function roleClass(role: string): string {
  const normalized = role.toLowerCase();
  if (normalized.includes("wolf")) {
    return "meta-pill meta-pill-danger";
  }
  if (normalized.includes("seer") || normalized.includes("doctor")) {
    return "meta-pill meta-pill-accent";
  }
  return "meta-pill meta-pill-success";
}

function clipKindClass(kind: string): string {
  if (kind === "death" || kind === "ending") {
    return "meta-pill meta-pill-danger";
  }
  if (kind === "vote" || kind === "close_vote") {
    return "meta-pill meta-pill-accent";
  }
  return "meta-pill";
}

interface MatchViewerClientProps {
  matchId: string;
}

export function MatchViewerClient({ matchId }: MatchViewerClientProps) {
  const [match, setMatch] = useState<PublicMatchRecord | null>(null);
  const [mode, setMode] = useState<MatchEventMode>("replay");
  const [visibility, setVisibility] = useState<VisibilityMode>("public");
  const [actionError, setActionError] = useState<string | null>(null);
  const [runningRequest, setRunningRequest] = useState<boolean>(false);
  const [recap, setRecap] = useState<RecapPayload | null>(null);
  const [recapError, setRecapError] = useState<string | null>(null);
  const [highlightedEventId, setHighlightedEventId] = useState<string | null>(null);
  const highlightTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchMatch = useCallback(async () => {
    try {
      const next = await fetchJson<PublicMatchRecord>(`/matches/${matchId}`);
      setMatch(next);
      if (next.status === "running") {
        setMode("live");
      }
      if (next.status === "finished") {
        setMode("replay");
      }
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to load match");
    }
  }, [matchId]);

  useEffect(() => {
    void fetchMatch();
    const interval = setInterval(() => {
      void fetchMatch();
    }, 3000);
    return () => clearInterval(interval);
  }, [fetchMatch]);

  const { events, isLoading, error: eventsError } = useMatchEvents(matchId, visibility, mode);

  useEffect(() => {
    if (match?.status !== "finished") {
      setRecap(null);
      setRecapError(null);
      return;
    }

    let closed = false;

    async function loadRecap() {
      try {
        const nextRecap = await fetchJson<RecapPayload>(`/matches/${matchId}/recap?visibility=${visibility}`);
        if (!closed) {
          setRecap(nextRecap);
          setRecapError(null);
        }
      } catch (err) {
        if (closed) {
          return;
        }
        const message = err instanceof Error ? err.message : "Failed to load recap";
        if (message.includes("recap not ready")) {
          setRecap(null);
          setRecapError(null);
          return;
        }
        setRecap(null);
        setRecapError(message);
      }
    }

    void loadRecap();
    const interval = setInterval(() => {
      void loadRecap();
    }, 5000);

    return () => {
      closed = true;
      clearInterval(interval);
    };
  }, [match?.status, matchId, visibility]);

  useEffect(() => {
    return () => {
      if (highlightTimerRef.current) {
        clearTimeout(highlightTimerRef.current);
      }
    };
  }, []);

  const roster = useMemo<RosterEntry[]>(() => {
    const createdEvent = events.find((event) => event.type === "match_created");
    const payload = asRecord(createdEvent?.payload);
    const rosterValue = payload.roster;

    if (Array.isArray(rosterValue)) {
      const parsed = rosterValue
        .map((entry) => asRecord(entry))
        .map((entry) => ({
          player_id: asString(entry.player_id),
          name: asString(entry.name, asString(entry.player_id))
        }))
        .filter((entry) => entry.player_id.length > 0);
      if (parsed.length > 0) {
        return parsed;
      }
    }

    const config = asRecord(match?.config);
    const names = asRecord(match?.names);
    const playerCount = asNumber(config.player_count, 0);
    return Array.from({ length: playerCount }, (_, index) => {
      const playerId = `p${index}`;
      const candidateName = names[playerId];
      return {
        player_id: playerId,
        name: typeof candidateName === "string" ? candidateName : playerId
      };
    });
  }, [events, match?.config, match?.names]);

  const rolesByPlayer = useMemo<Record<string, string>>(() => {
    const roleEvent = events.find((event) => event.type === "roles_assigned");
    if (!roleEvent) {
      return {};
    }
    const payload = asRecord(roleEvent.payload);
    const rolesRaw = asRecord(payload.roles);
    const roles: Record<string, string> = {};
    Object.entries(rolesRaw).forEach(([playerId, role]) => {
      if (typeof role === "string") {
        roles[playerId] = role;
      }
    });
    return roles;
  }, [events]);

  const aliveSet = useMemo(() => {
    const alive = new Set(roster.map((entry) => entry.player_id));
    for (const event of events) {
      if (event.type === "player_killed" || event.type === "player_eliminated") {
        const payload = asRecord(event.payload);
        const playerId = asString(payload.player_id);
        if (playerId) {
          alive.delete(playerId);
        }
      }
    }
    return alive;
  }, [events, roster]);

  const playerNameById = useMemo(() => {
    const map = new Map<string, string>();
    for (const entry of roster) {
      map.set(entry.player_id, entry.name);
    }
    return map;
  }, [roster]);

  const canRun = match?.status === "created" || match?.status === "failed";

  const runMatch = useCallback(async () => {
    setRunningRequest(true);
    setActionError(null);
    try {
      await fetchJson<PublicMatchRecord>(`/matches/${matchId}/run?sync=false`, {
        method: "POST"
      });
      setMode("live");
      await fetchMatch();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to run match");
    } finally {
      setRunningRequest(false);
    }
  }, [fetchMatch, matchId]);

  const requiredWolves = useMemo(() => {
    const config = asRecord(match?.config);
    return asNumber(config.werewolves, 2);
  }, [match?.config]);

  const shareCardVisibility = visibility === "public" ? "public" : "spoilers";
  const shareCardUrl = apiUrl(`/matches/${matchId}/share-card?visibility=${shareCardVisibility}`);

  const handleClipClick = useCallback((eventId: string) => {
    const element = document.getElementById(eventId);
    if (element) {
      element.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    setHighlightedEventId(eventId);
    if (highlightTimerRef.current) {
      clearTimeout(highlightTimerRef.current);
    }
    highlightTimerRef.current = setTimeout(() => {
      setHighlightedEventId(null);
      highlightTimerRef.current = null;
    }, 2000);
  }, []);

  const publicMessageCount = useMemo(
    () => events.filter((event) => event.type === "public_message").length,
    [events]
  );
  const voteCount = useMemo(() => events.filter((event) => event.type === "vote_cast").length, [events]);
  const killCount = useMemo(
    () => events.filter((event) => event.type === "player_killed" || event.type === "player_eliminated").length,
    [events]
  );
  const phaseLabel = useMemo(() => {
    const phases = [...events].reverse().find((event) => event.type === "phase_started");
    if (!phases) {
      return "Awaiting replay";
    }
    const payload = asRecord(phases.payload);
    return formatPhaseLabel(asString(payload.phase), asNumber(payload.day), asString(payload.round));
  }, [events]);

  const winnerLabel = useMemo(() => {
    if (match?.winner) {
      return formatStatusLabel(match.winner);
    }
    if (recap?.winner.team) {
      return formatStatusLabel(recap.winner.team);
    }
    return "Undecided";
  }, [match?.winner, recap?.winner.team]);

  const renderEvent = useCallback(
    (event: ReplayEvent) => {
      const payload = asRecord(event.payload);

      if (event.type === "phase_started") {
        return (
          <li id={event.id} key={event.id} className="phase-divider">
            <span className="phase-divider-line" aria-hidden="true" />
            <div className="phase-divider-copy">
              <span className="phase-divider-kicker">Phase change</span>
              <p className="phase-divider-label">
                {formatPhaseLabel(asString(payload.phase, event.type), asNumber(payload.day, 0), asString(payload.round))}
              </p>
              <p className="phase-divider-meta">Tick {event.t} · {formatEventClock(event.ts)}</p>
            </div>
          </li>
        );
      }

      if (event.type === "public_message") {
        const speaker = playerName(playerNameById, asString(payload.player_id));
        return (
          <li
            id={event.id}
            key={event.id}
            className={withHighlightClass(timelineVariant(event.type), event.id, highlightedEventId)}
          >
            <div className="timeline-card-shell">
              <span className="timeline-avatar">{getInitials(speaker)}</span>
              <div className="timeline-copy">
                <div className="timeline-head">
                  <div className="timeline-title">
                    <span className="timeline-kicker">Public message</span>
                    <strong className="timeline-speaker">{speaker}</strong>
                  </div>
                  <span className="timeline-time">{formatEventClock(event.ts)}</span>
                </div>
                <p className="timeline-body">{asString(payload.text)}</p>
              </div>
            </div>
          </li>
        );
      }

      if (event.type === "vote_cast") {
        const voter = playerName(playerNameById, asString(payload.voter_id));
        const target = playerName(playerNameById, asString(payload.target_id));
        return (
          <li
            id={event.id}
            key={event.id}
            className={withHighlightClass(timelineVariant(event.type), event.id, highlightedEventId)}
          >
            <div className="timeline-head">
              <div className="timeline-title">
                <span className="timeline-kicker">Vote lodged</span>
                <strong className="timeline-speaker">
                  {voter} → {target}
                </strong>
              </div>
              <span className="timeline-time">{formatEventClock(event.ts)}</span>
            </div>
            <p className="timeline-body">
              <strong>{voter}</strong> places public pressure on <strong>{target}</strong>.
            </p>
          </li>
        );
      }

      if (event.type === "player_killed" || event.type === "player_eliminated") {
        const playerId = asString(payload.player_id);
        const verb = event.type === "player_killed" ? "was killed overnight" : "was eliminated by vote";
        return (
          <li
            id={event.id}
            key={event.id}
            className={withHighlightClass(timelineVariant(event.type), event.id, highlightedEventId)}
          >
            <div className="timeline-head">
              <div className="timeline-title">
                <span className="timeline-kicker">{event.type === "player_killed" ? "Night kill" : "Elimination"}</span>
                <strong className="timeline-speaker">{playerName(playerNameById, playerId)}</strong>
              </div>
              <span className="timeline-time">{formatEventClock(event.ts)}</span>
            </div>
            <p className="timeline-body">
              <strong>{playerName(playerNameById, playerId)}</strong> {verb}.
            </p>
          </li>
        );
      }

      if (event.type === "vote_result") {
        const eliminated = asString(payload.eliminated);
        const tally = asRecord(payload.tally);
        return (
          <li
            id={event.id}
            key={event.id}
            className={withHighlightClass(timelineVariant(event.type), event.id, highlightedEventId)}
          >
            <div className="timeline-head">
              <div className="timeline-title">
                <span className="timeline-kicker">Vote result</span>
                <strong className="timeline-speaker">{playerName(playerNameById, eliminated)} leaves the table</strong>
              </div>
              <span className="timeline-time">{formatEventClock(event.ts)}</span>
            </div>
            <p className="timeline-body">The tally resolves publicly and the room narrows.</p>
            <div className="timeline-tags">
              {Object.entries(tally)
                .sort(([left], [right]) => left.localeCompare(right))
                .map(([playerId, votesValue]) => (
                  <span key={`${event.id}-${playerId}`} className="meta-pill">
                    {playerName(playerNameById, playerId)} {String(votesValue)}
                  </span>
                ))}
            </div>
          </li>
        );
      }

      if (event.type === "match_ended") {
        return (
          <li
            id={event.id}
            key={event.id}
            className={withHighlightClass(timelineVariant(event.type), event.id, highlightedEventId)}
          >
            <div className="timeline-head">
              <div className="timeline-title">
                <span className="timeline-kicker">Final verdict</span>
                <strong className="timeline-speaker">{formatStatusLabel(asString(payload.winning_team))} prevail</strong>
              </div>
              <span className="timeline-time">{formatEventClock(event.ts)}</span>
            </div>
            <p className="timeline-body">
              <strong>{formatStatusLabel(asString(payload.winning_team))}</strong> win by{" "}
              {formatStatusLabel(asString(payload.reason))}.
            </p>
          </li>
        );
      }

      if (event.type === "roles_assigned") {
        return (
          <li
            id={event.id}
            key={event.id}
            className={withHighlightClass(timelineVariant(event.type), event.id, highlightedEventId)}
          >
            <div className="timeline-head">
              <div className="timeline-title">
                <span className="timeline-kicker">Role reveal</span>
                <strong className="timeline-speaker">Dramatic Irony is available</strong>
              </div>
              <span className="timeline-time">{formatEventClock(event.ts)}</span>
            </div>
            <p className="timeline-body">Roles are available in Dramatic Irony mode.</p>
          </li>
        );
      }

      if (event.type === "match_created") {
        return (
          <li
            id={event.id}
            key={event.id}
            className={withHighlightClass(timelineVariant(event.type), event.id, highlightedEventId)}
          >
            <div className="timeline-head">
              <div className="timeline-title">
                <span className="timeline-kicker">Table seeded</span>
                <strong className="timeline-speaker">Room configured and ready</strong>
              </div>
              <span className="timeline-time">{formatEventClock(event.ts)}</span>
            </div>
            <p className="timeline-body">Match created and ready to run.</p>
          </li>
        );
      }

      return (
        <li id={event.id} key={event.id} className={withHighlightClass(timelineVariant(event.type), event.id, highlightedEventId)}>
          <div className="timeline-head">
            <div className="timeline-title">
              <span className="timeline-kicker">{formatStatusLabel(event.type)}</span>
              <strong className="timeline-speaker">System event</strong>
            </div>
            <span className="timeline-time">{formatEventClock(event.ts)}</span>
          </div>
          <p className="timeline-body">
            {Object.entries(payload)
              .slice(0, 4)
              .map(([key, value]) => `${formatStatusLabel(key)} ${String(value)}`)
              .join(" · ") || "System event"}
          </p>
        </li>
      );
    },
    [highlightedEventId, playerNameById]
  );

  return (
    <main className="page-shell page-stack viewer-page">
      <section className="hero-panel viewer-hero">
        <div className="hero-grid viewer-hero-grid">
          <div className="hero-copy">
            <p className="breadcrumb">
              <Link href="/">Matches</Link>
              <span>/</span>
              <span>{formatShortId(matchId, 10, 8)}</span>
            </p>
            <span className="eyebrow">Spectator viewer</span>
            <h1>{winnerLabel} pressure, archived with control.</h1>
            <p className="hero-body">
              Track the transcript in real time, shift between Mystery and Dramatic Irony without changing access
              rules, and jump from recap artifacts straight back into the source replay.
            </p>

            <div className="feature-strip">
              <span className={`status-pill status-${match?.status ?? "created"}`}>
                {formatStatusLabel(match?.status ?? "loading")}
              </span>
              <span className="feature-chip">{mode === "live" ? "Live feed" : "Replay mode"}</span>
              <span className="feature-chip">{visibility === "public" ? "Mystery" : "Dramatic Irony"}</span>
            </div>
          </div>

          <div className="viewer-hero-rail">
            <article className="panel dossier-card viewer-phase-card">
              <div className="section-heading">
                <span className="eyebrow">Current phase</span>
                <h2>{phaseLabel}</h2>
                <p className="section-copy">Replay tick {events.at(-1)?.t ?? 0} with deterministic state carried forward automatically.</p>
              </div>
              <div className="dossier-grid">
                <div className="dossier-stat">
                  <span className="stat-label">Winner</span>
                  <strong>{winnerLabel}</strong>
                </div>
                <div className="dossier-stat">
                  <span className="stat-label">Messages</span>
                  <strong>{publicMessageCount}</strong>
                </div>
                <div className="dossier-stat">
                  <span className="stat-label">Votes</span>
                  <strong>{voteCount}</strong>
                </div>
                <div className="dossier-stat">
                  <span className="stat-label">Eliminations</span>
                  <strong>{killCount}</strong>
                </div>
              </div>
            </article>
          </div>
        </div>
      </section>

      <div className="viewer-shell">
        <section className="viewer-main">
          <section className="panel viewer-toolbar">
            <div className="viewer-toolbar-row">
              <div className="section-heading">
                <span className="eyebrow">Controls</span>
                <h2>Replay control room</h2>
                <p className="section-copy">
                  Shift between live and replay instantly. Visibility changes the spectator layer, not the backend rules.
                </p>
              </div>

              <div className="toolbar-stack">
                <div className="control-cluster">
                  <span className="field-label">Feed</span>
                  <div className="segmented-control" role="tablist" aria-label="Viewer mode">
                    <button
                      type="button"
                      className={mode === "live" ? "segment-btn segment-btn-active" : "segment-btn"}
                      onClick={() => setMode("live")}
                    >
                      Live
                    </button>
                    <button
                      type="button"
                      className={mode === "replay" ? "segment-btn segment-btn-active" : "segment-btn"}
                      onClick={() => setMode("replay")}
                    >
                      Replay
                    </button>
                  </div>
                </div>

                <div className="control-cluster">
                  <span className="field-label">Visibility</span>
                  <div className="segmented-control" role="tablist" aria-label="Visibility mode">
                    <button
                      type="button"
                      className={visibility === "public" ? "segment-btn segment-btn-active" : "segment-btn"}
                      onClick={() => setVisibility("public")}
                    >
                      Mystery
                    </button>
                    <button
                      type="button"
                      className={visibility === "spoilers" ? "segment-btn segment-btn-active" : "segment-btn"}
                      onClick={() => setVisibility("spoilers")}
                    >
                      Dramatic Irony
                    </button>
                  </div>
                </div>

                {canRun ? (
                  <button type="button" className="button-primary" onClick={() => void runMatch()} disabled={runningRequest}>
                    {runningRequest ? "Starting..." : "Run match"}
                  </button>
                ) : null}
              </div>
            </div>

            <div className="viewer-summary-row">
              <span className="meta-pill">Winner {winnerLabel}</span>
              <span className="meta-pill">Created {formatDateTime(match?.created_at ?? null)}</span>
              <span className="meta-pill">
                Updated {formatDateTime(match?.finished_at ?? match?.started_at ?? match?.created_at ?? null)}
              </span>
              <span className="meta-pill">{events.length} replay events</span>
            </div>
          </section>

          {actionError ? (
            <div className="message-banner message-banner-error" role="alert">
              {actionError}
            </div>
          ) : null}
          {eventsError ? (
            <div className="message-banner message-banner-error" role="alert">
              {eventsError}
            </div>
          ) : null}

          <section className="panel transcript-panel">
            <div className="section-heading section-heading-row">
              <div>
                <span className="eyebrow">Transcript</span>
                <h2>Control-room transcript</h2>
                <p className="section-copy">
                  Every card is sourced from replay NDJSON or the live SSE stream for this match, with event styling that mirrors the table state.
                </p>
              </div>
              <div className="section-summary">
                <span className="feature-chip">{isLoading ? `Loading ${mode}...` : "Synced"}</span>
                <span className="muted">{visibility === "public" ? "Spoiler-safe" : "Spoiler-aware"}</span>
              </div>
            </div>

            {isLoading ? (
              <div className="timeline-skeleton">
                {Array.from({ length: 5 }, (_, index) => (
                  <div key={`timeline-skeleton-${index}`} className="timeline-card skeleton-card">
                    <div className="skeleton-line skeleton-line-short" />
                    <div className="skeleton-line" />
                    <div className="skeleton-line skeleton-line-short" />
                  </div>
                ))}
              </div>
            ) : null}

            {!isLoading && events.length === 0 ? (
              <div className="empty-state empty-state-compact">
                <div className="empty-state-art" aria-hidden="true" />
                <div>
                  <h3>No events yet</h3>
                  <p className="muted">Run the match or wait for the stream to begin emitting replay events.</p>
                </div>
              </div>
            ) : null}

            {!isLoading && events.length > 0 ? <ol className="timeline-list">{events.map(renderEvent)}</ol> : null}
          </section>
        </section>

        <aside className="viewer-sidebar">
          <section className="panel roster-panel">
            <div className="section-heading section-heading-row">
              <div>
                <span className="eyebrow">Roster</span>
                <h3>Table state</h3>
              </div>
              <span className="meta-pill">{aliveSet.size} alive</span>
            </div>

            <div className="roster-grid">
              {roster.map((entry) => {
                const alive = aliveSet.has(entry.player_id);
                const role = rolesByPlayer[entry.player_id];
                return (
                  <article key={entry.player_id} className={alive ? "player-card" : "player-card player-card-dead"}>
                    <div className="player-avatar">{getInitials(entry.name)}</div>
                    <div className="player-copy">
                      <strong>{entry.name}</strong>
                      <span className="mono-small">{entry.player_id}</span>
                    </div>
                    <div className="player-state">
                      <span className={alive ? "meta-pill meta-pill-success" : "meta-pill meta-pill-danger"}>
                        {alive ? "Alive" : "Dead"}
                      </span>
                      {visibility !== "public" && role ? <span className={roleClass(role)}>{formatStatusLabel(role)}</span> : null}
                    </div>
                    <p className="player-note">{alive ? "Still shaping the room" : "Removed from the table"}</p>
                  </article>
                );
              })}
            </div>
          </section>

          <PredictionWidget matchId={matchId} roster={roster} requiredWolves={requiredWolves} />
        </aside>
      </div>

      <section className="panel panel-strong recap-stage">
        <div className="section-heading section-heading-row">
          <div>
            <span className="eyebrow">Town Crier</span>
            <h2>Recap, clips, and share artifact</h2>
            <p className="section-copy">
              Finished matches generate the narrative layer: recap bullets, quote jumps, pivotal clips, and the share card preview.
            </p>
          </div>
          <span className="meta-pill">{visibility === "public" ? "Public teaser" : "Spoiler view"}</span>
        </div>

        {match?.status !== "finished" ? (
          <div className="empty-state empty-state-compact">
            <div className="empty-state-art" aria-hidden="true" />
            <div>
              <h3>Recap pending</h3>
              <p className="muted">Finish the match to generate bullets, narration, clips, and the share card preview.</p>
            </div>
          </div>
        ) : null}

        {recapError ? (
          <div className="message-banner message-banner-error" role="alert">
            {recapError}
          </div>
        ) : null}

        {match?.status === "finished" && !recap && !recapError ? (
          <div className="timeline-skeleton">
            <div className="timeline-card skeleton-card">
              <div className="skeleton-line skeleton-line-short" />
              <div className="skeleton-line" />
              <div className="skeleton-line" />
            </div>
          </div>
        ) : null}

        {recap ? (
          <div className="recap-stage-grid">
            <div className="recap-story-column">
              <div className="metrics-grid metrics-grid-compact">
                <article className="stat-card">
                  <span className="stat-label">Winner</span>
                  <strong className="stat-value">{formatStatusLabel(recap.winner.team)}</strong>
                  <span className="stat-meta">{formatStatusLabel(recap.winner.reason)}</span>
                </article>
                <article className="stat-card">
                  <span className="stat-label">Days</span>
                  <strong className="stat-value">{recap.stats.days}</strong>
                  <span className="stat-meta">{recap.stats.public_messages} public messages</span>
                </article>
                <article className="stat-card">
                  <span className="stat-label">Votes</span>
                  <strong className="stat-value">{recap.stats.votes}</strong>
                  <span className="stat-meta">{recap.stats.eliminations} eliminations</span>
                </article>
              </div>

              <div className="bullet-deck">
                <div className="section-heading">
                  <span className="eyebrow">Brief</span>
                  <h4>What the public story records</h4>
                </div>
                <ul className="bullet-list bullet-list-strong">
                  {recap.bullets.map((bullet, index) => (
                    <li key={`bullet-${index}`}>{bullet}</li>
                  ))}
                </ul>
              </div>

              <div className="narration-card">
                <span className="eyebrow">Narration</span>
                <p className="narration-block">{recap.narration_15s}</p>
              </div>

              {recap.key_quotes.length > 0 ? (
                <div className="quote-stack">
                  <div className="section-heading">
                    <span className="eyebrow">Key quotes</span>
                    <h4>Jump back to spoken pressure</h4>
                  </div>
                  <div className="quote-grid">
                    {recap.key_quotes.map((quote) => (
                      <button
                        key={quote.event_id}
                        type="button"
                        className="quote-card"
                        onClick={() => handleClipClick(quote.event_id)}
                      >
                        <span className="quote-card-top">
                          <strong>{playerName(playerNameById, quote.player_id)}</strong>
                          <span className="meta-pill">Day {quote.day}</span>
                        </span>
                        <span className="quote-card-copy">{quote.text}</span>
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>

            <div className="recap-artifact-column">
              <div className="clip-stack">
                <div className="section-heading">
                  <span className="eyebrow">Clip list</span>
                  <h4>Jump to pivotal beats</h4>
                </div>

                <ol className="clip-list">
                  {recap.clips.map((clip) => (
                    <li key={clip.clip_id}>
                      <button
                        type="button"
                        className={`clip-card clip-card-${clip.kind}`}
                        onClick={() => handleClipClick(clip.start_event_id)}
                      >
                        <span className="clip-card-top">
                          <strong>{clip.title}</strong>
                          <span className={clipKindClass(clip.kind)}>{clip.kind}</span>
                        </span>
                        <span className="clip-card-copy">{clip.reason}</span>
                      </button>
                    </li>
                  ))}
                </ol>
              </div>

              <div className="share-card-frame">
                <div className="section-heading section-heading-row">
                  <div>
                    <span className="eyebrow">Share card</span>
                    <h4>Preview artifact</h4>
                  </div>
                  <a href={shareCardUrl} target="_blank" rel="noreferrer" className="button-link button-link-subtle">
                    Open image
                  </a>
                </div>

                <span className="meta-pill">{shareCardVisibility === "public" ? "Spoiler-safe public card" : "Spoiler reveal card"}</span>

                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  className="share-card"
                  src={shareCardUrl}
                  alt={`HowlHouse share card (${shareCardVisibility})`}
                />
              </div>
            </div>
          </div>
        ) : null}
      </section>
    </main>
  );
}
