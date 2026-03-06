"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { apiUrl, fetchText } from "./api";
import { parseNdjson } from "./events";
import type { MatchEventMode, ReplayEvent, VisibilityMode } from "./types";

interface UseMatchEventsResult {
  events: ReplayEvent[];
  isLoading: boolean;
  error: string | null;
}

export function useMatchEvents(
  matchId: string,
  visibility: VisibilityMode,
  mode: MatchEventMode
): UseMatchEventsResult {
  const [events, setEvents] = useState<ReplayEvent[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const seenEventIdsRef = useRef<Set<string>>(new Set());
  const hasEndedRef = useRef<boolean>(false);

  const appendEvent = useCallback((event: ReplayEvent) => {
    if (seenEventIdsRef.current.has(event.id)) {
      return;
    }
    seenEventIdsRef.current.add(event.id);
    setEvents((prev) => [...prev, event]);
  }, []);

  const resetState = useCallback(() => {
    seenEventIdsRef.current = new Set();
    hasEndedRef.current = false;
    setEvents([]);
    setIsLoading(true);
    setError(null);
  }, []);

  useEffect(() => {
    let closed = false;
    let source: EventSource | null = null;
    let retryHandle: ReturnType<typeof setTimeout> | null = null;

    resetState();

    async function loadReplay() {
      try {
        const text = await fetchText(`/matches/${matchId}/replay?visibility=${visibility}`);
        if (closed) {
          return;
        }
        for (const event of parseNdjson(text)) {
          appendEvent(event);
        }
        setIsLoading(false);
      } catch (err) {
        if (closed) {
          return;
        }
        setError(err instanceof Error ? err.message : "Failed to load replay");
        setIsLoading(false);
      }
    }

    function connectLiveStream() {
      source = new EventSource(apiUrl(`/matches/${matchId}/events?visibility=${visibility}`));
      source.onopen = () => {
        if (!closed) {
          setIsLoading(false);
          setError(null);
        }
      };
      source.onmessage = (message) => {
        if (closed) {
          return;
        }
        try {
          const event = JSON.parse(message.data) as ReplayEvent;
          appendEvent(event);
          if (event.type === "match_ended") {
            hasEndedRef.current = true;
            if (source) {
              source.close();
              source = null;
            }
          }
        } catch {
          setError("Received malformed event stream payload");
        }
      };
      source.onerror = () => {
        if (source) {
          source.close();
          source = null;
        }
        if (closed) {
          return;
        }
        if (hasEndedRef.current) {
          return;
        }
        setError("Stream disconnected. Reconnecting...");
        retryHandle = setTimeout(connectLiveStream, 1000);
      };
    }

    if (mode === "replay") {
      loadReplay();
    } else {
      connectLiveStream();
    }

    return () => {
      closed = true;
      if (source) {
        source.close();
      }
      if (retryHandle) {
        clearTimeout(retryHandle);
      }
    };
  }, [appendEvent, matchId, mode, resetState, visibility]);

  return useMemo(
    () => ({
      events,
      isLoading,
      error
    }),
    [error, events, isLoading]
  );
}
