import type { DataSource, MatchSignal, PolicyCheck, QueueItem } from "./types";

export const rupees = (paise: number) =>
  `₹${(paise / 100).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export const pct = (v: number, digits = 1) => `${(v * 100).toFixed(digits)}%`;

export const shortDate = (iso: string) => iso.slice(0, 10);

/** The provenance chip. This is a load-bearing piece of honesty, not decoration: no session in
 *  this project has ever had Razorpay credentials, so the UI must never imply a live connection.
 *  See REAL_VS_SIMULATED.md. */
export function ProvenanceChip({ text }: { text: string }) {
  return (
    <span className="chip" title="See REAL_VS_SIMULATED.md — every data source in this project is synthetic.">
      <span className="dot synthetic" />
      {text}
    </span>
  );
}

/** Where the numbers on screen came from. Snapshot data is never labelled live. */
export function SourceChip({ source, attempt }: { source: DataSource; attempt: number }) {
  if (source === "live") {
    return (<span className="chip"><span className="dot live" />Live API</span>);
  }
  if (source === "waking") {
    return (
      <span className="chip" title="The backend sleeps on its free tier; waking it can take up to a minute.">
        <span className="dot waking" />Snapshot · waking backend{attempt > 1 ? ` (${attempt})` : ""}
      </span>
    );
  }
  if (source === "snapshot") {
    return (
      <span className="chip" title="Committed output from a real pipeline run. The backend is not reachable.">
        <span className="dot snapshot" />Snapshot · backend unreachable
      </span>
    );
  }
  return (<span className="chip"><span className="dot snapshot" />Loading…</span>);
}

export function ActionBadge({ action }: { action: string }) {
  const cls = action === "AUTO_POST" ? "auto" : action === "FLAG_ANOMALY" ? "anomaly" : "escalate";
  const label = action === "AUTO_POST" ? "AUTO-POST" : action === "FLAG_ANOMALY" ? "ANOMALY" : "REVIEW";
  return <span className={`badge ${cls}`}>{label}</span>;
}

export function StatTile({
  k, v, n, accent,
}: { k: string; v: string; n?: string; accent?: "good" | "critical" }) {
  return (
    <div className={`tile${accent ? ` accent-${accent}` : ""}`}>
      <div className="k">{k}</div>
      <div className="v">{v}</div>
      {n && <div className="n">{n}</div>}
    </div>
  );
}

export function SignalList({ signals }: { signals: MatchSignal[] }) {
  const icon = (s: string) => (s === "pass" ? "✓" : s === "warn" ? "!" : "✕");
  return (
    <div>
      {signals.map((s, i) => (
        <div className={`signal ${s.status}`} key={`${s.label}-${i}`}>
          <span className="icon" aria-hidden>{icon(s.status)}</span>
          <span className="body">
            <div className="label">
              {s.label} <span className="val">— {s.value}</span>
            </div>
            {s.detail && <div className="detail">{s.detail}</div>}
          </span>
        </div>
      ))}
    </div>
  );
}

/** Calibrated confidence against the cost-derived threshold. A single bar with the threshold
 *  marked is the honest form here: the comparison IS the story. */
export function ConfidenceMeter({ value, threshold }: { value: number; threshold: number }) {
  const cleared = value >= threshold;
  return (
    <div className="meter">
      <div className="meter-track">
        <div
          className="meter-fill"
          style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%`, background: cleared ? "var(--good)" : "var(--serious)" }}
        />
        <div className="meter-thresh" style={{ left: `${threshold * 100}%` }} title={`threshold ${threshold.toFixed(2)}`} />
      </div>
      <div className="meter-legend">
        <span>calibrated {value.toFixed(3)}</span>
        <span>threshold {threshold.toFixed(2)}</span>
      </div>
    </div>
  );
}

export function PolicyPanel({ policy }: { policy: PolicyCheck[] }) {
  return (
    <div>
      <div className="policy-row policy-head">
        <span>Clause</span>
        <span className="req">Required</span>
        <span className="act">Actual</span>
        <span />
      </div>
      {policy.map((c) => (
        <div className="policy-row" key={c.label}>
          <span>{c.label}</span>
          <span className="req">{c.required}</span>
          <span className="act">{c.actual}</span>
          <span className={`mark ${c.passed ? "ok" : "no"}`} aria-label={c.passed ? "pass" : "fail"}>
            {c.passed ? "✓" : "✕"}
          </span>
        </div>
      ))}
    </div>
  );
}

export function QueueTable({
  items, onSelect,
}: { items: QueueItem[]; onSelect: (id: string) => void }) {
  if (items.length === 0) return <div className="empty">No decisions match these filters.</div>;
  return (
    <div className="scroll">
      <table>
        <thead>
          <tr>
            <th>Bank line</th>
            <th>Value date</th>
            <th>Amount</th>
            <th>Resolver</th>
            <th>Confidence</th>
            <th>Reason</th>
            <th>Decision</th>
          </tr>
        </thead>
        <tbody>
          {items.map((i) => (
            <tr className="clickable" key={i.bank_line_id} onClick={() => onSelect(i.bank_line_id)}>
              <td className="mono">{i.bank_line_id}</td>
              <td>{shortDate(i.value_date)}</td>
              <td>{rupees(i.credit_paise)}</td>
              <td>{i.resolver}</td>
              <td>{i.calibrated_confidence.toFixed(3)}</td>
              <td className="mono">{i.reason_code ?? "—"}</td>
              <td><ActionBadge action={i.action} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
