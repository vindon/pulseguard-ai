'use client';

import type { PipelineSignalsResponse } from '@/lib/types';
import { usePolling } from '@/lib/usePolling';
import StatCard from './StatCard';
import { List, TriangleAlert, CircleCheck, Activity } from 'lucide-react';

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

export default function OverviewStats({
  initialData = null,
}: {
  initialData?: PipelineSignalsResponse | null;
}) {
  const { data } = usePolling<PipelineSignalsResponse>('/pipeline/signals?hours=24', 5000, initialData);
  const signals = data?.signals ?? [];

  const open = signals.filter((s) => s.stage !== 'resolved').length;
  const resolved = signals.filter((s) => s.stage === 'resolved').length;
  const escalated = signals.filter((s) => s.stage === 'escalated');
  const p1 = escalated.filter((s) => s.severity === 'P1').length;
  const resolvedPct = signals.length > 0 ? Math.round((resolved / signals.length) * 100) : null;
  const avgTriage = avgTriageSeconds(signals);

  return (
    <div className="mb-5 grid grid-cols-4 gap-3.5 max-[760px]:grid-cols-2">
      <StatCard
        label="Open signals"
        value={signals.length > 0 ? open : '—'}
        sub="last 24h"
        icon={<List className="h-3 w-3" />}
        iconTone="violet"
      />
      <StatCard
        label="Auto-resolved"
        value={resolvedPct !== null ? `${resolvedPct}%` : '—'}
        sub="of triaged signals"
        icon={<CircleCheck className="h-3 w-3" />}
        iconTone="success"
      />
      <StatCard
        label="Escalated (P1)"
        value={p1}
        sub={`${escalated.length} escalated total`}
        icon={<TriangleAlert className="h-3 w-3" />}
        iconTone="critical"
      />
      <StatCard
        label="Avg. time to triage"
        value={avgTriage !== null ? `${avgTriage.toFixed(1)}s` : '—'}
        sub="Sentinel → Triage"
        icon={<Activity className="h-3 w-3" />}
        iconTone="teal"
      />
    </div>
  );
}
