import type { NextRequest } from "next/server";

const API_BASE_URL = (
  process.env.API_BASE_URL ?? "http://127.0.0.1:8000"
).replace(/\/+$/, "");

const API_KEY = process.env.ATS_API_KEY;

/**
 * Only expose the engine routes this UI actually uses. A catch-all proxy that
 * forwards arbitrary paths would turn the frontend into an open proxy.
 */
const ALLOWED_ROOTS = new Set([
  "health",
  "meta",
  "resumes",
  "jds",
  "score",
  "scores",
  "optimise",
  "jobs",
  "facts",
]);

const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
  "content-length",
  "content-encoding",
]);

type RouteParams = { params: Promise<{ path: string[] }> };

function errorResponse(code: string, message: string, status: number) {
  return Response.json({ error: { code, message } }, { status });
}

async function proxy(request: NextRequest, context: RouteParams) {
  const { path } = await context.params;
  const root = path[0];

  if (!root || !ALLOWED_ROOTS.has(root)) {
    return errorResponse(
      "proxy_route_not_allowed",
      "That engine route is not exposed by this frontend.",
      404,
    );
  }

  const target = `${API_BASE_URL}/v1/${path
    .map((segment) => encodeURIComponent(segment))
    .join("/")}${request.nextUrl.search}`;

  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  const accept = request.headers.get("accept");
  if (accept) headers.set("accept", accept);
  if (API_KEY) headers.set("x-api-key", API_KEY);

  const init: RequestInit = {
    method: request.method,
    headers,
    cache: "no-store",
    redirect: "manual",
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.arrayBuffer();
  }

  let upstream: Response;
  try {
    upstream = await fetch(target, init);
  } catch {
    return errorResponse(
      "api_unreachable",
      "The scoring engine is not reachable. Check that the FastAPI server is running.",
      502,
    );
  }

  const responseHeaders = new Headers();
  upstream.headers.forEach((value, key) => {
    if (!HOP_BY_HOP_HEADERS.has(key.toLowerCase())) {
      responseHeaders.set(key, value);
    }
  });
  responseHeaders.set("cache-control", "no-store");

  if (upstream.headers.get("content-type")?.includes("text/event-stream")) {
    responseHeaders.set("x-accel-buffering", "no");
  }

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
}

export {
  proxy as GET,
  proxy as POST,
  proxy as PUT,
  proxy as PATCH,
  proxy as DELETE,
  proxy as HEAD,
};
