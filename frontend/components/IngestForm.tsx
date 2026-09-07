'use client';

import { useState } from 'react';
import Link from 'next/link';
import type { IngestResponse, SignalSource } from '@/lib/types';
import { Check, TriangleAlert, Send } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

const SOURCES: { value: SignalSource; label: string }[] = [
  { value: 'x', label: 'X (Twitter)' },
  { value: 'reddit', label: 'Reddit' },
  { value: 'app_store', label: 'App Store review' },
  { value: 'google_play', label: 'Google Play review' },
  { value: 'trustpilot', label: 'Trustpilot review' },
  { value: 'quora', label: 'Quora' },
];

const CARRIERS = [
  { value: '', label: 'Let Sentinel detect it' },
  { value: 'verizon', label: 'Verizon' },
  { value: 'tmobile', label: 'T-Mobile' },
  { value: 'att', label: 'AT&T' },
];

const EXAMPLES = [
  {
    label: 'Billing dispute (likely escalates)',
    source: 'x' as SignalSource,
    author: 'frustrated_customer22',
    content:
      "Verizon overcharged me AGAIN this month, third time in a row. I want a refund or I'm switching carriers.",
    carrier: 'verizon',
  },
  {
    label: 'eSIM activation issue (likely auto-resolves)',
    source: 'app_store' as SignalSource,
    author: 'newuser2026',
    content: "eSIM won't activate on the new plan, tried scanning the QR code 3 times. Please help.",
    carrier: 'tmobile',
  },
  {
    label: 'Positive mention (should stay low priority)',
    source: 'trustpilot' as SignalSource,
    author: 'happy_switcher',
    content: 'Switched to AT&T last week and the support call to set up my new SIM was fast and painless.',
    carrier: 'att',
  },
];

export default function IngestForm() {
  const [source, setSource] = useState<SignalSource>('x');
  const [author, setAuthor] = useState('');
  const [content, setContent] = useState('');
  const [carrier, setCarrier] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<IngestResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  function fillExample(example: (typeof EXAMPLES)[number]) {
    setSource(example.source);
    setAuthor(example.author);
    setContent(example.content);
    setCarrier(example.carrier);
    setResult(null);
    setError(null);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setResult(null);

    const now = new Date().toISOString();
    const sourceId = `demo-${Date.now()}`;

    try {
      const res = await fetch('/api/proxy/signals/ingest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source,
          source_id: sourceId,
          author_handle: author || 'anonymous_demo_user',
          content,
          url: `https://example.com/${source}/${sourceId}`,
          posted_at: now,
          carrier_hint: carrier || undefined,
        }),
      });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      setResult((await res.json()) as IngestResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ingest failed');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-[560px] rounded-2xl border border-border bg-surface p-6 shadow-[var(--shadow-card)]">
      <div className="mb-4">
        <Label className="mb-2 block text-[12.5px] font-bold">Try an example</Label>
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((ex) => (
            <Button
              key={ex.label}
              type="button"
              variant="outline"
              className="rounded-full px-3 py-1.5 text-[12px] font-semibold"
              onClick={() => fillExample(ex)}
            >
              {ex.label}
            </Button>
          ))}
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-2 gap-3.5 max-[520px]:grid-cols-1">
          <div>
            <Label htmlFor="source" className="mb-1.5 block text-[12.5px] font-bold">
              Feed source
            </Label>
            <Select value={source} onValueChange={(v) => setSource(v as SignalSource)}>
              <SelectTrigger id="source" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SOURCES.map((s) => (
                  <SelectItem key={s.value} value={s.value}>
                    {s.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label htmlFor="carrier" className="mb-1.5 block text-[12.5px] font-bold">
              Carrier hint
            </Label>
            <Select value={carrier || 'auto'} onValueChange={(v) => setCarrier(v === 'auto' ? '' : v)}>
              <SelectTrigger id="carrier" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CARRIERS.map((c) => (
                  <SelectItem key={c.value || 'auto'} value={c.value || 'auto'}>
                    {c.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div>
          <Label htmlFor="author" className="mb-1.5 block text-[12.5px] font-bold">
            Author handle
          </Label>
          <Input
            id="author"
            type="text"
            value={author}
            onChange={(e) => setAuthor(e.target.value)}
            placeholder="anonymous_demo_user"
          />
          <div className="mt-1.5 text-[11.5px] text-muted">
            Hashed with SHA-256 before storage — never kept in the clear.
          </div>
        </div>

        <div>
          <Label htmlFor="content" className="mb-1.5 block text-[12.5px] font-bold">
            What they said
          </Label>
          <Textarea
            id="content"
            required
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="Write a complaint (or compliment) as if it were a real post…"
            className="min-h-[80px]"
          />
        </div>

        {error && (
          <div
            data-testid="callout-error"
            className="flex items-start gap-2 rounded-[10px] bg-critical-tint px-3.5 py-3 text-[12.5px] text-critical"
          >
            <TriangleAlert className="mt-0.5 h-[15px] w-[15px] shrink-0" />
            <span>Couldn&apos;t send that signal — {error}</span>
          </div>
        )}

        {result && (
          <div
            data-testid="callout-success"
            className="flex items-start gap-2 rounded-[10px] bg-success-tint px-3.5 py-3 text-[12.5px] text-success"
          >
            <Check className="mt-0.5 h-[15px] w-[15px] shrink-0" />
            <span>
              Queued as <span className="font-mono">{result.signal_id.slice(0, 8)}</span>. It&apos;s moving through
              Sentinel → Triage now — check the{' '}
              <Link href="/queue" className="underline">
                signal queue
              </Link>{' '}
              in a few seconds to watch it land.
            </span>
          </div>
        )}

        <Button
          type="submit"
          disabled={submitting || !content}
          className="bg-gradient-to-r from-brand to-jewel-violet text-white hover:opacity-90"
        >
          {submitting ? (
            <>
              <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white" />
              Sending…
            </>
          ) : (
            <>
              <Send className="h-[15px] w-[15px]" />
              Send to the pipeline
            </>
          )}
        </Button>
      </form>
    </div>
  );
}
