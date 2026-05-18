import { useState } from "react";
import { getReport } from "../api";

function formatLookupError(err) {
  if (err.status === 404) {
    return { type: "warning", title: "Report not found", body: "No triage report exists for that patient ID." };
  }
  if (err instanceof TypeError) {
    return { type: "network", title: "Connection error", body: "Could not reach the server. Check your network and try again." };
  }
  const detail = err.detail;
  return {
    type: "error",
    title: `Error (${err.status ?? "unknown"})`,
    body: typeof detail === "string" ? detail : "An unexpected error occurred.",
  };
}

export default function ReportLookup({ onResult }) {
  const [patientId, setPatientId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function handleLookup(e) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const report = await getReport(patientId.trim());
      onResult(report);
    } catch (err) {
      setError(formatLookupError(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <form className="card lookup-card" onSubmit={handleLookup}>
      <h2 className="card-title">Lookup Report</h2>
      <div className="escalate-row">
        <input
          required
          value={patientId}
          onChange={(e) => setPatientId(e.target.value)}
          placeholder="Paste patient ID…"
        />
        <button className="btn btn-secondary" type="submit" disabled={loading}>
          {loading ? "Loading…" : "Fetch Report"}
        </button>
      </div>
      {error && (
        <div className={`alert-box alert-${error.type}`}>
          <strong>{error.title}</strong>
          {error.body && <p>{error.body}</p>}
        </div>
      )}
    </form>
  );
}