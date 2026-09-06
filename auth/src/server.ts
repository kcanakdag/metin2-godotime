import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { isIP } from "node:net";
import { createAuth } from "./auth.js";
import type { AuthConfig } from "./config.js";

const ROUTES = new Map([
  ["/auth/sign-up/email", "POST"],
  ["/auth/sign-in/username", "POST"],
  ["/auth/get-session", "GET"],
  ["/auth/sign-out", "POST"],
  ["/auth/token", "GET"],
  ["/auth/jwks", "GET"],
]);
const MAX_BODY = 16 * 1024;

function json(response: ServerResponse, status: number, body: unknown): void {
  response.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
  });
  response.end(JSON.stringify(body));
}

function readBody(request: IncomingMessage): Promise<Buffer | null> {
  return new Promise((resolve) => {
    const chunks: Buffer[] = [];
    let total = 0;
    request.on("data", (chunk: Buffer) => {
      total += chunk.length;
      if (total > MAX_BODY) {
        chunks.length = 0;
        resolve(null);
      } else {
        chunks.push(chunk);
      }
    });
    request.on("end", () => resolve(total > MAX_BODY ? null : Buffer.concat(chunks)));
    request.on("error", () => resolve(null));
    request.on("aborted", () => resolve(null));
  });
}

function requestHeaders(request: IncomingMessage, config: AuthConfig): Headers {
  const headers = new Headers();
  for (const [key, value] of Object.entries(request.headers)) {
    if (value !== undefined) headers.set(key, Array.isArray(value) ? value.join(", ") : value);
  }
  const forwarded = request.headers["x-real-ip"];
  const peer = request.socket.remoteAddress ?? "127.0.0.1";
  const client = config.trustProxy && typeof forwarded === "string" && isIP(forwarded) ? forwarded : peer;
  for (const key of ["forwarded", "x-forwarded-for", "x-forwarded-host", "x-forwarded-proto", "x-real-ip"]) {
    headers.delete(key);
  }
  headers.set("x-mt2-client-ip", client);
  headers.set("host", new URL(config.issuer).host);
  return headers;
}

export async function startAuthServer(config: AuthConfig) {
  const { auth, database } = await createAuth(config);
  const server = createServer(async (request, response) => {
    try {
      const url = new URL(request.url ?? "/", config.issuer);
      if (request.method === "GET" && url.pathname === "/auth/health") {
        json(response, 200, { status: "ok" });
        return;
      }
      if (request.method === "GET" && [
        "/auth/.well-known/openid-configuration", "/.well-known/openid-configuration",
      ].includes(url.pathname)) {
        json(response, 200, {
          issuer: config.issuer,
          jwks_uri: `${config.issuer}/jwks`,
          id_token_signing_alg_values_supported: ["RS256"],
          subject_types_supported: ["public"],
          claims_supported: ["iss", "aud", "sub", "iat", "exp"],
        });
        return;
      }
      if (ROUTES.get(url.pathname) !== request.method || url.search) {
        json(response, 404, { message: "Not found." });
        return;
      }
      const body = request.method === "POST" ? await readBody(request) : undefined;
      if (body === null) {
        response.setHeader("connection", "close");
        json(response, 413, { message: "Request body is too large." });
        return;
      }
      const init: RequestInit = { method: request.method ?? "GET", headers: requestHeaders(request, config) };
      if (body !== undefined && body.length) init.body = new Uint8Array(body);
      const reply = await auth.handler(new Request(new URL(url.pathname, config.issuer), init));
      response.statusCode = reply.status;
      for (const [key, value] of reply.headers) {
        if (key !== "set-cookie") response.setHeader(key, value);
      }
      const cookies = reply.headers.getSetCookie();
      if (cookies.length) response.setHeader("set-cookie", cookies);
      response.setHeader("cache-control", "no-store");
      response.setHeader("x-content-type-options", "nosniff");
      response.end(Buffer.from(await reply.arrayBuffer()));
    } catch {
      // Never print request bodies, passwords, session tokens, or library exception objects.
      if (!response.headersSent) json(response, 500, { message: "Authentication is temporarily unavailable." });
      else response.end();
    }
  });
  server.requestTimeout = 15_000;
  server.headersTimeout = 10_000;
  server.keepAliveTimeout = 5_000;
  server.maxHeadersCount = 40;
  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    server.listen(config.port, config.host, () => {
      server.off("error", reject);
      resolve();
    });
  });
  return {
    server,
    async close(): Promise<void> {
      await new Promise<void>((resolve, reject) => {
        server.close((error) => error ? reject(error) : resolve());
        server.closeIdleConnections();
      });
      database.close();
    },
  };
}
