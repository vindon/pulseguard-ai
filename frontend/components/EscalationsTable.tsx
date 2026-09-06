'use client';

import { useState } from 'react';
import type { EscalationsResponse, SignalLifecycle } from '@/lib/types';
import { usePolling } from '@/lib/usePolling';
import { relativeTime, carrierColor, carrierInitial } from '@/lib/format';
import Badge, { severityTone, severityLabel } from './Badge';
import SignalDrawer from './SignalDrawer';
import { Inbox } from 'lucide-react';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { Button } from '@/components/ui/button';

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
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <ToggleGroup
          type="single"
          value={priority ?? 'all'}
          onValueChange={(v) => setPriority(v === 'all' || !v ? null : v)}
          className="flex-wrap justify-start gap-2"
        >
          {PRIORITIES.map((p) => (
            <ToggleGroupItem
              key={p.label}
              value={p.value ?? 'all'}
              className="rounded-full border border-border px-3 py-1.5 text-[12.5px] font-semibold text-muted data-[state=on]:bg-ink data-[state=on]:text-bg"
            >
              {p.label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        <div className="flex-1" />
        <Button
          type="button"
          variant="outline"
          className="rounded-full px-3 py-1.5 text-[12.5px] font-semibold"
          onClick={() => setShowAcked((v) => !v)}
        >
          {showAcked ? 'Showing all' : 'Unacknowledged only'}
        </Button>
      </div>

      <div className="overflow-hidden rounded-[13px] border border-border bg-surface shadow-[var(--shadow-card)]">
        <div className="grid grid-cols-[28px_1.4fr_110px_130px_100px] gap-3.5 border-b border-border px-4 py-2.5 text-[10px] font-bold uppercase tracking-wide text-muted">
          <div></div>
          <div>Escalation</div>
          <div>Carrier</div>
          <div>Priority</div>
          <div className="text-right">Raised</div>
        </div>

        {loading && briefs.length === 0 && (
          <div data-testid="empty-state" className="p-14 text-center text-muted">
            Loading escalations…
          </div>
        )}

        {!loading && !error && briefs.length === 0 && (
          <div data-testid="empty-state" className="p-14 text-center text-muted">
            <Inbox className="mx-auto mb-3 h-8 w-8 opacity-50" />
            <div>{showAcked ? 'No escalations match these filters.' : 'Nothing unacknowledged right now.'}</div>
          </div>
        )}

        {error && briefs.length === 0 && (
          <div data-testid="empty-state" className="p-14 text-center text-muted">
            Couldn&apos;t reach the gateway — {error}
          </div>
        )}

        {briefs.map((brief) => (
          <button
            key={brief.signal_id}
            type="button"
            data-testid="escalation-row"
            className={`grid w-full grid-cols-[28px_1.4fr_110px_130px_100px] items-center gap-3.5 border-b border-border px-4 py-[11px] text-left text-[12.5px] last:border-b-0 hover:bg-neutral-tint ${
              selectedId === brief.signal_id ? 'bg-gradient-to-r from-brand-tint to-jewel-violet-tint' : ''
            }`}
            onClick={() => openSignal(brief.signal_id)}
          >
            <div
              className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-white"
              style={{ background: carrierColor(brief.carrier) }}
            >
              {carrierInitial(brief.carrier)}
            </div>
            <div className="min-w-0">
              <div className="truncate text-[12.5px] font-semibold">{brief.summary}</div>
              <div className="mt-0.5 text-[10.5px] text-muted">
                {brief.category} · <span className="font-mono">{brief.signal_id.slice(0, 8)}</span>
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
            <div className="text-right text-[12px] tabular-nums text-muted">{relativeTime(brief.escalated_at)}</div>
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
