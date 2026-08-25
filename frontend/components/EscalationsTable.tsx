'use client';

import { useState } from 'react';
import type { EscalationsResponse, SignalLifecycle } from '@/lib/types';
import { usePolling } from '@/lib/usePolling';
import { relativeTime, carrierColor, carrierInitial } from '@/lib/format';
import Badge, { severityTone, severityLabel } from './Badge';
import SignalDrawer from './SignalDrawer';
import { EmptyIcon } from './icons';

const PRIORITIES = [
  { value: null, label: 'All priorities' },
  { value: 'P1', label: 'P1 Critical' },
  { value: 'P2', label: 'P2 High' },
  { value: 'P3', label: 'P3 Standard' },
];

export default function EscalationsTable({
  initialData = null,
}: {
  initialData?: EscalationsResponse | null;
}) {
  const [priority, setPriority] = useState<string | null>(null);
  const [showAcked, setShowAcked] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selected, setSelected] = useState<SignalLifecycle | null>(null);
  const [drawerLoading, setDrawerLoading] = useState(false);

  const params = new URLSearchParams();
  if (priority) params.set('priority', priority);
  if (!showAcked) params.set('acknowledged', 'false');
  // initialData was fetched server-side for the default filters (no
  // priority, unacknowledged only) — only valid as first-paint data while
  // those are still the active filters.
  const isDefaultFilters = priority === null && !showAcked;
  const { data, error, loading } = usePolling<EscalationsResponse>(
    `/escalations?${params.toString()}`,
    5000,
    isDefaultFilters ? initialData : null
  );
  const briefs = data?.briefs ?? [];

  async function openSignal(signalId: string) {
    setSelectedId(signalId);
    setDrawerLoading(true);
    try {
      const res = await fetch(`/api/proxy/signals/${signalId}/lifecycle`, { cache: 'no-store' });
      if (res.ok) {
        setSelected((await res.json()) as SignalLifecycle);
      }
    } finally {
      setDrawerLoading(false);
    }
  }

  return (
    <>
      <div className="filter-row">
        {PRIORITIES.map((p) => (
          <button
            key={p.label}
            type="button"
            className={`filter-pill${priority === p.value ? ' active' : ''}`}
            onClick={() => setPriority(p.value)}
          >
            {p.label}
          </button>
        ))}
        <div className="filter-spacer" />
        <button
          type="button"
          className={`filter-pill${showAcked ? ' active' : ''}`}
          onClick={() => setShowAcked((v) => !v)}
        >
          {showAcked ? 'Showing all' : 'Unacknowledged only'}
        </button>
      </div>

      <div className="panel">
        <div className="esc-head">
          <div></div>
          <div>Escalation</div>
          <div>Carrier</div>
          <div>Priority</div>
          <div style={{ textAlign: 'right' }}>Raised</div>
        </div>

        {loading && briefs.length === 0 && <div className="empty-state">Loading escalations…</div>}

        {!loading && !error && briefs.length === 0 && (
          <div className="empty-state">
            <EmptyIcon />
            <div>
              {showAcked ? 'No escalations match these filters.' : 'Nothing unacknowledged right now.'}
            </div>
          </div>
        )}

        {error && briefs.length === 0 && (
          <div className="empty-state">Couldn&apos;t reach the gateway — {error}</div>
        )}

        {briefs.map((brief) => (
          <button
            key={brief.signal_id}
            type="button"
            className={`esc-row${selectedId === brief.signal_id ? ' -selected' : ''}`}
            onClick={() => openSignal(brief.signal_id)}
          >
            <div className="carrier-avatar" style={{ background: carrierColor(brief.carrier) }}>
              {carrierInitial(brief.carrier)}
            </div>
            <div className="ticket-main">
              <div className="ticket-title">{brief.summary}</div>
              <div className="ticket-meta">
                {brief.category} · <span className="mono">{brief.signal_id.slice(0, 8)}</span>
              </div>
            </div>
            <div>
              <Badge tone="neutral">{brief.carrier}</Badge>
            </div>
            <div>
              {brief.acknowledged ? (
                <Badge tone="success" dot>
                  Acknowledged
                </Badge>
              ) : (
                <Badge tone={severityTone(brief.severity)} dot>
                  {severityLabel(brief.severity)}
                </Badge>
              )}
            </div>
            <div className="time-cell">{relativeTime(brief.escalated_at)}</div>
          </button>
        ))}
      </div>

      {selectedId && !drawerLoading && selected && (
        <SignalDrawer
          signal={selected}
          onClose={() => {
            setSelectedId(null);
            setSelected(null);
          }}
        />
      )}
    </>
  );
}
