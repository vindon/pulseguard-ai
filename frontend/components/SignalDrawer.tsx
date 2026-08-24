'use client';

import { useState } from 'react';
import type { SignalLifecycle } from '@/lib/types';
import { relativeTime, sourceLabel } from '@/lib/format';
import Badge, { severityTone, severityLabel } from './Badge';
import { CloseIcon, CheckIcon, DownloadIcon, AlertTriangleIcon } from './icons';

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
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <div className="drawer" role="dialog" aria-label={`Signal ${signal.signal_id}`}>
        <div className="drawer-head">
          <div className="drawer-eyebrow">
            <span className="drawer-id mono">
              {signal.signal_id.slice(0, 8)} · {signal.sentinel ? sourceLabel(signal.sentinel.source) : '—'}
            </span>
            <button type="button" className="drawer-close" onClick={onClose} aria-label="Close">
              <CloseIcon />
            </button>
          </div>
          <div className="drawer-title">
            {category} — {carrier}
          </div>
          <div className="drawer-badges">
            {signal.severity && (
              <Badge tone={severityTone(signal.severity)} dot>
                {severityLabel(signal.severity)}
              </Badge>
            )}
            {signal.triage && (
              <Badge tone="neutral">
                Churn risk: {signal.triage.churn_risk ? 'High' : 'Low'}
              </Badge>
            )}
            {signal.triage && (
              <Badge tone="neutral">Sentiment: {signal.triage.sentiment_score.toFixed(2)}</Badge>
            )}
          </div>
        </div>

        <div className="drawer-body">
          <div className="drawer-section-label">Agent trail</div>
          <div className="timeline">
            {signal.sentinel && (
              <div className="timeline-item">
                <div className="timeline-rail">
                  <div className="timeline-dot -success">
                    <CheckIcon />
                  </div>
                  <div className="timeline-line" />
                </div>
                <div className="timeline-content">
                  <span className="timeline-agent">Sentinel</span>
                  <span className="timeline-time">validated · {relativeTime(signal.sentinel.validated_at)}</span>
                  <div className="timeline-desc">
                    {signal.sentinel.validity_reason ??
                      'Deduplicated, PII-sanitised, carrier detected.'}
                  </div>
                </div>
              </div>
            )}

            {signal.triage && (
              <div className="timeline-item">
                <div className="timeline-rail">
                  <div className="timeline-dot -success">
                    <CheckIcon />
                  </div>
                  {(signal.resolver || signal.escalation) && <div className="timeline-line" />}
                </div>
                <div className="timeline-content">
                  <span className="timeline-agent">Triage</span>
                  <span className="timeline-time">classified · {relativeTime(signal.triage.triaged_at)}</span>
                  <div className="timeline-desc">
                    Category: {signal.triage.category} · Tier {signal.triage.resolution_tier} · severity{' '}
                    {signal.triage.severity_score}/5 · routed to {signal.triage.routing_decision}
                  </div>
                </div>
              </div>
            )}

            {signal.resolver && (
              <div className="timeline-item">
                <div className="timeline-rail">
                  <div className={`timeline-dot ${signal.resolver.resolved ? '-success' : '-critical'}`}>
                    {signal.resolver.resolved ? <CheckIcon /> : <AlertTriangleIcon />}
                  </div>
                </div>
                <div className="timeline-content">
                  <span className="timeline-agent">Resolver</span>
                  <span className="timeline-time">
                    {signal.resolver.resolved ? 'resolved' : 'attempted'} ·{' '}
                    {relativeTime(signal.resolver.resolved_at)}
                  </span>
                  <div className="timeline-desc">
                    Confidence {(signal.resolver.confidence_score * 100).toFixed(0)}%
                    {signal.resolver.escalation_reason ? ` — ${signal.resolver.escalation_reason}` : ''}
                  </div>
                  <div className="timeline-card">{signal.resolver.draft_response}</div>
                </div>
              </div>
            )}

            {signal.escalation && (
              <div className="timeline-item">
                <div className="timeline-rail">
                  <div className="timeline-dot -critical">
                    <AlertTriangleIcon />
                  </div>
                </div>
                <div className="timeline-content">
                  <span className="timeline-agent">Escalation</span>
                  <span className="timeline-time">raised · {relativeTime(signal.escalation.escalated_at)}</span>
                  <div className="timeline-desc">{signal.escalation.summary}</div>
                  <div className="timeline-card">{signal.escalation.recommended_action}</div>
                </div>
              </div>
            )}

            {!signal.sentinel && <div className="drawer-empty">No lifecycle data yet.</div>}
          </div>
        </div>

        {signal.escalation && (
          <div className="drawer-footer">
            <button type="button" className="btn btn-ghost -block" onClick={exportJson}>
              <DownloadIcon />
              Export
            </button>
            <button
              type="button"
              className="btn btn-primary -block"
              onClick={acknowledge}
              disabled={acked || acking}
            >
              {acked ? (
                <>
                  <CheckIcon />
                  Acknowledged
                </>
              ) : acking ? (
                'Acknowledging…'
              ) : (
                <>
                  <CheckIcon />
                  Acknowledge
                </>
              )}
            </button>
          </div>
        )}
        {ackError && <div className="callout -error" style={{ margin: '0 24px 16px' }}>{ackError}</div>}
      </div>
    </>
  );
}
