import { useState } from "react";
import { getReport } from "./api";
import TriageForm from "./components/TriageForm";
import TriageReport from "./components/TriageReport";
import ReportLookup from "./components/ReportLookup";
import "./App.css";

export default function App() {
  const [reports, setReports] = useState([]);
  const [activeTab, setActiveTab] = useState("new");

  function addOrUpdateReport(report) {
    setReports((prev) => {
      const idx = prev.findIndex((r) => r.patient_id === report.patient_id);
      if (idx !== -1) {
        const updated = [...prev];
        updated[idx] = report;
        return updated;
      }
      return [report, ...prev];
    });
    setActiveTab("reports");
  }

  async function refreshReport(patientId) {
    try {
      const updated = await getReport(patientId);
      addOrUpdateReport(updated);
    } catch {
      // silently ignore
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-inner">
          <div className="header-title">
            <span className="header-icon">🏥</span>
            <div>
              <h1>Patient Triage Agent</h1>
              <p>AI-powered triage assessment &amp; care routing</p>
            </div>
          </div>
          <nav className="tab-nav">
            <button
              className={`tab-btn ${activeTab === "new" ? "active" : ""}`}
              onClick={() => setActiveTab("new")}
            >
              New Triage
            </button>
            <button
              className={`tab-btn ${activeTab === "reports" ? "active" : ""}`}
              onClick={() => setActiveTab("reports")}
            >
              Reports{" "}
              {reports.length > 0 && (
                <span className="badge-count">{reports.length}</span>
              )}
            </button>
            <button
              className={`tab-btn ${activeTab === "lookup" ? "active" : ""}`}
              onClick={() => setActiveTab("lookup")}
            >
              Lookup
            </button>
          </nav>
        </div>
      </header>

      <main className="app-main">
        {activeTab === "new" && <TriageForm onResult={addOrUpdateReport} />}

        {activeTab === "reports" && (
          <div>
            {reports.length === 0 ? (
              <div className="empty-state">
                <p>No reports yet. Submit a triage to get started.</p>
                <button
                  className="btn btn-primary"
                  onClick={() => setActiveTab("new")}
                >
                  New Triage
                </button>
              </div>
            ) : (
              reports.map((r) => (
                <TriageReport
                  key={r.patient_id}
                  report={r}
                  onUpdated={refreshReport}
                />
              ))
            )}
          </div>
        )}

        {activeTab === "lookup" && <ReportLookup onResult={addOrUpdateReport} />}
      </main>
    </div>
  );
}