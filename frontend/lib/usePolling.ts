'use client';

import { useEffect, useRef, useState } from 'react';

interface PollingState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

// Dispatched after any write that should be reflected everywhere
// immediately (e.g. acknowledging an escalation) rather than waiting for
// each poller's own interval — the sidebar badge alone polls every 20s,
// which would otherwise make an acknowledged escalation look stuck.
const REFRESH_EVENT = 'pulseguard:refresh';

export function requestRefresh() {
  window.dispatchEvent(new Event(REFRESH_EVENT));
}

// Polls a proxy endpoint on an interval. Used instead of a WebSocket/SSE
// connection because the FastAPI gateway doesn't currently expose either —
// this is the pragmatic choice for a portfolio-showcase build, not a
// production-scale operations tool serving many concurrent viewers.
//
// `initialData`, when given, comes from the page's Server Component (which
// fetched it directly via lib/api.ts before this component ever mounted) so
// the first paint shows real data instead of a loading flash — polling then
// takes over seamlessly from there.
export function usePolling<T>(path: string, intervalMs = 5000, initialData: T | null = null): PollingState<T> {
  const [state, setState] = useState<PollingState<T>>({
    data: initialData,
    error: null,
    loading: initialData === null,
  });
  const pathRef = useRef(path);
  pathRef.current = path;

  useEffect(() => {
    let cancelled = false;

    async function tick() {
      try {
        const res = await fetch(`/api/proxy${pathRef.current}`, { cache: 'no-store' });
        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
        const data = (await res.json()) as T;
        if (!cancelled) setState({ data, error: null, loading: false });
      } catch (err) {
        if (!cancelled) {
          setState((prev) => ({
            data: prev.data,
            error: err instanceof Error ? err.message : 'Request failed',
            loading: false,
          }));
        }
      }
    }

    tick();
    const id = setInterval(tick, intervalMs);
    window.addEventListener(REFRESH_EVENT, tick);
    return () => {
      cancelled = true;
      clearInterval(id);
      window.removeEventListener(REFRESH_EVENT, tick);
    };
  }, [path, intervalMs]);

  return state;
}
