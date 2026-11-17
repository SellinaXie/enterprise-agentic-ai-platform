import { getManagedAuth } from "@/lib/auth/server";

type Context = { params: Promise<{ path: string[] }> };

function handler(method: "GET" | "POST" | "PUT" | "DELETE" | "PATCH") {
  return async (request: Request, context: Context) => {
    if (!process.env.NEON_AUTH_BASE_URL || !process.env.NEON_AUTH_COOKIE_SECRET) {
      return Response.json({ error: "Workspace sign-in is not configured." }, { status: 503 });
    }
    return getManagedAuth().handler()[method](request, context);
  };
}

export const GET = handler("GET");
export const POST = handler("POST");
export const PUT = handler("PUT");
export const DELETE = handler("DELETE");
export const PATCH = handler("PATCH");
