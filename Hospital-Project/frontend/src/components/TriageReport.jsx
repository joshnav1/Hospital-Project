import { useState } from "react";
import { escalatePatient } from "../api";

const LEVEL_COLOR = {
  EMERGENCY: "level-emergency",
  URGENT: "level-urgent",
  STANDARD: "level-standard",
  SELF_CARE: "level-self-care",
};

const LEVEL_LABEL = {
  EMERGENCY: "EMERGENCY",
  URGENT: "URGENT",
  STANDARD: "STANDARD",
  SELF_CARE: "SELF-CARE",
};

export default function TriageReport({ report, onUpdated }) {
  const [reason, setReason] = useState("");
  const [escalating, setEscalating] = useState(false);
  const [escalateError, setEscalateError] = useState(null);

  async function handleEscalate() {
    setEscalateError(null);
    setEscalating(true);
    try {
      await escalatePatient(report.patient_id, reason || "Manual escalation by clinical staff");
      onUpdated(report.patient_id);
    } catch (err) {
      if (err instanceof TypeError) {
        setEscalateError("Connection error — could not reach the server.");
      } else if (err.status === 404) {
        setEscalateError("Patient report not found. It may have been removed.");
      } else {
        const detail = err.detail;
        setEscalateError(typeof detail === "string" ? detail : `Escalation failed (${err.status ?? "unknown error"}).`);
      }
    } finally {
      setEscalating(false);
    }
  }

  const levelClass = LEVEL_COLOR[report.triage_level] ?? "level-standard";

  return (
    <div className="card report-card">
      {/* Header */}
      <div className="report-header">
        <div>
          <h2 className="card-title">{report.patient_name}</h2>
          <p className="report-meta">
            {report.age} yrs · {report.gender} · ID: <code>{report.patient_id}</code>
          </p>
        </div>
        <span className={`badge ${levelClass}`}>
          {LEVEL_LABEL[report.triage_level]}
        </span>
      </div>

      {/* Red flags */}
      {report.red_flags.length > 0 && (
        <div className="red-flags">
          {report.red_flags.map((f) => (
            <span key={f} className="flag-chip">{f}</span>
          ))}
        </div>
      )}

      {/* Key metrics */}
      <div className="metrics-grid">
        <Metric label="Triage Score" value={`${report.triage_score} / 10`} />
        <Metric label="Department" value={report.matched_department} />
        <Metric label="Available Slots" value={report.available_slots} alert={report.capacity_flag} />
        <Metric label="Est. Wait" value={`${report.estimated_wait_minutes} min`} />
      </div>

      {/* Capacity fallback */}
      {report.capacity_flag && report.next_best_department && (
        <div className="capacity-notice">
          <strong>Capacity full.</strong> Next best department:{" "}
          <strong>{report.next_best_department}</strong>
        </div>
      )}

      {/* Clinical */}
      <div className="clinical-section">
        <p className="section-label">Chief Complaint</p>
        <p>{report.chief_complaint}</p>
      </div>

      <div className="clinical-section">
        <p className="section-label">Clinical Summary</p>
        <p>{report.clinical_summary}</p>
      </div>

      {report.recommended_actions.length > 0 && (
        <div className="clinical-section">
          <p className="section-label">Recommended Actions</p>
          <ul className="action-list">
            {report.recommended_actions.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Escalation status */}
      {report.escalated && (
        <div className="escalated-notice">
          <strong>Escalated</strong> — {report.escalation_reason}
          <br />
          <small>{new Date(report.escalated_at).toLocaleString()}</small>
        </div>
      )}

      {/* Escalate action */}
      {!report.escalated && report.triage_level !== "EMERGENCY" && (
        <div className="escalate-section">
          <p className="section-label">Manual Escalation</p>
          <div className="escalate-row">
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Reason for escalation…"
            />
            <button className="btn btn-danger" onClick={handleEscalate} disabled={escalating}>
              {escalating ? "Escalating…" : "Escalate to EMERGENCY"}
            </button>
          </div>
          {escalateError && <div className="error-box">{escalateError}</div>}
        </div>
      )}

      <p className="report-footer">
        Model: <strong>{report.llm_model_used}</strong> ·{" "}
        {new Date(report.created_at).toLocaleString()}
      </p>
    </div>
  );
}

function Metric({ label, value, alert }) {
  return (
    <div className={`metric ${alert ? "metric-alert" : ""}`}>
      <span className="metric-label">{label}</span>
      <span className="metric-value">{value}</span>
    </div>
  );
}