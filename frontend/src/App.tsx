import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchAudit, fetchDashboard, fetchInvestigation, fetchQueue, loadSnapshot, waitForBackend,
} from "./api/client";
import { ProvenanceChip, SourceChip } from "./components";
import { AuditView, ControlCenter, EvaluationView, InvestigationView } from "./pages";
import type { AuditEvent, Dashboard, DataSource, Investigation, QueueItem, Snapshot } from "./types";

type Tab = "control" | "evaluation" | "audit";

export default function App() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [source, setSource] = useState<DataSource>("loading");
  const [attempt, setAttempt] = useState(0);

  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [audit, setAudit] = useState<AuditEvent[]>([]);

  const [tab, setTab] = useState<Tab>("control");
  const [selected, setSelected] = useState<string | null>(null);
  const [liveInvestigation, setLiveInvestigation] = useState<Investigation | null>(null);

  // 1. Snapshot first, always. The page is usable before the backend is even contacted.
  useEffect(() => {
    let cancelled = false;
    loadSnapshot()
      .then((s) => {
        if (cancelled) return;
        setSnapshot(s);
        setDashboard(s.dashboard);
        setQueue(s.queue.items);
        setSource((cur) => (cur === "live" ? cur : "waking"));
      })
      .catch(() => !cancelled && setSource("snapshot"));
    return () => { cancelled = true; };
  }, []);

  // 2. Wake the backend in parallel, then swap to live data if it answers.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const awake = await waitForBackend((n) => !cancelled && setAttempt(n));
      if (cancelled) return;
      if (!awake) { setSource("snapshot"); return; }
      try {
        const [d, q] = await Promise.all([fetchDashboard(), fetchQueue()]);
        if (cancelled) return;
        setDashboard(d);
        setQueue(q);
        setSource("live");
      } catch {
        if (!cancelled) setSource("snapshot");
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // Live investigation detail, when the backend is up. Falls back to the snapshot's own copy.
  useEffect(() => {
    let cancelled = false;
    setLiveInvestigation(null);
    if (!selected || source !== "live") return;
    fetchInvestigation(selected)
      .then((i) => !cancelled && setLiveInvestigation(i))
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, [selected, source]);

  const refreshAudit = useCallback(() => {
    if (source !== "live") return;
    fetchAudit().then(setAudit).catch(() => undefined);
  }, [source]);

  useEffect(() => { if (tab === "audit") refreshAudit(); }, [tab, refreshAudit]);

  const investigation = useMemo(() => {
    if (!selected) return null;
    return liveInvestigation ?? snapshot?.investigations[selected] ?? null;
  }, [selected, liveInvestigation, snapshot]);

  // Named by the generator's own chaos manifest, not inferred: the dataset contains ten bank
  // lines of each reason code, so guessing would surface the wrong pair.
  const twinIds = dashboard?.demo_pair ?? [];

  const provenance = dashboard?.data_provenance ?? "Synthetic dataset · no live Razorpay connection";

  return (
    <>
      <header className="masthead">
        <div className="masthead-inner">
          <div className="brand">LedgerGuard<span>Reconciliation control center</span></div>
          <nav>
            <button onClick={() => { setTab("control"); setSelected(null); }} aria-current={tab === "control" ? "page" : undefined}>Control</button>
            <button onClick={() => { setTab("evaluation"); setSelected(null); }} aria-current={tab === "evaluation" ? "page" : undefined}>Evaluation</button>
            <button onClick={() => { setTab("audit"); setSelected(null); }} aria-current={tab === "audit" ? "page" : undefined}>Audit</button>
          </nav>
          <div className="spacer" />
          <ProvenanceChip text={provenance} />
          <SourceChip source={source} attempt={attempt} />
        </div>
      </header>

      <main className="wrap">
        {!dashboard && (
          <div className="card" style={{ marginTop: 16 }}>
            <div className="empty">Loading reconciliation state…</div>
          </div>
        )}

        {dashboard && tab === "control" && !selected && (
          <ControlCenter dashboard={dashboard} queue={queue} twinIds={twinIds} onSelect={setSelected} />
        )}

        {dashboard && tab === "control" && selected && investigation && (
          <InvestigationView
            data={investigation}
            source={source}
            onBack={() => setSelected(null)}
            onExecuted={refreshAudit}
          />
        )}

        {dashboard && tab === "control" && selected && !investigation && (
          <div className="card"><div className="empty">No detail available for {selected}.</div></div>
        )}

        {tab === "evaluation" && snapshot && <EvaluationView evaluation={snapshot.evaluation} />}
        {tab === "audit" && <AuditView events={audit} source={source} />}

        <p className="note" style={{ marginTop: 24 }}>
          Every figure here comes from a real pipeline run over a seeded, committed dataset. No
          session in this project has ever had Razorpay or model-provider credentials — see
          <code> REAL_VS_SIMULATED.md</code> for the row-by-row account of what is real and what is
          simulated.
        </p>
      </main>
    </>
  );
}
