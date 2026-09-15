import { NextResponse } from "next/server";

import packageMetadata from "@/package.json";

export function GET() {
  return NextResponse.json(
    { status: "ok", version: packageMetadata.version },
    { headers: { "Cache-Control": "no-store" } },
  );
}
