// Talks to the LedgerGuard API, and survives it being asleep.
//
// The backend runs on a free container tier that sleeps after ~15 minutes idle; waking it can
// take the better part of a minute. So the load order is deliberate:
//
//   1. fetch the committed snapshot (static, same-origin, instant) -> render immediately
//   2. ping /healthz in parallel -> if it answers, swap to live data
//   3. if it doesn't, keep polling with backoff while the UI stays usable on the snapshot
//
// The UI never shows a blank page waiting on the backend, and never labels snapshot data as
// live. See eval/snapshot.py for why the fallback is generated rather than hand-written.

import type { AuditEvent, Dashboard, ExecuteResult, Investigation, QueueItem, Snapshot } from "../types";

const RAW_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
export const API_BASE = RAW_BASE.replace(/\/+$/, "");

/** Health check is short-timeout on purpose: a sleeping instance should fail fast so the UI can
 *  show "waking" and retry, rather than hanging on one long request. */
const HEALTH_TIMEOUT_MS = 4000;
const DATA_TIMEOUT_MS = 20000;

async function withTimeout(url: string, ms: number, init?: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ms);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

export async function loadSnapshot(): Promise<Snapshot> {
  const res = await fetch(`${import.meta.env.BASE_URL}snapshot.json`);
  if (!res.ok) throw new Error(`snapshot ${res.status}`);
  return res.json();
}

export async function pingHealth(): Promise<boolean> {
  try {
    const res = await withTimeout(`${API_BASE}/healthz`, HEALTH_TIMEOUT_MS);
    return res.ok;
  } catch {
    return false;
  }
}

export async function fetchDashboard(): Promise<Dashboard> {
  const res = await withTimeout(`${API_BASE}/api/v1/dashboard`, DATA_TIMEOUT_MS);
  if (!res.ok) throw new Error(`dashboard ${res.status}`);
  return res.json();
}

export async function fetchQueue(): Promise<QueueItem[]> {
  const res = await withTimeout(`${API_BASE}/api/v1/reconciliation?limit=2000`, DATA_TIMEOUT_MS);
  if (!res.ok) throw new Error(`reconciliation ${res.status}`);
  return (await res.json()).items;
}

export async function fetchInvestigation(id: string): Promise<Investigation> {
  const res = await withTimeout(`${API_BASE}/api/v1/reconciliation/${encodeURIComponent(id)}`, DATA_TIMEOUT_MS);
  if (!res.ok) throw new Error(`investigation ${res.status}`);
  return res.json();
}

export async function executeDecision(id: string): Promise<ExecuteResult> {
  const res = await withTimeout(
    `${API_BASE}/api/v1/reconciliation/${encodeURIComponent(id)}/execute`,
    DATA_TIMEOUT_MS,
    { method: "POST" },
  );
  if (!res.ok) throw new Error(`execute ${res.status}`);
  return res.json();
}

export async function fetchAudit(): Promise<AuditEvent[]> {
  const res = await withTimeout(`${API_BASE}/api/v1/audit`, DATA_TIMEOUT_MS);
  if (!res.ok) throw new Error(`audit ${res.status}`);
  return (await res.json()).events;
}

/** Poll /healthz with backoff until it answers or we give up. Resolves true once awake.
 *  Backoff rather than a tight loop: a cold container is not helped by being hammered. */
export async function waitForBackend(
  onAttempt: (attempt: number) => void,
  maxAttempts = 12,
): Promise<boolean> {
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    onAttempt(attempt);
    if (await pingHealth()) return true;
    const delay = Math.min(1000 * 2 ** (attempt - 1), 8000);
    await new Promise((r) => setTimeout(r, delay));
  }
  return false;
}
