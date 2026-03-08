"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { apiUrl, getStoredIdentityToken, setStoredIdentityToken } from "../lib/api";

interface IdentityPayload {
  identity_id: string;
  handle: string | null;
  display_name: string | null;
  feed_url: string | null;
}

async function parseError(response: Response): Promise<string> {
  try {
    const data = await response.json();
    if (typeof data?.detail === "string") {
      return data.detail;
    }
    return JSON.stringify(data);
  } catch {
    return `${response.status} ${response.statusText}`;
  }
}

async function validateToken(token: string): Promise<IdentityPayload> {
  const response = await fetch(apiUrl("/identity/me"), {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`
    },
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as IdentityPayload;
}

export function AuthSessionBar() {
  const [tokenInput, setTokenInput] = useState<string>("");
  const [tokenStored, setTokenStored] = useState<boolean>(false);
  const [identity, setIdentity] = useState<IdentityPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<boolean>(false);
  const [expanded, setExpanded] = useState<boolean>(false);

  useEffect(() => {
    const existing = getStoredIdentityToken();
    if (!existing) {
      return;
    }
    setTokenStored(true);
    setBusy(true);
    void validateToken(existing)
      .then((payload) => {
        setIdentity(payload);
        setError(null);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Token validation failed");
      })
      .finally(() => {
        setBusy(false);
      });
  }, []);

  const handleValidate = useCallback(async () => {
    const token = tokenInput.trim();
    if (!token) {
      setError("Paste a token first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const payload = await validateToken(token);
      setStoredIdentityToken(token);
      setTokenStored(true);
      setIdentity(payload);
      setTokenInput("");
      setExpanded(false);
    } catch (err) {
      setIdentity(null);
      setTokenStored(false);
      setError(err instanceof Error ? err.message : "Token validation failed");
    } finally {
      setBusy(false);
    }
  }, [tokenInput]);

  const handleSignOut = useCallback(() => {
    setStoredIdentityToken(null);
    setIdentity(null);
    setTokenStored(false);
    setTokenInput("");
    setError(null);
  }, []);

  const identityLabel = useMemo(() => {
    if (!identity) {
      return busy ? "Checking token..." : "Guest viewer";
    }
    if (identity.display_name) {
      return identity.display_name;
    }
    if (identity.handle) {
      return `@${identity.handle}`;
    }
    return identity.identity_id;
  }, [busy, identity]);

  const identityMeta = useMemo(() => {
    if (!identity) {
      return tokenStored ? "Stored identity token" : "No verified token";
    }
    if (identity.handle) {
      return identity.identity_id;
    }
    return "Verified spectator";
  }, [identity, tokenStored]);

  return (
    <div className={expanded ? "auth-panel auth-panel-expanded" : "auth-panel"}>
      <div className="auth-summary">
        <div className="auth-copy">
          <span className="auth-label">Identity</span>
          <strong className="auth-value">{identityLabel}</strong>
          <span className="auth-meta">{identityMeta}</span>
        </div>

        {!tokenStored ? (
          <button
            type="button"
            className="button-secondary button-compact"
            onClick={() => setExpanded((value) => !value)}
          >
            {expanded ? "Close" : "Sign in"}
          </button>
        ) : (
          <button type="button" className="button-secondary button-compact" onClick={handleSignOut}>
            Sign out
          </button>
        )}
      </div>

      {expanded ? (
        <div className="auth-form">
          <input
            type="password"
            value={tokenInput}
            onChange={(event) => setTokenInput(event.target.value)}
            placeholder="Paste identity token"
            autoComplete="off"
          />
          <button type="button" className="button-primary" disabled={busy} onClick={() => void handleValidate()}>
            {busy ? "Validating..." : "Validate token"}
          </button>
        </div>
      ) : null}

      {error ? (
        <div className="message-inline message-inline-error" role="alert">
          {error}
        </div>
      ) : null}
    </div>
  );
}
