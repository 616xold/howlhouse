"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { fetchJson } from "../lib/api";
import { getInitials } from "../lib/format";
import type { PredictionSummary, RosterEntry } from "../lib/types";

const VIEWER_STORAGE_KEY = "howlhouse_viewer_id";

function ensureViewerId(): string {
  const existing = window.localStorage.getItem(VIEWER_STORAGE_KEY);
  if (existing) {
    return existing;
  }
  const generated = window.crypto.randomUUID();
  window.localStorage.setItem(VIEWER_STORAGE_KEY, generated);
  return generated;
}

interface PredictionWidgetProps {
  matchId: string;
  roster: RosterEntry[];
  requiredWolves: number;
}

export function PredictionWidget({ matchId, roster, requiredWolves }: PredictionWidgetProps) {
  const [viewerId, setViewerId] = useState<string>("");
  const [selected, setSelected] = useState<string[]>([]);
  const [summary, setSummary] = useState<PredictionSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState<boolean>(false);

  useEffect(() => {
    setViewerId(ensureViewerId());
  }, []);

  const loadSummary = useCallback(async () => {
    try {
      const nextSummary = await fetchJson<PredictionSummary>(`/matches/${matchId}/predictions/summary`);
      setSummary(nextSummary);
    } catch {
      // Summary may not exist yet; keep quiet until first submit.
    }
  }, [matchId]);

  useEffect(() => {
    void loadSummary();
    const interval = setInterval(() => {
      void loadSummary();
    }, 5000);
    return () => clearInterval(interval);
  }, [loadSummary]);

  const togglePlayer = useCallback(
    (playerId: string) => {
      setSelected((prev) => {
        if (prev.includes(playerId)) {
          return prev.filter((id) => id !== playerId);
        }
        if (prev.length >= requiredWolves) {
          return prev;
        }
        return [...prev, playerId];
      });
    },
    [requiredWolves]
  );

  const submitPrediction = useCallback(async () => {
    setError(null);
    if (!viewerId) {
      setError("Viewer ID is not ready yet.");
      return;
    }
    if (selected.length !== requiredWolves) {
      setError(`Select exactly ${requiredWolves} players.`);
      return;
    }

    setSubmitting(true);
    try {
      const nextSummary = await fetchJson<PredictionSummary>(`/matches/${matchId}/predictions`, {
        method: "POST",
        body: JSON.stringify({ viewer_id: viewerId, wolves: selected })
      });
      setSummary(nextSummary);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to submit prediction");
    } finally {
      setSubmitting(false);
    }
  }, [matchId, requiredWolves, selected, viewerId]);

  const selectedCountLabel = useMemo(
    () => `${selected.length}/${requiredWolves} selected`,
    [requiredWolves, selected.length]
  );

  const maxVotes = useMemo(() => {
    if (!summary) {
      return 0;
    }
    return roster.reduce((max, entry) => Math.max(max, summary.by_player[entry.player_id] ?? 0), 0);
  }, [roster, summary]);

  return (
    <section className="panel prediction-panel">
      <div className="section-heading">
        <span className="eyebrow">Spectator pick</span>
        <h3>Who are the wolves?</h3>
        <p className="section-copy">Lock in your suspicion before the recap tells the story for you.</p>
      </div>

      <div className="prediction-topline">
        <span className="meta-pill meta-pill-accent">{selectedCountLabel}</span>
        <span className="mono-small">viewer_id {viewerId ? viewerId.slice(0, 8) : "loading"}</span>
      </div>

      <div className="prediction-option-grid">
        {roster.map((entry) => {
          const checked = selected.includes(entry.player_id);
          return (
            <button
              key={entry.player_id}
              type="button"
              className={checked ? "prediction-option prediction-option-active" : "prediction-option"}
              aria-pressed={checked}
              onClick={() => togglePlayer(entry.player_id)}
            >
              <span className="prediction-option-avatar">{getInitials(entry.name)}</span>
              <span className="prediction-option-copy">
                <strong>{entry.name}</strong>
                <span className="mono-small">{entry.player_id}</span>
              </span>
            </button>
          );
        })}
      </div>

      <button
        type="button"
        className="button-secondary button-wide"
        onClick={() => void submitPrediction()}
        disabled={submitting}
      >
        {submitting ? "Saving prediction..." : "Submit prediction"}
      </button>

      {error ? (
        <div className="message-inline message-inline-error" role="alert">
          {error}
        </div>
      ) : null}

      {summary ? (
        <div className="prediction-summary">
          <div className="summary-stat">
            <span className="summary-stat-label">Total predictions</span>
            <strong className="summary-stat-value">{summary.total_predictions}</strong>
          </div>

          <div className="crowd-board">
            {roster.map((entry) => {
              const votes = summary.by_player[entry.player_id] ?? 0;
              const width = maxVotes > 0 ? `${(votes / maxVotes) * 100}%` : "0%";

              return (
                <div key={entry.player_id} className="crowd-row">
                  <div className="crowd-row-head">
                    <span>{entry.name}</span>
                    <span>{votes}</span>
                  </div>
                  <div className="crowd-bar">
                    <div className="crowd-bar-fill" style={{ width }} />
                  </div>
                </div>
              );
            })}
          </div>

          <div>
            <strong className="summary-heading">Top wolf pairs</strong>
            <ul className="compact-list compact-list-tight">
              {summary.top_pairs.map((pairItem) => (
                <li key={`${pairItem.pair.join("-")}-${pairItem.count}`}>
                  <span>{pairItem.pair.join(" + ")}</span>
                  <span className="meta-pill">{pairItem.count}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}
    </section>
  );
}
