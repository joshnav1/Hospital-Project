const BASE = "";   // Vite proxy forwards /triage, /report, /escalate to :8000

export async function submitTriage(payload) {
  const res = await fetch(`${BASE}/triage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) throw { status: res.status, detail: data.detail ?? data };
  return data;
}

export async function getReport(patientId) {
  const res = await fetch(`${BASE}/report/${patientId}`);
  const data = await res.json();
  if (!res.ok) throw { status: res.status, detail: data.detail ?? data };
  return data;
}

export async function escalatePatient(patientId, reason) {
  const res = await fetch(`${BASE}/escalate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ patient_id: patientId, reason }),
  });
  const data = await res.json();
  if (!res.ok) throw { status: res.status, detail: data.detail ?? data };
  return data;
}

export async function getEscalationStatus(patientId) {
  const res = await fetch(`${BASE}/escalate/${patientId}`);
  const data = await res.json();
  if (!res.ok) throw { status: res.status, detail: data.detail ?? data };
  return data;
}