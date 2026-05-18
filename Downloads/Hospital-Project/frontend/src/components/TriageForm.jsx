import { useRef, useState } from "react";

const EMPTY = {
  patient_name: "",
  age: "",
  gender: "male",
  symptoms: "",
  symptom_duration_hours: "",
  medical_history: "",
  current_medications: "",
  allergies: "",
  temperature_celsius: "",
  heart_rate_bpm: "",
  blood_pressure_systolic: "",
  oxygen_saturation_pct: "",
  notes: "",
};

function formatError(status, data) {
  if (status === 422) {
    const items = Array.isArray(data?.detail) ? data.detail : [];
    const lines = items.map((e) => {
      const field = (e.loc ?? []).slice(1).join(" → ") || "field";
      return `• ${field}: ${e.msg}`;
    });
    return {
      type: "warning",
      title: "Please fix the following before submitting:",
      body: lines.length ? lines.join("\n") : "Check all required fields and try again.",
    };
  }
  if (status === 503 || status === 502) {
    return {
      type: "error",
      title: "Service unavailable",
      body: "The triage service is temporarily unavailable. Please try again in a moment.",
    };
  }
  if (status >= 500) {
    return {
      type: "error",
      title: "Server error",
      body: "An unexpected server error occurred. Please try again.",
    };
  }
  const detail = data?.detail;
  return {
    type: "error",
    title: `Error (${status})`,
    body: typeof detail === "string" ? detail : JSON.stringify(detail ?? data, null, 2),
  };
}

export default function TriageForm({ onResult }) {
  const [form, setForm] = useState(EMPTY);
  const [status, setStatus] = useState("idle");
  const [streamText, setStreamText] = useState("");
  const [liveFlags, setLiveFlags] = useState([]);
  const [error, setError] = useState(null);
  const [showDetails, setShowDetails] = useState(false);
  const [showVitals, setShowVitals] = useState(false);
  const streamBoxRef = useRef(null);

  function set(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  function parseList(str) {
    return str.split(",").map((s) => s.trim()).filter(Boolean);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setStreamText("");
    setLiveFlags([]);
    setStatus("streaming");

    const vitalsFields = {
      temperature_celsius: parseFloat(form.temperature_celsius),
      heart_rate_bpm: parseInt(form.heart_rate_bpm),
      blood_pressure_systolic: parseInt(form.blood_pressure_systolic),
      oxygen_saturation_pct: parseFloat(form.oxygen_saturation_pct),
    };
    const vitals = Object.fromEntries(
      Object.entries(vitalsFields).filter(([, v]) => !isNaN(v))
    );

    const payload = {
      patient_name: form.patient_name,
      age: parseInt(form.age),
      gender: form.gender,
      symptoms: parseList(form.symptoms),
      ...(form.symptom_duration_hours && { symptom_duration_hours: parseFloat(form.symptom_duration_hours) }),
      ...(form.medical_history && { medical_history: parseList(form.medical_history) }),
      ...(form.current_medications && { current_medications: parseList(form.current_medications) }),
      ...(form.allergies && { allergies: parseList(form.allergies) }),
      ...(Object.keys(vitals).length > 0 && { vitals }),
      ...(form.notes && { notes: form.notes }),
    };

    try {
      const res = await fetch("/triage/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        let data = {};
        try { data = await res.json(); } catch { /* non-JSON body */ }
        setError(formatError(res.status, data));
        setStatus("idle");
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let currentEvent = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();

        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            const data = JSON.parse(line.slice(6));

            if (currentEvent === "red_flags") {
              setLiveFlags(data.flags ?? []);
            } else if (currentEvent === "reasoning") {
              setStreamText((prev) => {
                const next = prev + data.text;
                setTimeout(() => {
                  if (streamBoxRef.current)
                    streamBoxRef.current.scrollTop = streamBoxRef.current.scrollHeight;
                }, 0);
                return next;
              });
            } else if (currentEvent === "complete") {
              setStatus("done");
              setForm(EMPTY);
              onResult(data);
            }
          }
        }
      }
    } catch (err) {
      setStreamText("");
      setLiveFlags([]);
      setStatus("idle");
      if (err instanceof TypeError) {
        setError({
          type: "network",
          title: "Connection error",
          body: "Could not reach the server. Check your network connection and try again.",
        });
      } else {
        setError({
          type: "error",
          title: "Unexpected error",
          body: err.message ?? String(err),
        });
      }
    }
  }

  const busy = status === "streaming";

  return (
    <form className="card" onSubmit={handleSubmit}>
      <h2 className="card-title">New Patient Triage</h2>

      {/* ── Core fields ── */}
      <div className="form-grid">
        <div className="form-group">
          <label>Patient Name *</label>
          <input required value={form.patient_name} onChange={(e) => set("patient_name", e.target.value)} placeholder="e.g. Ravi Kumar" />
        </div>

        <div className="form-group">
          <label>Age *</label>
          <input required type="number" min={0} max={130} value={form.age} onChange={(e) => set("age", e.target.value)} placeholder="e.g. 54" />
        </div>

        <div className="form-group">
          <label>Gender *</label>
          <select value={form.gender} onChange={(e) => set("gender", e.target.value)}>
            <option value="male">Male</option>
            <option value="female">Female</option>
            <option value="other">Other</option>
          </select>
        </div>

        <div className="form-group">
          <label>Duration (hours)</label>
          <input type="number" min={0} step={0.5} value={form.symptom_duration_hours} onChange={(e) => set("symptom_duration_hours", e.target.value)} placeholder="e.g. 2" />
        </div>

        <div className="form-group full-width">
          <label>Symptoms * <span className="hint">(comma-separated)</span></label>
          <input required value={form.symptoms} onChange={(e) => set("symptoms", e.target.value)} placeholder="e.g. severe chest pain, shortness of breath, left arm numbness" />
        </div>
      </div>

      {/* ── Additional Details (expandable) ── */}
      <button
        type="button"
        className="expand-btn"
        onClick={() => setShowDetails((v) => !v)}
      >
        <span className={`expand-arrow ${showDetails ? "open" : ""}`}>▶</span>
        Additional Details
        <span className="expand-hint">Medical history · Medications · Allergies</span>
      </button>

      {showDetails && (
        <div className="form-grid expand-body">
          <div className="form-group full-width">
            <label>Medical History <span className="hint">(comma-separated)</span></label>
            <input value={form.medical_history} onChange={(e) => set("medical_history", e.target.value)} placeholder="e.g. hypertension, type 2 diabetes" />
          </div>

          <div className="form-group">
            <label>Current Medications <span className="hint">(comma-separated)</span></label>
            <input value={form.current_medications} onChange={(e) => set("current_medications", e.target.value)} placeholder="e.g. metformin, aspirin" />
          </div>

          <div className="form-group">
            <label>Allergies <span className="hint">(comma-separated)</span></label>
            <input value={form.allergies} onChange={(e) => set("allergies", e.target.value)} placeholder="e.g. penicillin" />
          </div>
        </div>
      )}

      {/* ── Vitals (expandable) ── */}
      <button
        type="button"
        className="expand-btn"
        onClick={() => setShowVitals((v) => !v)}
      >
        <span className={`expand-arrow ${showVitals ? "open" : ""}`}>▶</span>
        Vitals
        <span className="expand-hint">Temperature · Heart rate · BP · SpO₂</span>
      </button>

      {showVitals && (
        <div className="form-grid expand-body">
          <div className="form-group">
            <label>Temperature (°C)</label>
            <input type="number" step={0.1} value={form.temperature_celsius} onChange={(e) => set("temperature_celsius", e.target.value)} placeholder="e.g. 38.5" />
          </div>

          <div className="form-group">
            <label>Heart Rate (bpm)</label>
            <input type="number" value={form.heart_rate_bpm} onChange={(e) => set("heart_rate_bpm", e.target.value)} placeholder="e.g. 95" />
          </div>

          <div className="form-group">
            <label>Systolic BP (mmHg)</label>
            <input type="number" value={form.blood_pressure_systolic} onChange={(e) => set("blood_pressure_systolic", e.target.value)} placeholder="e.g. 140" />
          </div>

          <div className="form-group">
            <label>SpO₂ (%)</label>
            <input type="number" step={0.1} value={form.oxygen_saturation_pct} onChange={(e) => set("oxygen_saturation_pct", e.target.value)} placeholder="e.g. 97" />
          </div>
        </div>
      )}

      {/* ── Staff notes ── */}
      <div className="form-grid" style={{ marginTop: "0.75rem" }}>
        <div className="form-group full-width">
          <label>Staff Notes</label>
          <textarea rows={2} value={form.notes} onChange={(e) => set("notes", e.target.value)} placeholder="Free-text notes from admitting staff..." />
        </div>
      </div>

      {/* Error alert */}
      {error && (
        <div className={`alert-box alert-${error.type}`}>
          <strong>{error.title}</strong>
          {error.body && <p>{error.body}</p>}
        </div>
      )}

      {/* Live streaming panel */}
      {!error && (busy || liveFlags.length > 0 || streamText) && (
        <div className="stream-panel">
          <div className="stream-header">
            {busy && <span className="stream-pulse" />}
            <span className="stream-title">
              {busy ? "Assessing patient…" : "Assessment complete"}
            </span>
          </div>

          {liveFlags.length > 0 && (
            <div className="stream-flags">
              {liveFlags.map((f) => (
                <span key={f} className="flag-chip">{f}</span>
              ))}
            </div>
          )}

          {streamText && (
            <div className="stream-text" ref={streamBoxRef}>
              <span>{streamText}</span>
              {busy && <span className="stream-cursor">▋</span>}
            </div>
          )}
        </div>
      )}

      <button className="btn btn-primary" type="submit" disabled={busy}>
        {busy ? "Streaming…" : "Submit Triage"}
      </button>
    </form>
  );
}