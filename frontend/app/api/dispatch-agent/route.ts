import { NextResponse } from 'next/server';

const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL ?? 'http://127.0.0.1:8000';

export const revalidate = 0;

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const roomName = body?.room_name;
    const avatarId = body?.avatar_id;
    const switchId = body?.switch_id;

    if (typeof roomName !== 'string' || roomName.length === 0) {
      return NextResponse.json({ error: 'room_name is required' }, { status: 400 });
    }
    if (typeof avatarId !== 'string' || avatarId.length === 0) {
      return NextResponse.json({ error: 'avatar_id is required' }, { status: 400 });
    }
    if (typeof switchId !== 'string' || switchId.length === 0) {
      return NextResponse.json({ error: 'switch_id is required' }, { status: 400 });
    }

    const response = await fetch(`${BACKEND_BASE_URL}/dispatch-agent`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ room_name: roomName, avatar_id: avatarId, switch_id: switchId }),
      cache: 'no-store',
    });

    if (!response.ok) {
      const text = await response.text();
      return NextResponse.json(
        { error: 'Dispatch failed', detail: text },
        { status: response.status }
      );
    }

    return new NextResponse(null, { status: 204 });
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
