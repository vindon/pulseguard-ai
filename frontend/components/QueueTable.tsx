'use client';

import { useState } from 'react';
import type { PipelineSignalsResponse, SignalLifecycle } from '@/lib/types';
import { usePolling } from '@/lib/usePolling';
import { relativeTime, carrierColor, carrierInitial, sourceLabel } from '@/lib/format';
import Badge, { severityTone, severityLabel, stageTone, stageLabel } from './Badge';
import AgentTrail from './AgentTrail';
import SignalDrawer from './SignalDrawer';
import { ChevronRightIcon, EmptyIcon } from './icons';

const SOURCES = [
  { value: null, label: 'All feeds' },
  { value: 'x', label: 'X' },
  { value: 'reddit', label: 'Reddit' },
  { value: 'google_play', label: 'Google Play' },
  { value: 'app_store', label: 'App Store' },
  { value: 'trustpilot', label: 'Trustpilot' },
  { value: 'quora', label: 'Quora' },
];

export default function QueueTable({
  hours = 24,
  limit,
  showFilters = false,
  initialData = null,
}: {
  hours?: number;
  limit?: number;
  showFilters?: boolean;
  initialData?: PipelineSignalsResponse | null;
}) {
  const [source, setSource] = useState<string | null>(null);
  const path = `/pipeline/signals?hours=${hours}${source ? `&source=${source}` : ''}`;
  // initialData was fetched server-side for the unfiltered path — only
  // valid as the first-paint value while no source filter is applied yet.
  const { data, error, loading } = usePolling<PipelineSignalsResponse>(
    path,
    5000,
    source === null ? initialData : null
  );
  const [selected, setSelected] = useState<SignalLifecycle | null>(null);

  const signals = (data?.signals ?? []).slice(0, limit);

  return (
    <>
      {showFilters && (
        <div className="filter-row">
          {SOURCES.map((s) => (
            <button
              key={s.label}
              type="button"
              className={`filter-pill${source === s.value ? ' active' : ''}`}
              onClick={() => setSource(s.value)}
            >
              {s.label}
            </button>
          ))}
          <div className="filter-spacer" />
          <span className="filter-pill">Last {hours}h</span>
        </div>
      )}
      <div className="panel">
        <div className="queue-head">
          <div></div>
          <div>Signal</div>
          <div>Carrier</div>
          <div>Agent trail</div>
          <div>Priority</div>
          <div style={{ textAlign: 'right' }}>Time</div>
          <div></div>
        </div>

        {loading && signals.length === 0 && (
          <div className="empty-state">Loading live signals…</div>
        )}

        {!loading && !error && signals.length === 0 && (
          <div className="empty-state">
            <EmptyIcon />
            <div>No signals in the last {hours}h. Send a test signal to see the pipeline run.</div>
          </div>
        )}

        {error && signals.length === 0 && (
          <div className="empty-state">Couldn&apos;t reach the gateway — {error}</div>
        )}

        {signals.map((signal) => {
          const sentinel = signal.sentinel;
          const carrier = sentinel?.carrier ?? null;
          return (
            <button
              key={signal.signal_id}
              type="button"
              className={`queue-row${selected?.signal_id === signal.signal_id ? ' -selected' : ''}`}
              onClick={() => setSelected(signal)}
            >
              <div
                className="carrier-avatar"
                style={{ background: carrierColor(carrier) }}
              >
                {carrierInitial(carrier)}
              </div>
              <div className="ticket-main">
                <div className="ticket-title">
                  {sentinel?.content_preview || '(content pending validation)'}
                </div>
                <div className="ticket-meta">
                  {signal.triage?.category ?? (sentinel ? sourceLabel(sentinel.source) : '—')} ·{' '}
                  <span className="mono">{signal.signal_id.slice(0, 8)}</span>
                </div>
              </div>
              <div>
                <Badge tone="neutral">{carrier ?? 'Unknown'}</Badge>
              </div>
              <AgentTrail signal={signal} />
              <div>
                {signal.stage === 'escalated' || signal.stage === 'resolved' ? (
                  <Badge tone={signal.stage === 'resolved' ? 'success' : severityTone(signal.severity)} dot>
                    {signal.stage === 'resolved' ? 'Resolved' : severityLabel(signal.severity)}
                  </Badge>
                ) : (
                  <Badge tone={stageTone(signal.stage)}>{stageLabel(signal.stage)}</Badge>
                )}
              </div>
              <div className="time-cell">
                {sentinel?.posted_at ? relativeTime(sentinel.posted_at) : '—'}
              </div>
              <div className="chev">
                <ChevronRightIcon />
              </div>
            </button>
          );
        })}
      </div>

      {selected && <SignalDrawer signal={selected} onClose={() => setSelected(null)} />}
    </>
  );
}
