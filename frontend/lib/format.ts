export function formatDateTime(iso: string | null): string {
  if (!iso) {
    return "-";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit"
  });
}

export function formatRelativeTime(iso: string | null): string {
  if (!iso) {
    return "-";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }

  const diffMs = date.getTime() - Date.now();
  const diffSeconds = Math.round(diffMs / 1000);
  const absSeconds = Math.abs(diffSeconds);

  if (absSeconds < 60) {
    return diffSeconds >= 0 ? "in moments" : "just now";
  }

  const thresholds = [
    { limit: 60 * 60, unit: "minute", seconds: 60 },
    { limit: 60 * 60 * 24, unit: "hour", seconds: 60 * 60 },
    { limit: 60 * 60 * 24 * 30, unit: "day", seconds: 60 * 60 * 24 }
  ] as const;

  for (const threshold of thresholds) {
    if (absSeconds < threshold.limit) {
      const value = Math.round(diffSeconds / threshold.seconds);
      return new Intl.RelativeTimeFormat(undefined, { numeric: "auto" }).format(
        value,
        threshold.unit
      );
    }
  }

  const value = Math.round(diffSeconds / (60 * 60 * 24 * 30));
  return new Intl.RelativeTimeFormat(undefined, { numeric: "auto" }).format(value, "month");
}

export function formatStatusLabel(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  return value
    .replaceAll("_", " ")
    .split(" ")
    .filter(Boolean)
    .map((word) => word.slice(0, 1).toUpperCase() + word.slice(1))
    .join(" ");
}

export function formatShortId(value: string, head = 8, tail = 6): string {
  if (value.length <= head + tail + 1) {
    return value;
  }
  return `${value.slice(0, head)}...${value.slice(-tail)}`;
}

export function formatEventClock(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return date.toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit"
  });
}

export function getInitials(name: string): string {
  const tokens = name
    .split(/\s+/)
    .map((token) => token.trim())
    .filter(Boolean);

  if (tokens.length === 0) {
    return "?";
  }

  if (tokens.length === 1) {
    return tokens[0].slice(0, 2).toUpperCase();
  }

  return `${tokens[0][0] ?? ""}${tokens[1][0] ?? ""}`.toUpperCase();
}

export function summarizeText(value: string | null | undefined, fallback: string): string {
  const text = value?.trim();
  if (!text) {
    return fallback;
  }

  const normalized = text.replace(/\s+/g, " ");
  const [firstSentence] = normalized.split(/(?<=[.!?])\s+/);
  return firstSentence.length > 180 ? `${firstSentence.slice(0, 177)}...` : firstSentence;
}
