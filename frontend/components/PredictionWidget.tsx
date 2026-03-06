"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { fetchJson } from "../lib/api";
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
    loadSummary();
    const interval = setInterval(loadSummary, 5000);
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

  return (
    <section className="sidebar-card">
      <h3>Prediction Widget</h3>
      <p className="muted">Choose who you think the wolves are.</p>
      <p className="mono-small">viewer_id: {viewerId || "loading"}</p>
      <p className="muted">{selectedCountLabel}</p>

      <div className="prediction-grid">
        {roster.map((entry) => {
          const checked = selected.includes(entry.player_id);
          return (
            <label key={entry.player_id} className="checkbox-row">
              <input
                type="checkbox"
                checked={checked}
                onChange={() => togglePlayer(entry.player_id)}
              />
              <span>
                {entry.name} ({entry.player_id})
              </span>
            </label>
          );
        })}
      </div>

      <button type="button" className="secondary-btn" onClick={submitPrediction} disabled={submitting}>
        {submitting ? "Saving..." : "Submit Prediction"}
      </button>

      {error ? <p className="error-text">{error}</p> : null}

      {summary ? (
        <div className="summary-block">
          <h4>Summary</h4>
          <p>Total predictions: {summary.total_predictions}</p>
          <div>
            <strong>By player</strong>
            <ul className="compact-list">
              {roster.map((entry) => (
                <li key={entry.player_id}>
                  {entry.player_id}: {summary.by_player[entry.player_id] ?? 0}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <strong>Top pairs</strong>
            <ul className="compact-list">
              {summary.top_pairs.map((pairItem) => (
                <li key={`${pairItem.pair.join("-")}-${pairItem.count}`}>
                  {pairItem.pair.join(" + ")}: {pairItem.count}
                </li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}
    </section>
  );
}
