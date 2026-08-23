// Inline-SVG charts. Colors come from the validated categorical slots 1-3 and the status
// palette (see styles.css); every bar carries a direct value label, which is also what
// discharges the light-mode contrast relief rule for the aqua slot.
//
// Note on the D1 chart: invocation rate and precision are NOT plotted on one pair of axes.
// A dual-axis chart is the single most common charting mistake -- two measures on two y-scales
// invite a comparison the geometry does not support. They are two small multiples instead.

import type { AblationRow, RuleLearningRow } from "./types";

const PAD = { top: 16, right: 14, bottom: 30, left: 40 };

function Grid({
  w, h, ticks, max, rightPad = PAD.right,
}: { w: number; h: number; ticks: number[]; max: number; rightPad?: number }) {
  return (
    <g>
      {ticks.map((t) => {
        const y = PAD.top + (1 - t / max) * (h - PAD.top - PAD.bottom);
        return (
          <g key={t}>
            <line x1={PAD.left} x2={w - rightPad} y1={y} y2={y} stroke="var(--grid)" strokeWidth={1} />
            <text x={PAD.left - 7} y={y + 3.5} textAnchor="end" fontSize={10} fill="var(--text-muted)">
              {t}
            </text>
          </g>
        );
      })}
    </g>
  );
}

/** Grouped bars: three configurations per difficulty stratum. */
export function AblationChart({ rows }: { rows: AblationRow[] }) {
  const data = rows.filter((r) => r.stratum !== "Overall");
  const w = 640;
  const h = 260;
  const innerW = w - PAD.left - PAD.right;
  const innerH = h - PAD.top - PAD.bottom;
  const groupW = innerW / data.length;
  const barW = Math.min(22, (groupW - 14) / 3);
  const series: Array<{ key: keyof AblationRow; label: string; color: string }> = [
    { key: "rules_only_f1", label: "Rules-only", color: "var(--series-1)" },
    { key: "hybrid_f1", label: "Hybrid", color: "var(--series-2)" },
    { key: "llm_only_f1", label: "LLM-only", color: "var(--series-3)" },
  ];

  return (
    <>
      <div className="legend">
        {series.map((s) => (
          <span key={s.label}>
            <span className="swatch" style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
      </div>
      <div className="scroll">
        <svg viewBox={`0 0 ${w} ${h}`} width="100%" role="img" aria-label="F1 by difficulty stratum for each configuration">
          <Grid w={w} h={h} ticks={[0, 0.5, 1]} max={1} />
          {data.map((row, gi) => {
            const gx = PAD.left + gi * groupW;
            return (
              <g key={row.stratum}>
                {series.map((s, si) => {
                  const v = row[s.key] as number;
                  const bh = v * innerH;
                  const x = gx + groupW / 2 - (barW * 3 + 4) / 2 + si * (barW + 2);
                  const y = PAD.top + innerH - bh;
                  return (
                    <g key={s.label}>
                      {bh > 0 && <rect x={x} y={y} width={barW} height={bh} rx={4} fill={s.color} />}
                      <text
                        x={x + barW / 2}
                        y={bh > 0 ? y - 4 : PAD.top + innerH - 4}
                        textAnchor="middle"
                        fontSize={9.5}
                        fill="var(--text-secondary)"
                      >
                        {v.toFixed(2)}
                      </text>
                    </g>
                  );
                })}
                <text x={gx + groupW / 2} y={h - 12} textAnchor="middle" fontSize={10.5} fill="var(--text-secondary)">
                  {row.stratum}
                </text>
                <text x={gx + groupW / 2} y={h - 2} textAnchor="middle" fontSize={9.5} fill="var(--text-muted)">
                  n={row.n}
                </text>
              </g>
            );
          })}
          <line
            x1={PAD.left} x2={w - PAD.right} y1={PAD.top + innerH} y2={PAD.top + innerH}
            stroke="var(--axis)" strokeWidth={1}
          />
        </svg>
      </div>
    </>
  );
}

/** One small multiple. Two of these side by side replace what would otherwise be a dual axis. */
function LineMultiple({
  title, rows, accessor, format, color, max,
}: {
  title: string;
  rows: RuleLearningRow[];
  accessor: (r: RuleLearningRow) => number;
  format: (v: number) => string;
  color: string;
  max: number;
}) {
  const w = 300;
  const h = 190;
  // Wider right margin than the shared PAD: the last point's label sits at the plot edge and
  // was clipping. End points anchor inward for the same reason -- a centred label on the first
  // point overhangs the y-axis and collides with its top tick.
  const rightPad = 26;
  const innerW = w - PAD.left - rightPad;
  const innerH = h - PAD.top - PAD.bottom;
  const step = rows.length > 1 ? innerW / (rows.length - 1) : 0;
  const pts = rows.map((r, i) => ({
    x: PAD.left + i * step,
    y: PAD.top + (1 - accessor(r) / max) * innerH,
    v: accessor(r),
    batch: r.batch,
    anchor: (i === 0 ? "start" : i === rows.length - 1 ? "end" : "middle") as "start" | "end" | "middle",
  }));

  return (
    <div>
      <h3>{title}</h3>
      <svg viewBox={`0 0 ${w} ${h}`} width="100%" role="img" aria-label={title}>
        <Grid w={w} h={h} ticks={[0, max / 2, max]} max={max} rightPad={rightPad} />
        <polyline
          points={pts.map((p) => `${p.x},${p.y}`).join(" ")}
          fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"
        />
        {pts.map((p) => (
          <g key={p.batch}>
            <circle cx={p.x} cy={p.y} r={4.5} fill={color} stroke="var(--surface-1)" strokeWidth={2} />
            <text
              x={p.x + (p.anchor === "start" ? 7 : p.anchor === "end" ? -7 : 0)}
              y={p.y - 11}
              textAnchor={p.anchor}
              fontSize={10}
              fill="var(--text-secondary)"
            >
              {format(p.v)}
            </text>
            <text x={p.x} y={h - 10} textAnchor={p.anchor} fontSize={10} fill="var(--text-muted)">
              batch {p.batch}
            </text>
          </g>
        ))}
        <line
          x1={PAD.left} x2={w - rightPad} y1={PAD.top + innerH} y2={PAD.top + innerH}
          stroke="var(--axis)" strokeWidth={1}
        />
      </svg>
    </div>
  );
}

export function RuleLearningCharts({ rows }: { rows: RuleLearningRow[] }) {
  return (
    <div className="grid2">
      <LineMultiple
        title="LLM invocation rate (%)"
        rows={rows}
        accessor={(r) => r.invocation_rate * 100}
        format={(v) => `${v.toFixed(1)}%`}
        color="var(--series-2)"
        max={25}
      />
      <LineMultiple
        title="Precision on auto-posted (%)"
        rows={rows}
        accessor={(r) => r.precision_auto_post * 100}
        format={(v) => `${v.toFixed(1)}%`}
        color="var(--series-1)"
        max={100}
      />
    </div>
  );
}
