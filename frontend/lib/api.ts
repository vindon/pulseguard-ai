// Server-only: reads the gateway URL/key from the server environment and
// attaches X-API-Key itself. Never import this from a 'use client' file —
// the key must never reach the browser. Client components go through
// app/api/proxy/[...path]/route.ts instead.
import 'server-only';

const API_URL = process.env.PULSEGUARD_API_URL || 'http://localhost:8000';
const API_KEY = process.env.PULSEGUARD_API_KEY || '';

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit & { cache?: RequestCache } = {}
): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      'X-API-Key': API_KEY,
      'Content-Type': 'application/json',
      ...init.headers,
    },
    // Live operational data — never cache a stale queue.
    cache: init.cache ?? 'no-store',
  });

  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new ApiError(res.status, body || `${res.status} ${res.statusText}`);
  }

  return res.json() as Promise<T>;
}
