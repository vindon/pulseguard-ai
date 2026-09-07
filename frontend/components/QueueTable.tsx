'use client';

import { useState } from 'react';
import type { PipelineSignalsResponse, SignalLifecycle } from '@/lib/types';
import { usePolling } from '@/lib/usePolling';
import { relativeTime, carrierColor, carrierInitial, sourceLabel } from '@/lib/format';
import Badge, { severityTone, severityLabel, stageTone, stageLabel } from './Badge';
import CategoryChip from './CategoryChip';
import AgentTrail from './AgentTrail';
import SignalDrawer from './SignalDrawer';
import { ChevronRight, Inbox } from 'lucide-react';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';

const SOURCES = [
  { value: null, label: 'All feeds' },
  { value: 'x', label: 'X' },
  { value: 'reddit', label: 'Reddit' },
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
        <ToggleGroup
          type="single"
          value={source ?? 'all'}
          onValueChange={(v) => setSource(v === 'all' || !v ? null : v)}
          className="mb-4 flex-wrap justify-start gap-2"
        >
          {SOURCES.map((s) => (
            <ToggleGroupItem
              key={s.label}
              value={s.value ?? 'all'}
              className="rounded-full border border-border px-3 py-1.5 text-[12.5px] font-semibold text-muted data-[state=on]:bg-ink data-[state=on]:text-bg"
            >
              {s.label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      )}
      <div className="overflow-hidden rounded-[13px] border border-border bg-surface shadow-[var(--shadow-card)]">
        <div className="grid grid-cols-[28px_1.3fr_96px_150px_96px_84px_20px] max-[840px]:grid-cols-[28px_1fr_90px_26px] gap-3.5 border-b border-border px-4 py-2.5 text-[10px] font-bold uppercase tracking-wide text-muted">
          <div></div>
          <div>Signal</div>
          <div>Carrier</div>
          <div className="max-[840px]:hidden">Agent trail</div>
          <div className="text-right max-[840px]:hidden">Priority</div>
          <div className="text-right">Time</div>
          <div></div>
        </div>

        {loading && signals.length === 0 && (
          <div data-testid="empty-state" className="p-14 text-center text-muted">
            Loading live signals…
          </div>
        )}

        {!loading && !error && signals.length === 0 && (
          <div data-testid="empty-state" className="p-14 text-center text-muted">
            <Inbox className="mx-auto mb-3 h-8 w-8 opacity-50" />
            <div>No signals in the last {hours}h. Send a test signal to see the pipeline run.</div>
          </div>
        )}

        {error && signals.length === 0 && (
          <div data-testid="empty-state" className="p-14 text-center text-muted">
            Couldn&apos;t reach the gateway — {error}
          </div>
        )}

        {signals.map((signal) => {
          const sentinel = signal.sentinel;
          const carrier = sentinel?.carrier ?? null;
          return (
            <button
              key={signal.signal_id}
              type="button"
              data-testid="queue-row"
              className={`grid w-full grid-cols-[28px_1.3fr_96px_150px_96px_84px_20px] max-[840px]:grid-cols-[28px_1fr_90px_26px] items-center gap-3.5 border-b border-border px-4 py-[11px] text-left text-[12.5px] last:border-b-0 hover:bg-neutral-tint ${
                selected?.signal_id === signal.signal_id
                  ? 'bg-gradient-to-r from-brand-tint to-jewel-violet-tint'
                  : ''
              }`}
              onClick={() => setSelected(signal)}
            >
              <div
                className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-white"
                style={{ background: carrierColor(carrier) }}
              >
                {carrierInitial(carrier)}
              </div>
              <div className="min-w-0">
                <div className="truncate text-[12.5px] font-semibold">
                  {sentinel?.content_preview || '(content pending validation)'}
                </div>
                <div className="mt-0.5 flex items-center gap-1.5 text-[10.5px] text-muted">
                  <CategoryChip
                    category={signal.triage?.category ?? (sentinel ? sourceLabel(sentinel.source) : 'Uncategorised')}
                  />
                  <span className="font-mono">{signal.signal_id.slice(0, 8)}</span>
                </div>
              </div>
              <div>
                <Badge tone="neutral">{carrier ?? 'Unknown'}</Badge>
              </div>
              <div className="max-[840px]:hidden">
                <AgentTrail signal={signal} />
              </div>
              <div className="text-right max-[840px]:hidden">
                {signal.stage === 'escalated' || signal.stage === 'resolved' ? (
                  <Badge tone={signal.stage === 'resolved' ? 'success' : severityTone(signal.severity)} dot>
                    {signal.stage === 'resolved' ? 'Resolved' : severityLabel(signal.severity)}
                  </Badge>
                ) : (
                  <Badge tone={stageTone(signal.stage)}>{stageLabel(signal.stage)}</Badge>
                )}
              </div>
              <div className="text-right text-[12px] tabular-nums text-muted">
                {sentinel?.posted_at ? relativeTime(sentinel.posted_at) : '—'}
              </div>
              <div className="flex text-muted">
                <ChevronRight className="h-[15px] w-[15px]" />
              </div>
            </button>
          );
        })}
      </div>

      {selected && <SignalDrawer signal={selected} onClose={() => setSelected(null)} />}
    </>
  );
}
