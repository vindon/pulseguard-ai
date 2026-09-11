'use client';

import type { AdapterStatusResponse, OrchestratorStatus } from '@/lib/types';
import { usePolling } from '@/lib/usePolling';
import { relativeTime, sourceLabel } from '@/lib/format';
import StatCard from './StatCard';
import { Activity, ListTree, Gauge, Radio } from 'lucide-react';

type StatusKey = 'healthy' | 'degraded' | 'down';

const DOT_CLASSES: Record<StatusKey, string> = {
  healthy: 'bg-success',
  degraded: 'bg-warning',
  down: 'bg-critical',
};

function statusKey(status: string): StatusKey {
  if (status === 'HEALTHY') return 'healthy';
  if (status === 'DEGRADED') return 'degraded';
  return 'down';
}

export default function StatusPanel({
  initialAdapters = null,
  initialOrchestrator = null,
}: {
  initialAdapters?: AdapterStatusResponse | null;
  initialOrchestrator?: OrchestratorStatus | null;
}) {
  const adapters = usePolling<AdapterStatusResponse>('/adapters/status', 10000, initialAdapters);
  const orchestrator = usePolling<OrchestratorStatus>('/orchestrator/status', 10000, initialOrchestrator);

  const adapterEntries = Object.entries(adapters.data?.adapters ?? {});
  const breakerEntries = Object.entries(orchestrator.data?.adapter_circuit_breakers ?? {});

  return (
    <>
      <div className="mb-5 grid grid-cols-4 gap-3.5 max-[760px]:grid-cols-2">
        <StatCard
          label="Orchestrator"
          value={orchestrator.data ? (orchestrator.data.running ? 'Running' : 'Stopped') : '—'}
          sub={orchestrator.data?.global_circuit_open ? 'Global circuit open' : 'All systems normal'}
          subTone={orchestrator.data?.global_circuit_open ? 'critical' : 'success'}
          icon={<Activity className="h-3 w-3" />}
          iconTone="violet"
        />
        <StatCard
          label="Unacknowledged queue"
          value={orchestrator.data?.queue_depth_unacknowledged ?? '—'}
          sub="escalations waiting"
          icon={<ListTree className="h-3 w-3" />}
          iconTone="critical"
        />
        <StatCard
          label="X API usage"
          value={orchestrator.data ? orchestrator.data.x_monthly_reads.toLocaleString() : '—'}
          sub={`of ${orchestrator.data?.x_monthly_cap.toLocaleString() ?? '—'} monthly reads`}
          icon={<Gauge className="h-3 w-3" />}
          iconTone="teal"
        />
        <StatCard
          label="Adapters reporting"
          value={adapterEntries.length || '—'}
          sub="feeds configured"
          icon={<Radio className="h-3 w-3" />}
          iconTone="success"
        />
      </div>

      <div className="mb-3 text-[12px] font-semibold text-ink">Feed adapters</div>

      {adapterEntries.length === 0 ? (
        <div data-testid="empty-state" className="p-12 text-center text-muted">
          {adapters.loading ? 'Loading adapter status…' : 'No adapter health reported yet.'}
        </div>
      ) : (
        <div className="mb-6 grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3.5">
          {adapterEntries.map(([name, health]) => {
            const key = statusKey(health.status);
            return (
              <div
                key={name}
                data-testid="status-card"
                className="rounded-xl border border-border bg-surface p-4 shadow-[var(--shadow-card)]"
              >
                <div className="mb-2 flex items-center justify-between">
                  <span data-testid="status-card-name" className="text-[13.5px] font-bold capitalize">
                    {sourceLabel(name)}
                  </span>
                  <span
                    data-testid="status-dot"
                    data-status={key}
                    title={health.status}
                    className={`h-2 w-2 shrink-0 rounded-full ${DOT_CLASSES[key]}`}
                  />
                </div>
                <div className="text-[11.5px] text-muted">
                  {health.last_successful_fetch
                    ? `Last fetch ${relativeTime(health.last_successful_fetch)}`
                    : 'Never fetched'}
                </div>
                {health.consecutive_errors > 0 && (
                  <div className="mt-0.5 text-[11.5px] text-critical">
                    {health.consecutive_errors} consecutive error{health.consecutive_errors === 1 ? '' : 's'}
                  </div>
                )}
                {health.monthly_cap_limit !== null && health.monthly_cap_used !== null && (
                  <div className="mt-0.5 text-[11.5px] text-muted">
                    {health.monthly_cap_used.toLocaleString()} / {health.monthly_cap_limit.toLocaleString()} monthly
                    cap
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      <div className="mb-3 text-[12px] font-semibold text-ink">Circuit breakers</div>

      {breakerEntries.length === 0 ? (
        <div data-testid="empty-state" className="p-12 text-center text-muted">
          {orchestrator.loading ? 'Loading circuit breaker state…' : 'No circuit breaker data yet.'}
        </div>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3.5">
          {breakerEntries.map(([name, breaker]) => {
            const key: StatusKey = breaker.state === 'closed' ? 'healthy' : breaker.state === 'half-open' ? 'degraded' : 'down';
            return (
              <div
                key={name}
                data-testid="status-card"
                className="rounded-xl border border-border bg-surface p-4 shadow-[var(--shadow-card)]"
              >
                <div className="mb-2 flex items-center justify-between">
                  <span data-testid="status-card-name" className="text-[13.5px] font-bold capitalize">
                    {sourceLabel(name)}
                  </span>
                  <span
                    data-testid="status-dot"
                    data-status={key}
                    title={breaker.state}
                    className={`h-2 w-2 shrink-0 rounded-full ${DOT_CLASSES[key]}`}
                  />
                </div>
                <div className="text-[11.5px] text-muted">
                  {breaker.state === 'closed'
                    ? 'Closed — passing traffic'
                    : breaker.state === 'half-open'
                      ? 'Half-open — testing recovery'
                      : `Open since ${breaker.opened_at ? relativeTime(breaker.opened_at) : 'unknown'}`}
                </div>
                {breaker.consecutive_errors > 0 && (
                  <div className="mt-0.5 text-[11.5px] text-muted">
                    {breaker.consecutive_errors} consecutive error{breaker.consecutive_errors === 1 ? '' : 's'}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}
