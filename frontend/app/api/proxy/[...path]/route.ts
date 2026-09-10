import { NextRequest, NextResponse } from 'next/server';

// Thin authenticated proxy: client components call /api/proxy/<path>, this
// handler attaches X-API-Key server-side and forwards to the real gateway.
// The API key never reaches the browser. Only GET and the specific POST
// actions the UI actually performs are allowed through — this is not a
// general-purpose passthrough.

const API_URL = process.env.PULSEGUARD_API_URL || 'http://localhost:8000';
const API_KEY = process.env.PULSEGUARD_API_KEY || '';

const ALLOWED_POST_SUFFIXES = [/\/ack$/, /^signals\/ingest$/, /\/(approve|reject)$/];

function resolveTarget(pathSegments: string[]): string | null {
  if (pathSegments.some((seg) => seg === '..' || seg === '.' || seg === '')) {
    return null;
  }
  return `/api/v1/${pathSegments.join('/')}`;
}

export async function GET(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const target = resolveTarget(path);
  if (!target) {
    return NextResponse.json({ error: 'invalid path' }, { status: 400 });
  }

  const search = request.nextUrl.search;
  const res = await fetch(`${API_URL}${target}${search}`, {
    headers: { 'X-API-Key': API_KEY },
    cache: 'no-store',
  });

  const body = await res.text();
  return new NextResponse(body, {
    status: res.status,
    headers: { 'Content-Type': res.headers.get('Content-Type') ?? 'application/json' },
  });
}

export async function POST(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const target = resolveTarget(path);
  const joined = path.join('/');
  if (!target || !ALLOWED_POST_SUFFIXES.some((re) => re.test(joined))) {
    return NextResponse.json({ error: 'invalid path' }, { status: 400 });
  }

  const bodyText = await request.text();
  const res = await fetch(`${API_URL}${target}`, {
    method: 'POST',
    headers: { 'X-API-Key': API_KEY, 'Content-Type': 'application/json' },
    body: bodyText,
    cache: 'no-store',
  });

  const responseBody = await res.text();
  return new NextResponse(responseBody, {
    status: res.status,
    headers: { 'Content-Type': res.headers.get('Content-Type') ?? 'application/json' },
  });
}
