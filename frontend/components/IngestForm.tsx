'use client';

import { useState } from 'react';
import Link from 'next/link';
import type { IngestResponse, SignalSource } from '@/lib/types';
import { CheckIcon, AlertTriangleIcon, SendIcon } from './icons';

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
    <div className="form-card">
      <div className="field">
        <span className="field-label">Try an example</span>
        <div className="filter-row" style={{ marginBottom: 0 }}>
          {EXAMPLES.map((ex) => (
            <button key={ex.label} type="button" className="filter-pill" onClick={() => fillExample(ex)}>
              {ex.label}
            </button>
          ))}
        </div>
      </div>

      <form onSubmit={handleSubmit}>
        <div className="field-row">
          <div className="field">
            <label className="field-label" htmlFor="source">
              Feed source
            </label>
            <select id="source" value={source} onChange={(e) => setSource(e.target.value as SignalSource)}>
              {SOURCES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label className="field-label" htmlFor="carrier">
              Carrier hint
            </label>
            <select id="carrier" value={carrier} onChange={(e) => setCarrier(e.target.value)}>
              {CARRIERS.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="field">
          <label className="field-label" htmlFor="author">
            Author handle
          </label>
          <input
            id="author"
            type="text"
            value={author}
            onChange={(e) => setAuthor(e.target.value)}
            placeholder="anonymous_demo_user"
          />
          <div className="field-hint">Hashed with SHA-256 before storage — never kept in the clear.</div>
        </div>

        <div className="field">
          <label className="field-label" htmlFor="content">
            What they said
          </label>
          <textarea
            id="content"
            required
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="Write a complaint (or compliment) as if it were a real post…"
          />
        </div>

        {error && (
          <div className="callout -error">
            <AlertTriangleIcon />
            <span>Couldn&apos;t send that signal — {error}</span>
          </div>
        )}

        {result && (
          <div className="callout -success">
            <CheckIcon />
            <span>
              Queued as <span className="mono">{result.signal_id.slice(0, 8)}</span>. It&apos;s moving
              through Sentinel → Triage now — check the{' '}
              <Link href="/queue" style={{ textDecoration: 'underline' }}>
                signal queue
              </Link>{' '}
              in a few seconds to watch it land.
            </span>
          </div>
        )}

        <button type="submit" className="btn btn-primary" disabled={submitting || !content}>
          {submitting ? (
            <>
              <span className="spinner" />
              Sending…
            </>
          ) : (
            <>
              <SendIcon width={15} height={15} />
              Send to the pipeline
            </>
          )}
        </button>
      </form>
    </div>
  );
}
