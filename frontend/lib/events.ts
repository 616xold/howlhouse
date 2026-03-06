import type { ReplayEvent } from "./types";

export function parseNdjson(text: string): ReplayEvent[] {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map((line) => JSON.parse(line) as ReplayEvent);
}
