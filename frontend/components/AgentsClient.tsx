"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { apiUrl, buildAuthHeaders, fetchJson } from "../lib/api";
import type { AgentRecord } from "../lib/types";

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

export function AgentsClient() {
  const [agents, setAgents] = useState<AgentRecord[]>([]);
  const [name, setName] = useState<string>("My Agent");
  const [version, setVersion] = useState<string>("0.1.0");
  const [runtimeType, setRuntimeType] = useState<"docker_py_v1" | "local_py_v1">("docker_py_v1");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState<boolean>(false);

  const fetchAgents = useCallback(async () => {
    try {
      const data = await fetchJson<AgentRecord[]>("/agents");
      setAgents(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load agents");
    }
  }, []);

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  const submit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      setError(null);
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
      } catch (err) {
        setError(err instanceof Error ? err.message : "Upload failed");
      } finally {
        setUploading(false);
      }
    },
    [fetchAgents, name, runtimeType, selectedFile, version]
  );

  return (
    <main className="page-shell">
      <section className="card">
        <p className="muted">
          <Link href="/">← Back to matches</Link>
        </p>
        <h1>Agent Registry</h1>
        <p className="muted">Upload ZIP packages containing agent.py and AGENT.md.</p>

        <form className="create-form" onSubmit={submit}>
          <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Name" />
          <input
            value={version}
            onChange={(event) => setVersion(event.target.value)}
            placeholder="Version"
          />
          <select
            value={runtimeType}
            onChange={(event) => setRuntimeType(event.target.value as "docker_py_v1" | "local_py_v1")}
          >
            <option value="docker_py_v1">docker_py_v1</option>
            <option value="local_py_v1">local_py_v1</option>
          </select>
          <input
            type="file"
            accept=".zip,application/zip"
            onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
          />
          <button type="submit" disabled={uploading}>
            {uploading ? "Uploading..." : "Upload Agent"}
          </button>
        </form>

        {error ? <p className="error-text">{error}</p> : null}
      </section>

      <section className="card">
        <h2>Registered Agents</h2>
        {agents.length === 0 ? <p className="muted">No agents registered yet.</p> : null}

        {agents.length > 0 ? (
          <div className="table-wrap">
            <table className="matches-table">
              <thead>
                <tr>
                  <th>Agent ID</th>
                  <th>Name</th>
                  <th>Version</th>
                  <th>Runtime</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {agents.map((agent) => (
                  <tr key={agent.agent_id}>
                    <td className="mono-small">{agent.agent_id}</td>
                    <td>{agent.name}</td>
                    <td>{agent.version}</td>
                    <td>{agent.runtime_type}</td>
                    <td>
                      <Link href={`/agents/${agent.agent_id}`}>Open</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </main>
  );
}
