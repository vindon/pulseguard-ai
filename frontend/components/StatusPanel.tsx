'use client';

import type { AdapterStatusResponse, OrchestratorStatus } from '@/lib/types';
import { usePolling } from '@/lib/usePolling';
import { relativeTime, sourceLabel } from '@/lib/format';

function statusDotClass(status: string): string {
  if (status === 'HEALTHY') return '-healthy';
  if (status === 'DEGRADED') return '-degraded';
  return '-down';
}

export default function StatusPanel({
  initialAdapters = null,
  initialOrchestrator = null,
}: {
  initialAdapters?: AdapterStatusResponse | null;
  initialOrchestrator?: OrchestratorStatus | null;
}) {
  const adapters = usePolling<AdapterStatusResponse>('/adapters/status', 10000, initialAdapters);
  const orchestrator = usePolling<OrchestratorStatus>(
    '/orchestrator/status',
    10000,
    initialOrchestrator
  );

  const adapterEntries = Object.entries(adapters.data?.adapters ?? {});
  const breakerEntries = Object.entries(orchestrator.data?.adapter_circuit_breakers ?? {});

  return (
    <>
      <div className="stat-row">
        <div className="stat-card">
          <div className="stat-label">Orchestrator</div>
          <div className="stat-value display">
            {orchestrator.data ? (orchestrator.data.running ? 'Running' : 'Stopped') : '—'}
          </div>
          <div className="stat-sub">
            {orchestrator.data?.global_circuit_open ? 'Global circuit open' : 'All systems normal'}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Unacknowledged queue</div>
          <div className="stat-value display">{orchestrator.data?.queue_depth_unacknowledged ?? '—'}</div>
          <div className="stat-sub">escalations waiting</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">X API usage</div>
          <div className="stat-value display">
            {orchestrator.data ? orchestrator.data.x_monthly_reads.toLocaleString() : '—'}
          </div>
          <div className="stat-sub">
            of {orchestrator.data?.x_monthly_cap.toLocaleString() ?? '—'} monthly reads
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Adapters reporting</div>
          <div className="stat-value display">{adapterEntries.length || '—'}</div>
          <div className="stat-sub">of 6 configured</div>
        </div>
      </div>

      <div className="content-head" style={{ marginBottom: 12 }}>
        <div className="page-sub" style={{ marginTop: 0, fontWeight: 600, color: 'var(--ink)' }}>
          Feed adapters
        </div>
      </div>

      {adapterEntries.length === 0 ? (
        <div className="empty-state">
          {adapters.loading ? 'Loading adapter status…' : 'No adapter health reported yet.'}
        </div>
      ) : (
        <div className="status-grid" style={{ marginBottom: 26 }}>
          {adapterEntries.map(([name, health]) => (
            <div key={name} className="status-card">
              <div className="status-card-head">
                <span className="status-card-name">{sourceLabel(name)}</span>
                <span className={`status-dot ${statusDotClass(health.status)}`} title={health.status} />
              </div>
              <div className="status-meta">
                {health.last_successful_fetch
                  ? `Last fetch ${relativeTime(health.last_successful_fetch)}`
                  : 'Never fetched'}
              </div>
              {health.consecutive_errors > 0 && (
                <div className="status-meta" style={{ color: 'var(--critical)', marginTop: 3 }}>
                  {health.consecutive_errors} consecutive error{health.consecutive_errors === 1 ? '' : 's'}
                </div>
              )}
              {health.monthly_cap_limit !== null && health.monthly_cap_used !== null && (
                <div className="status-meta" style={{ marginTop: 3 }}>
                  {health.monthly_cap_used.toLocaleString()} / {health.monthly_cap_limit.toLocaleString()}{' '}
                  monthly cap
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="content-head" style={{ marginBottom: 12 }}>
        <div className="page-sub" style={{ marginTop: 0, fontWeight: 600, color: 'var(--ink)' }}>
          Circuit breakers
        </div>
      </div>

      {breakerEntries.length === 0 ? (
        <div className="empty-state">
          {orchestrator.loading ? 'Loading circuit breaker state…' : 'No circuit breaker data yet.'}
        </div>
      ) : (
        <div className="status-grid">
          {breakerEntries.map(([name, breaker]) => (
            <div key={name} className="status-card">
              <div className="status-card-head">
                <span className="status-card-name">{sourceLabel(name)}</span>
                <span
                  className={`status-dot ${breaker.state === 'closed' ? '-healthy' : breaker.state === 'half-open' ? '-degraded' : '-down'}`}
                  title={breaker.state}
                />
              </div>
              <div className="status-meta">
                {breaker.state === 'closed'
                  ? 'Closed — passing traffic'
                  : breaker.state === 'half-open'
                    ? 'Half-open — testing recovery'
                    : `Open since ${breaker.opened_at ? relativeTime(breaker.opened_at) : 'unknown'}`}
              </div>
              {breaker.consecutive_errors > 0 && (
                <div className="status-meta" style={{ marginTop: 3 }}>
                  {breaker.consecutive_errors} consecutive error{breaker.consecutive_errors === 1 ? '' : 's'}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
