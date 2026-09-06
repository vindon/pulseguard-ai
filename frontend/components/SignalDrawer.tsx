'use client';

import { useState } from 'react';
import type { SignalLifecycle } from '@/lib/types';
import { relativeTime, sourceLabel } from '@/lib/format';
import { requestRefresh } from '@/lib/usePolling';
import Badge, { severityTone, severityLabel } from './Badge';
import { Check, Download, TriangleAlert } from 'lucide-react';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetFooter } from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';

export default function SignalDrawer({
  signal,
  onClose,
}: {
  signal: SignalLifecycle;
  onClose: () => void;
}) {
  const [acking, setAcking] = useState(false);
  const [acked, setAcked] = useState(signal.escalation?.acknowledged ?? false);
  const [ackError, setAckError] = useState<string | null>(null);

  async function acknowledge() {
    setAcking(true);
    setAckError(null);
    try {
      const res = await fetch(`/api/proxy/escalations/${signal.signal_id}/ack`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ack_by: 'vinoth@pulseguard.local' }),
      });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      setAcked(true);
      requestRefresh();
    } catch (err) {
      setAckError(err instanceof Error ? err.message : 'Acknowledge failed');
    } finally {
      setAcking(false);
    }
  }

  function exportJson() {
    window.open(`/api/proxy/escalations/${signal.signal_id}/export`, '_blank');
  }

  const carrier = signal.sentinel?.carrier ?? 'Unknown carrier';
  const category = signal.triage?.category ?? signal.sentinel?.source ?? 'Uncategorised';

  return (
    <Sheet open onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        data-testid="signal-drawer"
        className="flex w-[min(480px,92vw)] flex-col gap-0 p-0 sm:max-w-none"
        aria-label={`Signal ${signal.signal_id}`}
      >
        <SheetHeader className="gap-2 border-b border-border px-6 py-5 text-left">
          <span className="font-mono text-[11.5px] text-muted">
            {signal.signal_id.slice(0, 8)} · {signal.sentinel ? sourceLabel(signal.sentinel.source) : '—'}
          </span>
          <SheetTitle className="font-display text-[17px] font-extrabold">
            {category} — {carrier}
          </SheetTitle>
          <div className="flex flex-wrap gap-1.5">
            {signal.severity && (
              <Badge tone={severityTone(signal.severity)} dot>
                {severityLabel(signal.severity)}
              </Badge>
            )}
            {signal.triage && (
              <Badge tone="neutral">Churn risk: {signal.triage.churn_risk ? 'High' : 'Low'}</Badge>
            )}
            {signal.triage && <Badge tone="neutral">Sentiment: {signal.triage.sentiment_score.toFixed(2)}</Badge>}
          </div>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          <div className="mb-3 text-[11px] font-bold uppercase tracking-wide text-muted">Agent trail</div>
          <div className="flex flex-col">
            {signal.sentinel && (
              <div className="flex gap-3.5 pb-5">
                <div className="flex flex-col items-center">
                  <div className="flex h-[26px] w-[26px] shrink-0 items-center justify-center rounded-full bg-success-tint text-success">
                    <Check className="h-3.5 w-3.5" />
                  </div>
                  <div className="mt-1 w-0.5 flex-1 bg-border" />
                </div>
                <div className="pt-0.5">
                  <span data-testid="timeline-agent" className="text-[13px] font-bold">
                    Sentinel
                  </span>
                  <span className="ml-2 text-[11px] font-medium text-muted">
                    validated · {relativeTime(signal.sentinel.validated_at)}
                  </span>
                  <div className="mt-0.5 text-[12px] leading-relaxed text-muted">
                    {signal.sentinel.validity_reason ?? 'Deduplicated, PII-sanitised, carrier detected.'}
                  </div>
                </div>
              </div>
            )}

            {signal.triage && (
              <div className="flex gap-3.5 pb-5">
                <div className="flex flex-col items-center">
                  <div className="flex h-[26px] w-[26px] shrink-0 items-center justify-center rounded-full bg-success-tint text-success">
                    <Check className="h-3.5 w-3.5" />
                  </div>
                  {(signal.resolver || signal.escalation) && <div className="mt-1 w-0.5 flex-1 bg-border" />}
                </div>
                <div className="pt-0.5">
                  <span data-testid="timeline-agent" className="text-[13px] font-bold">
                    Triage
                  </span>
                  <span className="ml-2 text-[11px] font-medium text-muted">
                    classified · {relativeTime(signal.triage.triaged_at)}
                  </span>
                  <div className="mt-0.5 text-[12px] leading-relaxed text-muted">
                    Category: {signal.triage.category} · Tier {signal.triage.resolution_tier} · severity{' '}
                    {signal.triage.severity_score}/5 · routed to {signal.triage.routing_decision}
                  </div>
                </div>
              </div>
            )}

            {signal.resolver && (
              <div className="flex gap-3.5 pb-5">
                <div className="flex flex-col items-center">
                  <div
                    className={`flex h-[26px] w-[26px] shrink-0 items-center justify-center rounded-full ${
                      signal.resolver.resolved ? 'bg-success-tint text-success' : 'bg-critical-tint text-critical'
                    }`}
                  >
                    {signal.resolver.resolved ? (
                      <Check className="h-3.5 w-3.5" />
                    ) : (
                      <TriangleAlert className="h-3.5 w-3.5" />
                    )}
                  </div>
                </div>
                <div className="pt-0.5">
                  <span data-testid="timeline-agent" className="text-[13px] font-bold">
                    Resolver
                  </span>
                  <span className="ml-2 text-[11px] font-medium text-muted">
                    {signal.resolver.resolved ? 'resolved' : 'attempted'} ·{' '}
                    {relativeTime(signal.resolver.resolved_at)}
                  </span>
                  <div className="mt-0.5 text-[12px] leading-relaxed text-muted">
                    Confidence {(signal.resolver.confidence_score * 100).toFixed(0)}%
                    {signal.resolver.escalation_reason ? ` — ${signal.resolver.escalation_reason}` : ''}
                  </div>
                  <div className="mt-2 rounded-[10px] border border-border bg-bg px-3.5 py-2.5 text-[12.5px] leading-normal text-ink">
                    {signal.resolver.draft_response}
                  </div>
                </div>
              </div>
            )}

            {signal.escalation && (
              <div className="flex gap-3.5 pb-5">
                <div className="flex flex-col items-center">
                  <div className="flex h-[26px] w-[26px] shrink-0 items-center justify-center rounded-full bg-critical-tint text-critical">
                    <TriangleAlert className="h-3.5 w-3.5" />
                  </div>
                </div>
                <div className="pt-0.5">
                  <span data-testid="timeline-agent" className="text-[13px] font-bold">
                    Escalation
                  </span>
                  <span className="ml-2 text-[11px] font-medium text-muted">
                    raised · {relativeTime(signal.escalation.escalated_at)}
                  </span>
                  <div className="mt-0.5 text-[12px] leading-relaxed text-muted">{signal.escalation.summary}</div>
                  <div className="mt-2 rounded-[10px] border border-border bg-bg px-3.5 py-2.5 text-[12.5px] leading-normal text-ink">
                    {signal.escalation.recommended_action}
                  </div>
                </div>
              </div>
            )}

            {!signal.sentinel && (
              <div className="py-6 text-center text-[13px] text-muted">No lifecycle data yet.</div>
            )}
          </div>
        </div>

        {signal.escalation && (
          <SheetFooter data-testid="drawer-footer" className="flex-row gap-2.5 border-t border-border px-6 py-4">
            <Button variant="outline" className="flex-1" onClick={exportJson}>
              <Download className="h-3.5 w-3.5" />
              Export
            </Button>
            <Button
              className="flex-1 bg-gradient-to-r from-brand to-jewel-violet text-white hover:opacity-90"
              onClick={acknowledge}
              disabled={acked || acking}
            >
              {acked ? (
                <>
                  <Check className="h-3.5 w-3.5" />
                  Acknowledged
                </>
              ) : acking ? (
                'Acknowledging…'
              ) : (
                <>
                  <Check className="h-3.5 w-3.5" />
                  Acknowledge
                </>
              )}
            </Button>
          </SheetFooter>
        )}
        {ackError && (
          <div
            data-testid="callout-error"
            className="mx-6 mb-4 rounded-[10px] bg-critical-tint px-3.5 py-3 text-[13px] text-critical"
          >
            {ackError}
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
