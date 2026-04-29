import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND_URL = process.env.AIM_API_URL ?? "http://localhost:8000";
const AIM_API_KEY = process.env.AIM_API_KEY ?? "";

export async function POST(req: NextRequest) {
  const upstream = await fetch(`${BACKEND_URL}/api/v1/query/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(AIM_API_KEY ? { "X-API-Key": AIM_API_KEY } : {}),
    },
    body: await req.text(),
    cache: "no-store",
    signal: req.signal,
  });

  if (!upstream.body) {
    return NextResponse.json(
      { detail: "Backend returned an empty stream." },
      { status: 502 },
    );
  }

  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("Content-Type") ?? "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}
