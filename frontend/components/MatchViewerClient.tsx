"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { apiUrl, fetchJson } from "../lib/api";
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
  const phase = phaseRaw.replaceAll("_", " ");
  const round = roundRaw ? ` (${roundRaw})` : "";
  return `Day ${day} · ${phase}${round}`;
}

function withHighlightClass(baseClass: string, eventId: string, highlightedEventId: string | null): string {
  return highlightedEventId === eventId ? `${baseClass} event-highlight` : baseClass;
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
    fetchMatch();
    const interval = setInterval(fetchMatch, 3000);
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

  const renderPlayerName = useCallback(
    (playerId: string): string => {
      return playerNameById.get(playerId) ?? playerId;
    },
    [playerNameById]
  );

  const canRun = match?.status === "created" || match?.status === "failed";

  const runMatch = useCallback(async () => {
      setRunningRequest(true);
      setActionError(null);
      try {
        await fetchJson<PublicMatchRecord>(`/matches/${matchId}/run?sync=false`, {
          method: "POST"
        });
      setMode("live");
      fetchMatch();
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

  return (
    <main className="page-shell viewer-shell">
      <section className="card viewer-main">
        <header className="viewer-header">
          <div>
            <p className="muted">
              <Link href="/">← Back to matches</Link>
            </p>
            <h1>{matchId}</h1>
            <p className="muted">
              status: {match?.status ?? "loading"} · winner: {match?.winner ?? "-"}
            </p>
          </div>
          <div className="toolbar-group">
            <div className="toolbar-row">
              <button
                type="button"
                className={mode === "live" ? "active-btn" : "secondary-btn"}
                onClick={() => setMode("live")}
              >
                Live
              </button>
              <button
                type="button"
                className={mode === "replay" ? "active-btn" : "secondary-btn"}
                onClick={() => setMode("replay")}
              >
                Replay
              </button>
            </div>
            <div className="toolbar-row">
              <button
                type="button"
                className={visibility === "public" ? "active-btn" : "secondary-btn"}
                onClick={() => setVisibility("public")}
              >
                Mystery
              </button>
              <button
                type="button"
                className={visibility === "spoilers" ? "active-btn" : "secondary-btn"}
                onClick={() => setVisibility("spoilers")}
              >
                Dramatic Irony
              </button>
            </div>
            {canRun ? (
              <button type="button" onClick={runMatch} disabled={runningRequest}>
                {runningRequest ? "Starting..." : "Run Match"}
              </button>
            ) : null}
          </div>
        </header>

        {actionError ? <p className="error-text">{actionError}</p> : null}
        {eventsError ? <p className="error-text">{eventsError}</p> : null}
        {isLoading ? <p className="muted">Loading {mode} events...</p> : null}

        <ol className="transcript-list">
          {events.map((event: ReplayEvent) => {
            const payload = asRecord(event.payload);
            if (event.type === "phase_started") {
              const phase = asString(payload.phase, event.type);
              const day = asNumber(payload.day, 0);
              const round = asString(payload.round);
              return (
                <li id={event.id} key={event.id} className="phase-marker">
                  {formatPhaseLabel(phase, day, round)}
                </li>
              );
            }

            if (event.type === "public_message") {
              const playerId = asString(payload.player_id);
              const text = asString(payload.text);
              return (
                <li
                  id={event.id}
                  key={event.id}
                  className={withHighlightClass("event-row", event.id, highlightedEventId)}
                >
                  <strong>{renderPlayerName(playerId)}</strong>: <span>{text}</span>
                </li>
              );
            }

            if (event.type === "player_killed" || event.type === "player_eliminated") {
              const playerId = asString(payload.player_id);
              const verb = event.type === "player_killed" ? "was killed" : "was eliminated";
              return (
                <li
                  id={event.id}
                  key={event.id}
                  className={withHighlightClass("event-notice", event.id, highlightedEventId)}
                >
                  {renderPlayerName(playerId)} {verb}.
                </li>
              );
            }

            if (event.type === "vote_result") {
              const eliminated = asString(payload.eliminated);
              const tally = asRecord(payload.tally);
              const tallyText = Object.entries(tally)
                .sort(([a], [b]) => a.localeCompare(b))
                .map(([playerId, votesValue]) => `${playerId}:${String(votesValue)}`)
                .join(" ");
              return (
                <li
                  id={event.id}
                  key={event.id}
                  className={withHighlightClass("event-row", event.id, highlightedEventId)}
                >
                  Vote result: eliminated {renderPlayerName(eliminated)} | tally {tallyText}
                </li>
              );
            }

            if (event.type === "match_ended") {
              const winningTeam = asString(payload.winning_team);
              const reason = asString(payload.reason);
              return (
                <li id={event.id} key={event.id} className="winner-banner">
                  Winner: {winningTeam} ({reason})
                </li>
              );
            }

            if (event.type === "roles_assigned") {
              return (
                <li
                  id={event.id}
                  key={event.id}
                  className={withHighlightClass("event-row muted", event.id, highlightedEventId)}
                >
                  Roles assigned (spoiler data loaded).
                </li>
              );
            }

            return null;
          })}
        </ol>
      </section>

      <aside className="viewer-sidebar">
        <section className="sidebar-card">
          <h3>Roster</h3>
          <ul className="compact-list">
            {roster.map((entry) => {
              const alive = aliveSet.has(entry.player_id);
              const role = rolesByPlayer[entry.player_id];
              return (
                <li key={entry.player_id}>
                  <span>{entry.name}</span>
                  <span className={alive ? "alive-badge" : "dead-badge"}>
                    {alive ? "alive" : "dead"}
                  </span>
                  {visibility !== "public" && role ? <span className="role-pill">{role}</span> : null}
                </li>
              );
            })}
          </ul>
        </section>

        <PredictionWidget matchId={matchId} roster={roster} requiredWolves={requiredWolves} />

        {match?.status === "finished" ? (
          <section className="sidebar-card town-crier-panel">
            <h3>Town Crier</h3>
            {recapError ? <p className="error-text">{recapError}</p> : null}
            {!recap && !recapError ? <p className="muted">Recap is generating...</p> : null}
            {recap ? (
              <>
                <ul className="bullet-list">
                  {recap.bullets.map((bullet, index) => (
                    <li key={`bullet-${index}`}>{bullet}</li>
                  ))}
                </ul>

                <pre className="narration-block">{recap.narration_15s}</pre>

                <div>
                  <h4>Clips</h4>
                  <ol className="clip-list">
                    {recap.clips.map((clip) => (
                      <li key={clip.clip_id}>
                        <button
                          type="button"
                          className="clip-btn"
                          onClick={() => handleClipClick(clip.start_event_id)}
                        >
                          {clip.title} ({clip.kind}) · score {clip.score}
                          <br />
                          <span className="muted">{clip.reason}</span>
                        </button>
                      </li>
                    ))}
                  </ol>
                </div>

                <div>
                  <h4>Share Card</h4>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    className="share-card"
                    src={shareCardUrl}
                    alt={`HowlHouse share card (${shareCardVisibility})`}
                  />
                  <p className="muted">
                    <a href={shareCardUrl} target="_blank" rel="noreferrer">
                      Open image
                    </a>
                  </p>
                </div>
              </>
            ) : null}
          </section>
        ) : null}
      </aside>
    </main>
  );
}
