import { useEffect, useState } from "react";
import { apiBaseUrl } from "./config";

type HealthResponse = {
  status: string;
  app_name: string;
  app_version: string;
  frontend_origin: string;
  capwages_configured: boolean;
};

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadHealth() {
      try {
        const response = await fetch(`${apiBaseUrl}/api/health`);
        if (!response.ok) {
          throw new Error(`Healthcheck failed with ${response.status}.`);
        }

        const payload = (await response.json()) as HealthResponse;
        if (!cancelled) {
          setHealth(payload);
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "Unknown error.");
        }
      }
    }

    void loadHealth();

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="app-shell">
      <section className="hero">
        <p className="eyebrow">HockeyOps AI v0.5</p>
        <h1>Phase 1 application shell</h1>
        <p className="lede">
          This pass sets up the React and FastAPI foundations only. No NHL API, CapWages client,
          tool layer, or model orchestration is included yet.
        </p>
      </section>

      <section className="panel">
        <h2>Backend Connection</h2>
        <p className="meta">Configured API base: {apiBaseUrl}</p>
        {health ? (
          <dl className="status-grid">
            <div>
              <dt>Status</dt>
              <dd>{health.status}</dd>
            </div>
            <div>
              <dt>Backend</dt>
              <dd>{health.app_name}</dd>
            </div>
            <div>
              <dt>Version</dt>
              <dd>{health.app_version}</dd>
            </div>
            <div>
              <dt>CapWages Key</dt>
              <dd>{health.capwages_configured ? "Configured" : "Not configured"}</dd>
            </div>
          </dl>
        ) : null}
        {error ? <p className="error">{error}</p> : null}
      </section>

      <section className="panel">
        <h2>Phase Boundary</h2>
        <ul>
          <li>Included: project shells, settings, startup path, health check.</li>
          <li>Excluded: source clients, identity matching, tools, prompts, LLM integration.</li>
        </ul>
      </section>
    </main>
  );
}
