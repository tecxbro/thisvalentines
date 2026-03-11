import { NextResponse } from 'next/server';

const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL ?? 'http://127.0.0.1:8000';

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { avatar_id, message, thread_id } = body as {
      avatar_id?: string;
      message?: string;
      thread_id?: string;
    };

    if (!avatar_id || typeof message !== 'string' || message.trim() === '') {
      return NextResponse.json(
        { error: 'avatar_id and non-empty message are required' },
        { status: 400 }
      );
    }

    const response = await fetch(`${BACKEND_BASE_URL}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        avatar_id,
        message: message.trim(),
        ...(thread_id != null && thread_id !== '' ? { thread_id } : {}),
      }),
    });

    if (!response.ok) {
      const detail = await response.text();
      return NextResponse.json(
        { error: 'Chat request failed', detail },
        { status: response.status }
      );
    }

    const payload = await response.json();
    return NextResponse.json(payload);
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
