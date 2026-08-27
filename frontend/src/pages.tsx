import { useEffect, useMemo, useState } from "react";
import { AblationChart, RuleLearningCharts } from "./charts";
import {
  ActionBadge, ConfidenceMeter, PolicyPanel, QueueTable, SignalList, StatTile, pct, rupees, shortDate,
} from "./components";
import { executeDecision } from "./api/client";
import type { AuditEvent, Dashboard, DataSource, Evaluation, ExecuteResult, Investigation, QueueItem } from "./types";

/* ------------------------------------------------------------------ Control Center */

export function ControlCenter({
  dashboard, queue, twinIds, onSelect,
}: {
  dashboard: Dashboard;
  queue: QueueItem[];
  twinIds: string[];
  onSelect: (id: string) => void;
}) {
  const [action, setAction] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return queue.filter(
      (i) =>
        (!action || i.action === action) &&
        (!difficulty || i.difficulty === difficulty) &&
        (!needle || i.bank_line_id.toLowerCase().includes(needle) || i.narration.toLowerCase().includes(needle)),
    );
  }, [queue, action, difficulty, search]);

  const twins = queue.filter((i) => twinIds.includes(i.bank_line_id));

  return (
    <>
      {twins.length === 2 && (
        <div className="card hero">
          <h1>Two credits. Same amount, same day, one character apart.</h1>
          <p className="sub">
            One is a duplicate report. The other is real money sent twice. Both cleared the
            confidence gate — and the anomaly detector refused both anyway, with different reason
            codes so a reviewer knows which is which.
          </p>
          <div className="twins">
            {twins.map((t) => (
              <div className="twin" key={t.bank_line_id} onClick={() => onSelect(t.bank_line_id)} style={{ cursor: "pointer" }}>
                <div className="id">{t.bank_line_id}</div>
                <div className="amt">{rupees(t.credit_paise)}</div>
                <div className="narr">{t.narration}</div>
                <div style={{ marginTop: 8, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                  <ActionBadge action={t.action} />
                  <span className="mono" style={{ fontSize: 11.5 }}>{t.reason_code}</span>
                </div>
              </div>
            ))}
          </div>
          <p className="note">
            Calibrated confidence {twins[0].calibrated_confidence.toFixed(3)} against a threshold of{" "}
            {twins[0].threshold.toFixed(2)} — the gate said yes. L4 has veto power over L1 and L3, and used it.
          </p>
        </div>
      )}

      <div className="tiles" style={{ marginTop: 16 }}>
        <StatTile k="Reconciled" v={String(dashboard.total_bank_lines)} n={rupees(dashboard.total_credit_paise)} />
        <StatTile k="Auto-posted" v={String(dashboard.counts_by_action.AUTO_POST ?? 0)} n={pct(dashboard.auto_post_rate)} />
        <StatTile k="Refused" v={String(dashboard.refused)} n="escalated or flagged" />
        <StatTile k="False auto-match" v={pct(dashboard.false_auto_match_rate)} n="of everything posted" accent="good" />
        <StatTile k="Precision (posted)" v={pct(dashboard.precision_auto_posted)} n={`all ${dashboard.total_bank_lines} records`} />
        <StatTile k="LLM invocations" v={String(dashboard.llm_invocation_count)} n={`of ${dashboard.total_bank_lines} records`} />
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h2>Reconciliation queue</h2>
        <p className="sub">
          Refused decisions first, then by rupees at risk — the exception queue's own ranking, so the
          most consequential cases surface first. Click any row to investigate.
        </p>
        <div className="filters">
          <select value={action} onChange={(e) => setAction(e.target.value)} aria-label="Filter by decision">
            <option value="">All decisions</option>
            <option value="AUTO_POST">Auto-posted</option>
            <option value="ESCALATE">Escalated</option>
            <option value="FLAG_ANOMALY">Anomaly flagged</option>
          </select>
          <select value={difficulty} onChange={(e) => setDifficulty(e.target.value)} aria-label="Filter by stratum">
            <option value="">All strata</option>
            <option value="EASY">Easy</option>
            <option value="MEDIUM">Medium</option>
            <option value="HARD">Hard</option>
            <option value="ADVERSARIAL">Adversarial</option>
          </select>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search bank line id or narration"
            aria-label="Search"
          />
          <span style={{ color: "var(--text-muted)", fontSize: 13 }}>
            {filtered.length} of {queue.length}
          </span>
        </div>
        <QueueTable items={filtered} onSelect={onSelect} />
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ Investigation */

export function InvestigationView({
  data, source, onBack, onExecuted,
}: {
  data: Investigation;
  source: DataSource;
  onBack: () => void;
  onExecuted: () => void;
}) {
  const [result, setResult] = useState<ExecuteResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { setResult(null); setError(null); }, [data.bank_line.bank_line_id]);

  const live = source === "live";
  const matched = data.payments.filter((p) => p.role === "matched");
  const shown = matched.length > 0 ? matched : data.payments;

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const r = await executeDecision(data.bank_line.bank_line_id);
      setResult(r);
      onExecuted();
    } catch {
      setError("Could not reach the backend to execute. It may still be waking up.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button className="back" onClick={onBack}>← Back to queue</button>

      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap", alignItems: "flex-start" }}>
          <div>
            <h2 style={{ marginBottom: 4 }}>{data.bank_line.bank_line_id}</h2>
            <div style={{ fontSize: 26, fontWeight: 650, letterSpacing: "-0.02em" }}>
              {rupees(data.bank_line.credit_paise)}
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <ActionBadge action={data.action} />
            <div className="mono" style={{ fontSize: 12, marginTop: 6, color: "var(--text-secondary)" }}>
              {data.reason_code ?? "—"}
            </div>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
              {data.difficulty} · resolved by {data.resolver}
            </div>
          </div>
        </div>

        <div className="panels" style={{ marginTop: 18 }}>
          <div className="panel">
            <h4>Bank statement</h4>
            <div className="kv"><span className="k">UTR</span><span className="v">{data.bank_line.utr ?? "—"}</span></div>
            <div className="kv"><span className="k">Credit</span><span className="v">{rupees(data.bank_line.credit_paise)}</span></div>
            <div className="kv"><span className="k">Value date</span><span className="v">{shortDate(data.bank_line.value_date)}</span></div>
            <div className="kv"><span className="k">Narration</span><span className="v">{data.bank_line.narration}</span></div>
          </div>

          <div className="panel">
            <h4>Payment{shown.length > 1 ? "s" : ""} {matched.length === 0 && shown.length > 0 ? "(candidates)" : ""}</h4>
            {shown.length === 0 && <div style={{ fontSize: 13, color: "var(--text-muted)" }}>No candidate payment in the lookback window.</div>}
            {shown.slice(0, 3).map((p) => (
              <div key={p.payment_id} style={{ marginBottom: 8 }}>
                <div className="kv"><span className="k">Payment</span><span className="v">{p.payment_id}</span></div>
                <div className="kv"><span className="k">Net</span><span className="v">{rupees(p.net_paise)}</span></div>
                <div className="kv"><span className="k">Captured</span><span className="v">{shortDate(p.captured_at)}</span></div>
              </div>
            ))}
            {shown.length > 3 && <div className="note">+{shown.length - 3} more candidates in window</div>}
          </div>

          <div className="panel">
            <h4>Internal ledger</h4>
            {data.order_ids.length === 0 && <div style={{ fontSize: 13, color: "var(--text-muted)" }}>No order proposed.</div>}
            {data.order_ids.slice(0, 4).map((o) => (
              <div className="kv" key={o}><span className="k">Order</span><span className="v">{o}</span></div>
            ))}
            {data.order_ids.length > 4 && <div className="note">+{data.order_ids.length - 4} more</div>}
            {data.ground_truth_order_ids && (
              <div className="note" style={{ marginTop: 8 }}>
                Ground truth: {data.ground_truth_order_ids.join(", ") || "no match"} —{" "}
                {data.decision_was_correct ? "decision correct" : "decision differs"}. Available only
                because this dataset is synthetic.
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="card">
        <h2>Why wasn’t this posted automatically?</h2>
        <p className="sub">
          Structured decision factors, computed from the same feature vector the calibrator scores —
          not model narration.
        </p>
        <ConfidenceMeter value={data.calibrated_confidence} threshold={data.threshold} />
        <SignalList signals={data.signals} />
        {data.evidence.length > 0 && (
          <>
            <h3 style={{ marginTop: 16 }}>Evidence</h3>
            <ul className="evidence">
              {data.evidence.map((e, i) => <li key={i}>{e}</li>)}
            </ul>
          </>
        )}
      </div>

      <div className="card">
        <h2>Authority policy</h2>
        <p className="sub">All three clauses must hold before the system may act on its own.</p>
        <PolicyPanel policy={result ? result.policy : data.policy} />

        <div className={`verdict ${data.action === "AUTO_POST" ? "approved" : "blocked"}`}>
          {data.action === "AUTO_POST"
            ? "AUTHORIZED — within the autonomous envelope."
            : `AUTO-POST BLOCKED — ${data.anomalies.length > 0
                ? `an anomaly flag (${data.anomalies[0].reason_code}) prevents autonomous execution`
                : "the confidence gate was not cleared"}.`}
        </div>

        <div style={{ marginTop: 14, display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <button className="action" onClick={run} disabled={!live || busy}>
            {busy ? "Executing…" : "Authorize & execute"}
          </button>
          {!live && (
            <span className="note" style={{ margin: 0 }}>
              Execution needs the live backend — this view is running on the offline snapshot.
            </span>
          )}
        </div>

        {error && <div className="note" style={{ color: "var(--critical)" }}>{error}</div>}

        {result && (
          <div className="receipt">
            <div>{result.message}</div>
            {result.authorized && (
              <>
                <div className="ok">✓ Entry {result.newly_posted ? "created" : "already present"}</div>
                <div className="ok">✓ Idempotency key {result.idempotency_key?.slice(0, 24)}…</div>
                <div className="ok">✓ {result.newly_posted ? "Audit event recorded" : "No duplicate written"}</div>
                <div style={{ color: "var(--text-muted)" }}>{result.decision_id}</div>
              </>
            )}
          </div>
        )}
        {result?.authorized && (
          <p className="note">
            Run it again — the idempotency key is already stored, so the second call is a no-op
            rather than a second posting.
          </p>
        )}
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ Audit */

export function AuditView({ events, source }: { events: AuditEvent[]; source: DataSource }) {
  return (
    <div className="card">
      <h2>Audit log</h2>
      <p className="sub">Append-only. One line per posted decision, replayable after the fact.</p>
      {source !== "live" ? (
        <div className="empty">The audit log lives on the backend. It appears once the live API is reachable.</div>
      ) : events.length === 0 ? (
        <div className="empty">Nothing posted yet this session. Execute a clean decision to write the first entry.</div>
      ) : (
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>Bank line</th><th>Action</th><th>Resolver</th><th>Confidence</th><th>Idempotency key</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr key={e.decision_id}>
                  <td className="mono">{e.bank_line_id}</td>
                  <td><ActionBadge action={e.action} /></td>
                  <td>{e.resolver}</td>
                  <td>{e.calibrated_confidence?.toFixed(3) ?? "—"}</td>
                  <td className="mono">{e.idempotency_key.slice(0, 20)}…</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ Evaluation */

export function EvaluationView({ evaluation }: { evaluation: Evaluation }) {
  const e = evaluation;
  const overall = e.operational.find((r) => r.stratum === "Overall");
  return (
    <>
      <div className="card">
        <h2>Pre-registered ablation</h2>
        <p className="sub">
          The decision rule was committed to git <em>before</em> this was ever run
          (<code>PREREGISTRATION.md</code>) — so the verdict below was fixed while it was still
          cheap to be honest about.
        </p>
        <AblationChart rows={e.ablation} />

        <div className={`callout ${e.band === "NEGATIVE" ? "negative" : ""}`} style={{ marginTop: 16 }}>
          <strong>Δ (HARD + ADVERSARIAL) = {e.delta_hard_adversarial.toFixed(3)} → {e.band}.</strong>
          <div style={{ marginTop: 6 }}>{e.verdict}</div>
        </div>
        <p className="note">
          Δ on EASY = {e.delta_easy.toFixed(3)}, matching the registered prediction of ≈0. The HARD
          (n=4) and ADVERSARIAL (n=5) holdout strata are small — the result is exact on this dataset,
          but one flipped record would move it several points. Stated here rather than buried.
        </p>
        <p className="note">
          LLM-only scores 0.000 across every stratum. That is a structural property of the free
          rapidfuzz fallback serving L2 — without the deterministic layer narrowing the candidate
          window first, it almost never has grounds to answer. It is not a measurement of a live
          model, which this project has never had credentials to run.
        </p>

        <div className="scroll" style={{ marginTop: 16 }}>
          <table>
            <thead>
              <tr><th>Stratum</th><th>n</th><th>Rules-only F1</th><th>Hybrid F1</th><th>LLM-only F1</th><th>LLM calls</th></tr>
            </thead>
            <tbody>
              {e.ablation.map((r) => (
                <tr key={r.stratum} className={r.stratum === "Overall" ? "total" : undefined}>
                  <td>{r.stratum}</td><td>{r.n}</td>
                  <td>{r.rules_only_f1.toFixed(3)}</td>
                  <td>{r.hybrid_f1.toFixed(3)}</td>
                  <td>{r.llm_only_f1.toFixed(3)}</td>
                  <td>{r.llm_calls}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <h2>The LLM’s workload shrinks over time</h2>
        <p className="sub">
          A human resolves one exception; the system compiles it into a candidate rule, replays it
          against history, and promotes it only at ≥3 hits and zero false positives.
        </p>
        <RuleLearningCharts rows={e.rule_learning} />
        <p className="note">
          Two separate charts on purpose: invocation rate and precision are different measures, and
          putting them on one pair of axes would invite a comparison the geometry does not support.
        </p>
      </div>

      <div className="card">
        <h2>Operational metrics (holdout only)</h2>
        <p className="sub">
          Holdout split only — 60 of the 300 records. The Control tab reports the same measures over
          the full batch, so the two differ by denominator, not by method.
        </p>
        <div className="scroll">
          <table>
            <thead>
              <tr><th>Stratum</th><th>n</th><th>Auto-match</th><th>Precision</th><th>Recall</th><th>F1</th><th>False auto-match</th></tr>
            </thead>
            <tbody>
              {e.operational.map((r) => (
                <tr key={r.stratum} className={r.stratum === "Overall" ? "total" : undefined}>
                  <td>{r.stratum}</td><td>{r.n}</td>
                  <td>{pct(r.auto_match_rate)}</td>
                  <td>{pct(r.precision_auto_posted)}</td>
                  <td>{pct(r.recall)}</td>
                  <td>{r.f1.toFixed(2)}</td>
                  <td>{pct(r.false_auto_match_rate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="tiles" style={{ marginTop: 16 }}>
          <StatTile k="Calibration error (ECE)" v={e.ece_calibrated.toFixed(3)} n={`from ${e.ece_raw.toFixed(3)} raw`} />
          <StatTile k="Adversarial survival" v={`${e.redteam_survived}/${e.redteam_total}`} n="own red-team suite" />
          <StatTile
            k="False auto-match"
            v={overall ? pct(overall.false_auto_match_rate) : "—"}
            n="holdout" accent="good"
          />
        </div>
        <p className="note">
          The red-team suite is this project’s own construction, not an independent corpus — and one
          of its four attack categories still succeeds 12 times in 15. That gap is a structural limit
          of amount + date + narration matching, and is reported rather than hidden.
        </p>
      </div>
    </>
  );
}
