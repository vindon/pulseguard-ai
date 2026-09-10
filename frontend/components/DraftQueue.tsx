'use client';

import { useState } from 'react';
import type { DraftsResponse, PendingDraft } from '@/lib/types';
import { usePolling } from '@/lib/usePolling';
import { requestRefresh } from '@/lib/usePolling';
import { Button } from '@/components/ui/button';
import { Check, X, TriangleAlert } from 'lucide-react';

export default function DraftQueue() {
  const { data, loading } = usePolling<DraftsResponse>('/drafts?status=pending', 10000);
  const [actingOn, setActingOn] = useState<string | null>(null);
  const drafts = data?.drafts ?? [];

  async function act(signalId: string, action: 'approve' | 'reject') {
    setActingOn(signalId);
    try {
      await fetch(`/api/proxy/drafts/${signalId}/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reviewed_by: 'vinoth@pulseguard.local' }),
      });
      requestRefresh();
    } finally {
      setActingOn(null);
    }
  }

  if (loading && drafts.length === 0) {
    return <div className="p-14 text-center text-muted">Loading drafts…</div>;
  }

  if (drafts.length === 0) {
    return <div data-testid="empty-state" className="p-14 text-center text-muted">Nothing waiting for review.</div>;
  }

  return (
    <div className="flex flex-col gap-3.5">
      {drafts.map((draft: PendingDraft) => (
        <div
          key={draft.signal_id}
          data-testid="draft-card"
          className="rounded-[13px] border border-border bg-surface p-4 shadow-[var(--shadow-card)]"
        >
          <div className="flex items-center justify-between">
            <div className="text-[12.5px] font-semibold">
              {draft.category} — {draft.carrier}
            </div>
            <div className="font-mono text-[11px] text-muted">
              {(draft.confidence_score * 100).toFixed(0)}% confidence
            </div>
          </div>
          {draft.screen_flag && (
            <div className="mt-2 flex items-center gap-1.5 rounded-[8px] bg-warning-tint px-2.5 py-1.5 text-[11.5px] text-warning">
              <TriangleAlert className="h-3.5 w-3.5 shrink-0" />
              {draft.screen_flag}
            </div>
          )}
          <div className="mt-2.5 rounded-[10px] border border-border bg-bg px-3.5 py-2.5 text-[12.5px] leading-normal">
            {draft.draft_text}
          </div>
          <div className="mt-3 flex gap-2">
            <Button
              className="flex-1 bg-gradient-to-r from-brand to-jewel-violet text-white hover:opacity-90"
              disabled={actingOn === draft.signal_id}
              onClick={() => act(draft.signal_id, 'approve')}
            >
              <Check className="h-3.5 w-3.5" />
              Approve & Send
            </Button>
            <Button
              variant="outline"
              disabled={actingOn === draft.signal_id}
              onClick={() => act(draft.signal_id, 'reject')}
            >
              <X className="h-3.5 w-3.5" />
              Reject
            </Button>
          </div>
        </div>
      ))}
    </div>
  );
}
