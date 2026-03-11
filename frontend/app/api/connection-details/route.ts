import { NextResponse } from 'next/server';

const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL ?? 'http://127.0.0.1:8000';

export const revalidate = 0;

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const avatarId = body?.avatar_id;

    if (typeof avatarId !== 'string' || avatarId.length === 0) {
      return NextResponse.json({ error: 'avatar_id is required' }, { status: 400 });
    }

    const response = await fetch(`${BACKEND_BASE_URL}/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ avatar_id: avatarId }),
      cache: 'no-store',
    });

    if (!response.ok) {
      const text = await response.text();
      return NextResponse.json(
        { error: 'Failed to fetch token from backend', detail: text },
        { status: response.status }
      );
    }

    const payload = await response.json();
    return NextResponse.json(payload, {
      headers: { 'Cache-Control': 'no-store' },
    });
  } catch (error) {
    return NextResponse.json(
      {
        error: 'Backend unavailable',
        detail: error instanceof Error ? error.message : String(error),
      },
      { status: 503 }
    );
  }
}
