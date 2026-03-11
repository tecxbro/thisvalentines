import { NextResponse } from 'next/server';

const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL ?? 'http://127.0.0.1:8000';

export const revalidate = 0;

export async function GET() {
  try {
    const response = await fetch(`${BACKEND_BASE_URL}/avatars`, {
      cache: 'no-store',
    });

    if (!response.ok) {
      const body = await response.text();
      return NextResponse.json(
        { error: 'Failed to fetch avatars from backend', detail: body },
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
