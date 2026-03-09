"use client";

import Link from "next/link";
import { DragEvent, FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { apiUrl, buildAuthHeaders, fetchJson } from "../lib/api";
import { formatDateTime, formatRelativeTime, formatShortId, summarizeText } from "../lib/format";
import type { PublicAgentRecord } from "../lib/types";

const ENABLE_UNSAFE_LOCAL_AGENT_RUNTIME =
  process.env.NEXT_PUBLIC_ENABLE_UNSAFE_LOCAL_AGENT_RUNTIME === "true";

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") {
      return body.detail;
    }
    return JSON.stringify(body);
  } catch {
    return `${response.status} ${response.statusText}`;
  }
}

function visibilityLabel(agent: PublicAgentRecord): string {
  return agent.hidden_at ? "Hidden" : "Visible";
}

function visibilityClass(agent: PublicAgentRecord): string {
  return agent.hidden_at ? "meta-pill meta-pill-danger" : "meta-pill meta-pill-success";
}

export function AgentsClient() {
  const [agents, setAgents] = useState<PublicAgentRecord[]>([]);
  const [name, setName] = useState<string>("My Agent");
  const [version, setVersion] = useState<string>("0.1.0");
  const [runtimeType, setRuntimeType] = useState<"docker_py_v1" | "local_py_v1">("docker_py_v1");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [uploading, setUploading] = useState<boolean>(false);
  const [loadingAgents, setLoadingAgents] = useState<boolean>(true);
  const [dragActive, setDragActive] = useState<boolean>(false);
  const [search, setSearch] = useState<string>("");
  const [runtimeFilter, setRuntimeFilter] = useState<string>("all");
  const [sortBy, setSortBy] = useState<"newest" | "oldest" | "name">("newest");

  const fetchAgents = useCallback(async () => {
    try {
      const data = await fetchJson<PublicAgentRecord[]>("/agents");
      setAgents(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load agents");
    } finally {
      setLoadingAgents(false);
    }
  }, []);

  useEffect(() => {
    void fetchAgents();
  }, [fetchAgents]);

  const applyFile = useCallback((file: File | null) => {
    if (!file) {
      return;
    }
    if (!file.name.toLowerCase().endsWith(".zip")) {
      setError("Only ZIP packages are supported.");
      return;
    }
    setSelectedFile(file);
    setError(null);
  }, []);

  const onDrop = useCallback(
    (event: DragEvent<HTMLLabelElement>) => {
      event.preventDefault();
      setDragActive(false);
      applyFile(event.dataTransfer.files?.[0] ?? null);
    },
    [applyFile]
  );

  const submit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      setError(null);
      setSuccessMessage(null);
      if (!selectedFile) {
        setError("Choose a ZIP file before uploading.");
        return;
      }

      const formData = new FormData();
      formData.set("name", name);
      formData.set("version", version);
      formData.set("runtime_type", runtimeType);
      formData.set("file", selectedFile, selectedFile.name);

      setUploading(true);
      try {
        const response = await fetch(apiUrl("/agents"), {
          method: "POST",
          body: formData,
          headers: buildAuthHeaders()
        });
        if (!response.ok) {
          throw new Error(await readError(response));
        }
        await fetchAgents();
        setSelectedFile(null);
        setSuccessMessage("Agent uploaded and catalog refreshed.");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Upload failed");
      } finally {
        setUploading(false);
      }
    },
    [fetchAgents, name, runtimeType, selectedFile, version]
  );

  const filteredAgents = useMemo(() => {
    const query = search.trim().toLowerCase();
    const next = agents.filter((agent) => {
      const matchesQuery =
        query.length === 0 ||
        agent.name.toLowerCase().includes(query) ||
        agent.version.toLowerCase().includes(query) ||
        agent.runtime_type.toLowerCase().includes(query) ||
        (agent.strategy_text ?? "").toLowerCase().includes(query);

      const matchesRuntime = runtimeFilter === "all" || agent.runtime_type === runtimeFilter;
      return matchesQuery && matchesRuntime;
    });

    next.sort((left, right) => {
      if (sortBy === "name") {
        return left.name.localeCompare(right.name);
      }
      const leftTime = new Date(left.created_at).getTime();
      const rightTime = new Date(right.created_at).getTime();
      return sortBy === "oldest" ? leftTime - rightTime : rightTime - leftTime;
    });

    return next;
  }, [agents, runtimeFilter, search, sortBy]);
  const visibleAgentCount = useMemo(
    () => agents.filter((agent) => agent.hidden_at === null).length,
    [agents]
  );
  const productionSafeCount = useMemo(
    () => agents.filter((agent) => agent.runtime_type === "docker_py_v1").length,
    [agents]
  );
  const strategyProfileCount = useMemo(
    () => agents.filter((agent) => (agent.strategy_text ?? "").trim().length > 0).length,
    [agents]
  );

  return (
    <main className="page-shell page-stack">
      <section className="page-banner agents-banner">
        <div className="section-heading">
          <p className="breadcrumb">
            <Link href="/">Matches</Link>
            <span>/</span>
            <span>Agents</span>
          </p>
          <span className="eyebrow">Creator roster</span>
          <h1>Build a catalog that looks like a field guide, not a registry.</h1>
          <p className="section-copy">
            Registered agents should read like collectible competitors. Search strategies quickly, scan runtime
            posture at a glance, and keep uploads tucked into the workshop instead of the spotlight.
          </p>
        </div>

        <div className="metrics-grid metrics-grid-compact">
          <article className="stat-card">
            <span className="stat-label">Registered agents</span>
            <strong className="stat-value">{agents.length}</strong>
            <span className="stat-meta">{visibleAgentCount} visible for new tables</span>
          </article>
          <article className="stat-card">
            <span className="stat-label">Launch-safe packages</span>
            <strong className="stat-value">{productionSafeCount}</strong>
            <span className="stat-meta">Catalog entries backed by docker_py_v1</span>
          </article>
          <article className="stat-card">
            <span className="stat-label">Strategy dossiers</span>
            <strong className="stat-value">{strategyProfileCount}</strong>
            <span className="stat-meta">Summaries extracted from AGENT.md</span>
          </article>
        </div>
      </section>

      <section className="split-layout catalog-command">
        <section className="panel panel-strong catalog-command-main">
          <div className="section-heading section-heading-row">
            <div>
              <span className="eyebrow">Browse roster</span>
              <h2>Registered agents</h2>
              <p className="section-copy">
                Filter by runtime, inspect strategy summaries, and pick the next agent you want in a spectator-facing match.
              </p>
            </div>
            <span className="meta-pill meta-pill-accent">{filteredAgents.length} visible card(s)</span>
          </div>

          <div className="toolbar-grid">
            <label className="field field-search">
              <span className="field-label">Search</span>
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Name, version, runtime, or strategy"
              />
            </label>
            <label className="field">
              <span className="field-label">Runtime</span>
              <select value={runtimeFilter} onChange={(event) => setRuntimeFilter(event.target.value)}>
                <option value="all">All runtimes</option>
                <option value="docker_py_v1">docker_py_v1</option>
                {ENABLE_UNSAFE_LOCAL_AGENT_RUNTIME ? <option value="local_py_v1">local_py_v1</option> : null}
              </select>
            </label>
            <label className="field">
              <span className="field-label">Sort</span>
              <select value={sortBy} onChange={(event) => setSortBy(event.target.value as "newest" | "oldest" | "name")}>
                <option value="newest">Newest first</option>
                <option value="oldest">Oldest first</option>
                <option value="name">Name</option>
              </select>
            </label>
          </div>

          <p className="muted">
            BYA match creation uses the same inventory you see here, so runtime posture and visibility stay
            legible before anything goes on air.
          </p>

          {loadingAgents ? (
            <div className="catalog-grid">
              {Array.from({ length: 4 }, (_, index) => (
                <article key={`agent-skeleton-${index}`} className="agent-card skeleton-card">
                  <div className="skeleton-line skeleton-line-short" />
                  <div className="skeleton-line" />
                  <div className="skeleton-line" />
                  <div className="skeleton-line skeleton-line-short" />
                </article>
              ))}
            </div>
          ) : null}

          {!loadingAgents && filteredAgents.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-art" aria-hidden="true" />
              <div>
                <h3>No agents matched</h3>
                <p className="muted">
                  Adjust the filters or ship a new package from the workshop to expand the roster.
                </p>
              </div>
            </div>
          ) : null}

          {!loadingAgents && filteredAgents.length > 0 ? (
            <div className="catalog-grid">
              {filteredAgents.map((agent) => (
                <article key={agent.agent_id} className="agent-card agent-card-collectible">
                  <div className="agent-card-top">
                    <div className="agent-card-heading">
                      <span className="agent-sigil" aria-hidden="true">
                        {agent.name.slice(0, 1).toUpperCase()}
                      </span>
                      <div>
                        <h3>{agent.name}</h3>
                        <p className="mono-small">{formatShortId(agent.agent_id, 10, 8)}</p>
                      </div>
                    </div>
                    <div className="agent-card-badges">
                      <span className="meta-pill">{agent.version}</span>
                      <span className={visibilityClass(agent)}>{visibilityLabel(agent)}</span>
                    </div>
                  </div>

                  <p className="agent-card-summary">
                    {summarizeText(agent.strategy_text, "No strategy summary was provided in the uploaded AGENT.md file.")}
                  </p>

                  <dl className="detail-grid detail-grid-compact">
                    <div>
                      <dt>Runtime</dt>
                      <dd>{agent.runtime_type}</dd>
                    </div>
                    <div>
                      <dt>Updated</dt>
                      <dd>{formatRelativeTime(agent.updated_at)}</dd>
                    </div>
                    <div>
                      <dt>Isolation</dt>
                      <dd>{agent.runtime_type === "docker_py_v1" ? "Container sandbox" : "Development runtime"}</dd>
                    </div>
                    <div>
                      <dt>Created</dt>
                      <dd>{formatDateTime(agent.created_at)}</dd>
                    </div>
                  </dl>

                  <div className="agent-card-footer">
                    <Link href={`/agents/${agent.agent_id}`} className="button-link">
                      Open profile
                    </Link>
                  </div>
                </article>
              ))}
            </div>
          ) : null}
        </section>

        <aside className="panel upload-panel">
          <div className="section-heading">
            <span className="eyebrow">Workshop</span>
            <h2>Ship a new strategy package</h2>
            <p className="section-copy">
              Upload a ZIP containing <code>agent.py</code> and an <code>AGENT.md</code> file with a
              <code>HowlHouse Strategy</code> section.
            </p>
          </div>

          {!ENABLE_UNSAFE_LOCAL_AGENT_RUNTIME ? (
            <div className="message-inline">
              <strong>Runtime policy</strong>
              <span className="muted">
                <code>local_py_v1</code> stays hidden unless the explicit unsafe dev flag is enabled.
              </span>
            </div>
          ) : null}

          <form className="form-grid" onSubmit={submit}>
            <div className="form-row">
              <label className="field">
                <span className="field-label">Name</span>
                <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Name" />
              </label>
              <label className="field">
                <span className="field-label">Version</span>
                <input
                  value={version}
                  onChange={(event) => setVersion(event.target.value)}
                  placeholder="Version"
                />
              </label>
            </div>

            <label className="field">
              <span className="field-label">Runtime</span>
              <select
                value={runtimeType}
                onChange={(event) =>
                  setRuntimeType(event.target.value as "docker_py_v1" | "local_py_v1")
                }
              >
                <option value="docker_py_v1">docker_py_v1</option>
                {ENABLE_UNSAFE_LOCAL_AGENT_RUNTIME ? (
                  <option value="local_py_v1">local_py_v1</option>
                ) : null}
              </select>
            </label>

            <label
              htmlFor="agent-zip-input"
              className={dragActive ? "dropzone dropzone-active" : "dropzone"}
              onDragEnter={() => setDragActive(true)}
              onDragOver={(event) => {
                event.preventDefault();
                setDragActive(true);
              }}
              onDragLeave={() => setDragActive(false)}
              onDrop={onDrop}
            >
              <input
                id="agent-zip-input"
                type="file"
                accept=".zip,application/zip"
                onChange={(event) => applyFile(event.target.files?.[0] ?? null)}
                className="visually-hidden"
              />
              <span className="dropzone-title">Drag a ZIP here or choose a file</span>
              <span className="dropzone-copy">Single archive, no extra directories required.</span>
              <span className="dropzone-file">
                {selectedFile ? `${selectedFile.name} · ${(selectedFile.size / 1024).toFixed(1)} KB` : "No file selected"}
              </span>
            </label>

            <button type="submit" className="button-primary button-wide" disabled={uploading}>
              {uploading ? "Uploading..." : "Upload agent"}
            </button>
          </form>

          {error ? (
            <div className="message-banner message-banner-error" role="alert">
              {error}
            </div>
          ) : null}
          {successMessage ? <div className="message-banner">{successMessage}</div> : null}
        </aside>
      </section>
    </main>
  );
}
