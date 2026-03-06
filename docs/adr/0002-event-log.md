# ADR 0002: Event-sourced match log

Decision: the canonical output of a match is an append-only JSONL event log.
All UI, recaps, clips, and analytics derive from the event stream.

Status: Accepted
