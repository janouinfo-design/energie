import { useCallback, useEffect, useState } from "react";
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api/energy`;

const AVAIL_STYLE = {
  AVAILABLE: "bg-emerald-100 text-emerald-800 border-emerald-300",
  STALE: "bg-amber-100 text-amber-800 border-amber-300",
  UNAVAILABLE: "bg-slate-100 text-slate-600 border-slate-300",
  ERROR: "bg-rose-100 text-rose-800 border-rose-300",
};
const CONF_STYLE = {
  HIGH: "bg-emerald-100 text-emerald-800",
  MEDIUM: "bg-amber-100 text-amber-800",
  LOW: "bg-orange-100 text-orange-800",
  NONE: "bg-slate-100 text-slate-500",
};

function Badge({ text, cls }) {
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium border ${cls || "bg-slate-100 text-slate-600 border-slate-300"}`}>
      {text}
    </span>
  );
}

// Renders a value cell that NEVER shows 0 for missing data.
function ValueCell({ m }) {
  const missing = m.availability === "UNAVAILABLE" || m.value === null || m.value === undefined;
  return (
    <div className="flex flex-col">
      <span className={`font-mono ${missing ? "text-slate-400 italic" : "text-slate-900"}`}>
        {missing ? "N/A" : `${Number(m.value).toLocaleString(undefined, { maximumFractionDigits: 2 })}${m.unit ? " " + m.unit : ""}`}
      </span>
      {!m.unit_verified && !missing && (
        <span className="text-[10px] text-rose-600">unit non vérifiée</span>
      )}
    </div>
  );
}

export default function EnergyAudit() {
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [summary, setSummary] = useState(null);
  const [mapping, setMapping] = useState([]);
  const [anomalies, setAnomalies] = useState({ counts: {}, anomalies: [] });
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("mapping");
  const [proposals, setProposals] = useState({ counts: {}, proposals: [] });
  const [evFeas, setEvFeas] = useState({ summary: {}, assessments: [] });
  const [changes, setChanges] = useState([]);
  const [readiness, setReadiness] = useState(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [mp, an, pr, ev, ch, rd] = await Promise.all([
        axios.get(`${API}/mapping`),
        axios.get(`${API}/anomalies`),
        axios.get(`${API}/mapping-proposals`),
        axios.get(`${API}/ev-feasibility`),
        axios.get(`${API}/mapping-changes`),
        axios.get(`${API}/readiness`),
      ]);
      setMapping(mp.data.mapping || []);
      setAnomalies(an.data || { counts: {}, anomalies: [] });
      setProposals(pr.data || { counts: {}, proposals: [] });
      setEvFeas(ev.data || { summary: {}, assessments: [] });
      setChanges(ch.data.changes || []);
      setReadiness(rd.data || null);
    } catch (e) {
      if (e?.response?.status === 409) {
        setMapping([]);
        setError("Aucune donnée. Lancez une synchronisation Navixy.");
      } else {
        setError("Erreur de chargement des données.");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const runSync = async () => {
    setSyncing(true);
    setError(null);
    try {
      const r = await axios.post(`${API}/sync`);
      setSummary(r.data);
      await loadAll();
    } catch (e) {
      setError("Échec de la synchronisation Navixy.");
    } finally {
      setSyncing(false);
    }
  };

  const openDetail = async (tid) => {
    setSelected(tid);
    setDetail(null);
    try {
      const [caps, mets] = await Promise.all([
        axios.get(`${API}/trackers/${tid}/capabilities`),
        axios.get(`${API}/trackers/${tid}/metrics`),
      ]);
      setDetail({ caps: caps.data, mets: mets.data });
    } catch (e) {
      setDetail({ error: "Détails indisponibles" });
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800">
      <div className="max-w-7xl mx-auto p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">LOGITRAK — Énergie · Socle d&apos;audit</h1>
            <p className="text-sm text-slate-500">Identité véhicule/tracker · Mapping VIN · Capability map · Anomalies (données réelles Navixy, lecture seule)</p>
          </div>
          <button
            data-testid="energy-sync-btn"
            onClick={runSync}
            disabled={syncing}
            className="px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-700 text-white text-sm font-medium disabled:opacity-50"
          >
            {syncing ? "Synchronisation…" : "Synchroniser Navixy"}
          </button>
        </div>

        {error && (
          <div data-testid="energy-error" className="mb-4 p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-sm">{error}</div>
        )}

        {/* Summary cards */}
        {summary && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6" data-testid="energy-summary">
            {[
              ["Tenant", summary.tenant_id],
              ["Trackers", summary.trackers],
              ["Véhicules", summary.vehicles],
              ["Anomalies", summary.anomalies],
              ["Navixy now", summary.navixy_now],
            ].map(([k, v]) => (
              <div key={k} className="bg-white rounded-lg border border-slate-200 p-3">
                <div className="text-xs text-slate-500">{k}</div>
                <div className="text-lg font-semibold text-slate-900 truncate">{v}</div>
              </div>
            ))}
          </div>
        )}

        {/* Readiness banner */}
        {readiness && (
          <div
            data-testid="readiness-banner"
            className={`mb-4 p-3 rounded-lg border text-sm ${
              readiness.recommendation === "READY_FOR_A_E"
                ? "bg-emerald-50 border-emerald-200 text-emerald-800"
                : "bg-amber-50 border-amber-200 text-amber-800"
            }`}
          >
            <div className="font-semibold">Prêt pour Energy→Journal (A–E) : {readiness.recommendation}</div>
            <div className="text-xs mt-1 flex flex-wrap gap-x-4 gap-y-1">
              <span>Trackers associés: {readiness.kpis.pct_trackers_associated}%</span>
              <span>Véhicules associés: {readiness.kpis.pct_vehicles_associated}%</span>
              <span>Couverture VIN: {readiness.kpis.vin_coverage_physical}%</span>
              <span>Énergie thermique: {readiness.kpis.thermal_energy_coverage}%</span>
              <span>Énergie EV: {readiness.kpis.ev_energy_coverage}%</span>
              <span>Stale: {readiness.kpis.stale_trackers}</span>
              <span>Anomalies bloquantes: {readiness.kpis.blocking_anomalies}</span>
            </div>
            <div className="text-xs mt-1 italic">{readiness.reasons.join(" ")}</div>
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-1 mb-4 border-b border-slate-200" data-testid="energy-tabs">
          {[
            ["mapping", "Mapping"],
            ["proposals", `Propositions${proposals.proposals.length ? " (" + proposals.proposals.length + ")" : ""}`],
            ["ev", "Faisabilité EV"],
            ["changes", `Changements${changes.length ? " (" + changes.length + ")" : ""}`],
          ].map(([id, label]) => (
            <button
              key={id}
              data-testid={`tab-${id}`}
              onClick={() => setTab(id)}
              className={`px-3 py-2 text-sm font-medium -mb-px border-b-2 ${
                tab === id
                  ? "border-violet-600 text-violet-700"
                  : "border-transparent text-slate-500 hover:text-slate-700"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Anomaly counts */}
        <div className="mb-6">
          <h2 className="text-sm font-semibold text-slate-700 mb-2">Anomalies détectées</h2>
          <div className="flex flex-wrap gap-2" data-testid="anomaly-counts">
            {Object.keys(anomalies.counts || {}).length === 0 ? (
              <span className="text-sm text-slate-400 italic">Aucune donnée</span>
            ) : (
              Object.entries(anomalies.counts).map(([t, c]) => (
                <Badge key={t} text={`${t}: ${c}`} cls="bg-slate-100 text-slate-700 border-slate-300" />
              ))
            )}
          </div>
        </div>

        {/* Proposals tab */}
        {tab === "proposals" && (
          <div className="bg-white rounded-lg border border-slate-200 overflow-hidden" data-testid="proposals-table">
            <table className="w-full text-sm">
              <thead className="bg-slate-100 text-slate-600 text-xs uppercase">
                <tr>
                  <th className="text-left px-3 py-2">Anomalie</th>
                  <th className="text-left px-3 py-2">Classification</th>
                  <th className="text-left px-3 py-2">Tracker</th>
                  <th className="text-left px-3 py-2">Véhicule</th>
                  <th className="text-left px-3 py-2">VIN OBD</th>
                  <th className="text-left px-3 py-2">Proposition</th>
                  <th className="text-left px-3 py-2">Preuve</th>
                </tr>
              </thead>
              <tbody>
                {proposals.proposals.map((p, i) => (
                  <tr key={i} className="border-t border-slate-100">
                    <td className="px-3 py-2 text-xs">{p.anomaly}</td>
                    <td className="px-3 py-2"><Badge text={p.classification} cls={p.classification === "SAFE_TO_REVIEW" ? "bg-emerald-100 text-emerald-800" : p.classification === "AMBIGUOUS" ? "bg-amber-100 text-amber-800" : "bg-slate-100 text-slate-600"} /></td>
                    <td className="px-3 py-2 font-mono text-xs">{p.tracker_id || <span className="text-slate-400 italic">—</span>}</td>
                    <td className="px-3 py-2 text-xs">{p.vehicle_id || <span className="text-slate-400 italic">—</span>}</td>
                    <td className="px-3 py-2 font-mono text-xs">{p.obd_vin || <span className="text-slate-400 italic">absent</span>}</td>
                    <td className="px-3 py-2 text-xs">{p.proposed_match || <span className="text-slate-400 italic">aucune</span>}</td>
                    <td className="px-3 py-2 text-xs text-slate-500">{(p.evidence || []).join("; ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="px-3 py-2 text-xs text-slate-400 italic border-t border-slate-100">Aucune écriture Navixy n&apos;est effectuée. Propositions à valider manuellement.</div>
          </div>
        )}

        {/* EV feasibility tab */}
        {tab === "ev" && (
          <div className="bg-white rounded-lg border border-slate-200 p-4" data-testid="ev-feasibility">
            <div className="text-sm text-slate-700 mb-2">{evFeas.summary.conclusion}</div>
            <div className="flex flex-wrap gap-2 mb-3 text-xs">
              {Object.entries(evFeas.summary.device_families || {}).map(([f, c]) => (
                <Badge key={f} text={`${f}: ${c}`} cls="bg-slate-100 text-slate-700 border-slate-300" />
              ))}
            </div>
            <table className="w-full text-sm">
              <thead className="bg-slate-100 text-slate-600 text-xs uppercase">
                <tr>
                  <th className="text-left px-3 py-2">Tracker</th>
                  <th className="text-left px-3 py-2">Modèle</th>
                  <th className="text-left px-3 py-2">SoC — canal</th>
                  <th className="text-left px-3 py-2">Confiance</th>
                  <th className="text-left px-3 py-2">Config requise</th>
                </tr>
              </thead>
              <tbody>
                {evFeas.assessments.map((a) => {
                  const soc = (a.metrics || []).find((m) => m.metric === "soc") || {};
                  return (
                    <tr key={a.tracker_id} className="border-t border-slate-100">
                      <td className="px-3 py-2 font-mono text-xs">{a.tracker_id}</td>
                      <td className="px-3 py-2 text-xs">{a.device_family}</td>
                      <td className="px-3 py-2 text-xs">{soc.channel}</td>
                      <td className="px-3 py-2 text-xs">{soc.confidence}</td>
                      <td className="px-3 py-2 text-xs text-slate-500">{soc.config_required || "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Mapping changes tab */}
        {tab === "changes" && (
          <div className="bg-white rounded-lg border border-slate-200 overflow-hidden" data-testid="changes-table">
            {changes.length === 0 ? (
              <div className="p-4 text-sm text-slate-400 italic">Aucun changement de mapping détecté.</div>
            ) : (
              <table className="w-full text-sm">
                <thead className="bg-slate-100 text-slate-600 text-xs uppercase">
                  <tr>
                    <th className="text-left px-3 py-2">Type</th>
                    <th className="text-left px-3 py-2">Tracker</th>
                    <th className="text-left px-3 py-2">Détecté</th>
                    <th className="text-left px-3 py-2">Détail</th>
                  </tr>
                </thead>
                <tbody>
                  {changes.map((c, i) => (
                    <tr key={i} className="border-t border-slate-100">
                      <td className="px-3 py-2"><Badge text={c.type} cls="bg-violet-100 text-violet-700 border-violet-300" /></td>
                      <td className="px-3 py-2 font-mono text-xs">{c.tracker_id}</td>
                      <td className="px-3 py-2 text-xs">{c.detected_at}</td>
                      <td className="px-3 py-2 text-xs text-slate-500">{c.detail}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {/* Mapping table */}
        {tab === "mapping" && (
        <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
          <table className="w-full text-sm" data-testid="mapping-table">
            <thead className="bg-slate-100 text-slate-600 text-xs uppercase">
              <tr>
                <th className="text-left px-3 py-2">Tracker</th>
                <th className="text-left px-3 py-2">Label (info seule)</th>
                <th className="text-left px-3 py-2">VIN OBD</th>
                <th className="text-left px-3 py-2">Véhicule lié</th>
                <th className="text-left px-3 py-2">Confiance</th>
                <th className="text-left px-3 py-2">Connexion</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {mapping.map((m) => (
                <tr key={m.tracker_id} className="border-t border-slate-100 hover:bg-slate-50">
                  <td className="px-3 py-2 font-mono">{m.tracker_id}</td>
                  <td className="px-3 py-2 text-slate-500">{m.tracker_label}</td>
                  <td className="px-3 py-2 font-mono text-xs">{m.obd_vin || <span className="text-slate-400 italic">absent</span>}</td>
                  <td className="px-3 py-2">{m.vehicle_id || <span className="text-slate-400 italic">non lié</span>}</td>
                  <td className="px-3 py-2"><Badge text={m.confidence} cls={CONF_STYLE[m.confidence]} /></td>
                  <td className="px-3 py-2 text-xs">{m.connection_status}</td>
                  <td className="px-3 py-2 text-right">
                    <button
                      data-testid={`detail-btn-${m.tracker_id}`}
                      onClick={() => openDetail(m.tracker_id)}
                      className="text-violet-600 hover:underline text-xs"
                    >
                      Capabilities
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        )}

        {/* Detail panel */}
        {selected && (
          <div className="mt-6 bg-white rounded-lg border border-slate-200 p-4" data-testid="detail-panel">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold text-slate-800">Tracker {selected} · Capability map & métriques</h3>
              <button onClick={() => setSelected(null)} className="text-slate-400 hover:text-slate-600 text-sm">Fermer</button>
            </div>
            {!detail && <div className="text-sm text-slate-400">Chargement…</div>}
            {detail?.error && <div className="text-sm text-rose-600">{detail.error}</div>}
            {detail?.mets && (
              <table className="w-full text-sm mb-4">
                <thead className="text-xs text-slate-500 uppercase">
                  <tr>
                    <th className="text-left py-1">Métrique</th>
                    <th className="text-left py-1">Valeur</th>
                    <th className="text-left py-1">Disponibilité</th>
                    <th className="text-left py-1">Type</th>
                    <th className="text-left py-1">Source</th>
                    <th className="text-left py-1">Horodatage</th>
                    <th className="text-left py-1">Raison</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.mets.metrics.map((m) => (
                    <tr key={m.key} className="border-t border-slate-100">
                      <td className="py-1 pr-3">{m.label}</td>
                      <td className="py-1 pr-3"><ValueCell m={m} /></td>
                      <td className="py-1 pr-3"><Badge text={m.availability} cls={AVAIL_STYLE[m.availability]} /></td>
                      <td className="py-1 pr-3 text-xs">{m.measurement_type}</td>
                      <td className="py-1 pr-3 text-xs">{m.source}</td>
                      <td className="py-1 pr-3 text-xs text-slate-500" data-testid={`ts-${m.key}`}>{m.timestamp || <span className="italic text-slate-400">—</span>}</td>
                      <td className="py-1 pr-3 text-xs text-slate-400">{m.reason || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {detail?.caps && (
              <div>
                <div className="text-xs text-slate-500 mb-1">Capteurs EV détectés : {detail.caps.ev_sensors.length ? detail.caps.ev_sensors.join(", ") : <span className="italic text-slate-400">aucun</span>}</div>
                <div className="flex flex-wrap gap-1">
                  {detail.caps.capabilities
                    .filter((c) => ["soc", "battery_capacity", "range_est", "charge_power", "energy_used", "consumption_kwh_100"].includes(c.metric_key))
                    .map((c) => (
                      <Badge key={c.metric_key} text={`${c.metric_key}: ${c.availability}`} cls={AVAIL_STYLE[c.availability]} />
                    ))}
                </div>
              </div>
            )}
          </div>
        )}

        {loading && <div className="mt-4 text-sm text-slate-400">Chargement…</div>}
      </div>
    </div>
  );
}
