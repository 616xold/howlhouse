"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { fetchJson } from "../lib/api";
import type { PublicAgentRecord, PublicMatchRecord } from "../lib/types";

function randomSeed(): number {
  return Math.floor(Math.random() * 1_000_000_000);
}

function formatIso(iso: string | null): string {
  if (!iso) {
    return "-";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return date.toLocaleString();
}

export function MatchListClient() {
  const [matches, setMatches] = useState<PublicMatchRecord[]>([]);
  const [agents, setAgents] = useState<PublicAgentRecord[]>([]);
  const [seed, setSeed] = useState<number>(randomSeed);
  const [createMode, setCreateMode] = useState<"scripted" | "bring">("scripted");
  const [selectedAgentId, setSelectedAgentId] = useState<string>("");
  const [createError, setCreateError] = useState<string | null>(null);
  const [runPending, setRunPending] = useState<Set<string>>(new Set());

  const fetchMatches = useCallback(async () => {
    try {
      const data = await fetchJson<PublicMatchRecord[]>("/matches");
      setMatches(data);
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Failed to fetch matches");
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
    }
  }, [selectedAgentId]);

  useEffect(() => {
    fetchMatches();
    fetchAgents();
    const interval = setInterval(fetchMatches, 3000);
    return () => clearInterval(interval);
  }, [fetchAgents, fetchMatches]);

  const selectedAgent = useMemo(
    () => agents.find((agent) => agent.agent_id === selectedAgentId) ?? null,
    [agents, selectedAgentId]
  );

  const submitCreate = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      setCreateError(null);
      try {
        const body: Record<string, unknown> = { seed, agent_set: "scripted" };
        if (createMode === "bring") {
          if (!selectedAgent) {
            throw new Error("Select an agent before creating a BYA match");
          }
          const roster = [
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
          body.roster = roster;
        }

        await fetchJson<PublicMatchRecord>("/matches", {
          method: "POST",
          body: JSON.stringify(body)
        });
        setSeed(randomSeed());
        fetchMatches();
      } catch (err) {
        setCreateError(err instanceof Error ? err.message : "Failed to create match");
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
        fetchMatches();
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

  const hasMatches = matches.length > 0;
  const runningCount = useMemo(
    () => matches.filter((match) => match.status === "running").length,
    [matches]
  );

  return (
    <main className="page-shell">
      <section className="card">
        <h1>HowlHouse Spectator Console</h1>
        <p className="muted">Create deterministic matches, run them, and open the live viewer.</p>
        <p className="muted">
          Need to upload an agent first? <Link href="/agents">Open Agent Registry</Link>
        </p>
        <p className="muted">
          Looking for seasons and brackets? <Link href="/league">Open League Mode</Link>
        </p>

        <form className="create-form" onSubmit={submitCreate}>
          <label htmlFor="seed-input">Seed</label>
          <input
            id="seed-input"
            type="number"
            value={seed}
            onChange={(event) => setSeed(Number(event.target.value))}
          />
          <select
            value={createMode}
            onChange={(event) => setCreateMode(event.target.value as "scripted" | "bring")}
          >
            <option value="scripted">All scripted</option>
            <option value="bring">Bring Your Agent</option>
          </select>
          {createMode === "bring" ? (
            <select
              value={selectedAgentId}
              onChange={(event) => setSelectedAgentId(event.target.value)}
            >
              {agents.length === 0 ? <option value="">No agents available</option> : null}
              {agents.map((agent) => (
                <option key={agent.agent_id} value={agent.agent_id}>
                  {agent.name} ({agent.version})
                </option>
              ))}
            </select>
          ) : null}
          <button type="submit">Create Match</button>
        </form>

        {createError ? <p className="error-text">{createError}</p> : null}
        {runningCount > 0 ? (
          <p className="muted">{runningCount} match(es) currently running. List auto-refreshes.</p>
        ) : null}
      </section>

      <section className="card">
        <h2>Matches</h2>
        {!hasMatches ? <p className="muted">No matches yet. Create one above.</p> : null}

        {hasMatches ? (
          <div className="table-wrap">
            <table className="matches-table">
              <thead>
                <tr>
                  <th>Match ID</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th>Winner</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {matches.map((match) => {
                  const canRun = match.status === "created" || match.status === "failed";
                  const pending = runPending.has(match.match_id);
                  return (
                    <tr key={match.match_id}>
                      <td>
                        <Link href={`/matches/${match.match_id}`}>{match.match_id}</Link>
                      </td>
                      <td>{match.status}</td>
                      <td>{formatIso(match.created_at)}</td>
                      <td>{match.winner ?? "-"}</td>
                      <td className="actions-cell">
                        <Link href={`/matches/${match.match_id}`}>Open</Link>
                        {canRun ? (
                          <button
                            type="button"
                            className="secondary-btn"
                            disabled={pending}
                            onClick={() => runMatch(match.match_id)}
                          >
                            {pending ? "Running..." : "Run"}
                          </button>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </main>
  );
}
