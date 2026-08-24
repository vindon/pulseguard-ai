'use client';

import type { PipelineSignalsResponse } from '@/lib/types';
import { usePolling } from '@/lib/usePolling';

function avgTriageSeconds(signals: PipelineSignalsResponse['signals']): number | null {
  const deltas = signals
    .filter((s) => s.sentinel && s.triage)
    .map((s) => {
      const validated = new Date(s.sentinel!.validated_at).getTime();
      const triaged = new Date(s.triage!.triaged_at).getTime();
      return (triaged - validated) / 1000;
    })
    .filter((d) => Number.isFinite(d) && d >= 0);
  if (deltas.length === 0) return null;
  return deltas.reduce((a, b) => a + b, 0) / deltas.length;
}

export default function OverviewStats() {
  const { data } = usePolling<PipelineSignalsResponse>('/pipeline/signals?hours=24', 5000);
  const signals = data?.signals ?? [];

  const open = signals.filter((s) => s.stage !== 'resolved').length;
  const resolved = signals.filter((s) => s.stage === 'resolved').length;
  const escalated = signals.filter((s) => s.stage === 'escalated');
  const p1 = escalated.filter((s) => s.severity === 'P1').length;
  const resolvedPct = signals.length > 0 ? Math.round((resolved / signals.length) * 100) : null;
  const avgTriage = avgTriageSeconds(signals);

  return (
    <div className="stat-row">
      <div className="stat-card">
        <div className="stat-label">Open signals</div>
        <div className="stat-value display">{signals.length > 0 ? open : '—'}</div>
        <div className="stat-sub">last 24h</div>
      </div>
      <div className="stat-card">
        <div className="stat-label">Auto-resolved</div>
        <div className="stat-value display">{resolvedPct !== null ? `${resolvedPct}%` : '—'}</div>
        <div className="stat-sub">of triaged signals</div>
      </div>
      <div className="stat-card">
        <div className="stat-label">Escalated (P1)</div>
        <div className="stat-value display">{p1}</div>
        <div className="stat-sub">{escalated.length} escalated total</div>
      </div>
      <div className="stat-card">
        <div className="stat-label">Avg. time to triage</div>
        <div className="stat-value display">{avgTriage !== null ? `${avgTriage.toFixed(1)}s` : '—'}</div>
        <div className="stat-sub">Sentinel → Triage</div>
      </div>
    </div>
  );
}
