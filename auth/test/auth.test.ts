import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { createLocalJWKSet, decodeProtectedHeader, jwtVerify, type JSONWebKeySet } from "jose";
import { loadConfig, type AuthConfig } from "../src/config.js";
import { startAuthServer } from "../src/server.js";

type Json = Record<string, unknown>;

async function fixture(overrides: Partial<AuthConfig> = {}) {
  const dataDir = await mkdtemp(join(tmpdir(), "mt2-auth-test-"));
  const config = {
    ...loadConfig({ AUTH_DATA_DIR: dataDir, AUTH_ISSUER: "http://127.0.0.1:3219/auth" }),
    port: 0, loginLimit: 40, signupLimit: 40, ...overrides,
  };
  let service = await startAuthServer(config);
  function address(): string {
    const bound = service.server.address();
    assert.ok(bound && typeof bound !== "string");
    return `http://127.0.0.1:${bound.port}`;
  }
  async function call(path: string, body?: Json, token?: string, extra: Record<string, string> = {}) {
    const headers: Record<string, string> = { origin: new URL(config.issuer).origin, ...extra };
    const init: RequestInit = { method: body === undefined ? "GET" : "POST", headers };
    if (body !== undefined) {
      headers["content-type"] = "application/json";
      init.body = JSON.stringify(body);
    }
    if (token) headers.authorization = `Bearer ${token}`;
    const response = await fetch(address() + path, init);
    const result: unknown = await response.json();
    return { status: response.status, headers: response.headers, body: result as Json | null };
  }
  return {
    call, address, config,
    async restart() {
      await service.close();
      service = await startAuthServer(config);
    },
    async close() {
      await service.close();
      await rm(dataDir, { recursive: true, force: true });
    },
  };
}

const signup = { name: "Fixture", username: "FixtureWarrior", email: "fixture@example.invalid", password: "Fixture password 729!" };

test("signup, signed bearer session, case-insensitive username login and validation", async () => {
  const app = await fixture();
  try {
    assert.equal((await app.call("/auth/health")).status, 200);
    const registered = await app.call("/auth/sign-up/email", signup);
    assert.equal(registered.status, 200);
    const token = registered.headers.get("set-auth-token");
    assert.ok(token);
    assert.ok(registered.headers.get("access-control-expose-headers")?.includes("set-auth-token"));
    assert.equal((await app.call("/auth/get-session", undefined, token)).status, 200);
    assert.ok((await app.call("/auth/get-session", undefined, token)).body?.user);
    assert.equal((await app.call("/auth/get-session")).body, null);
    const unsigned = token.split(".")[0];
    assert.equal((await app.call("/auth/get-session", undefined, unsigned)).body, null);
    const duplicate = await app.call("/auth/sign-up/email", { ...signup, email: "another@example.invalid", username: "fixturewarrior" });
    assert.equal(duplicate.status, 400);
    const duplicateEmail = await app.call("/auth/sign-up/email", { ...signup, username: "DifferentName" });
    assert.ok(duplicateEmail.status >= 400);
    for (const password of ["tiny", "x".repeat(129)]) {
      const invalid = await app.call("/auth/sign-up/email", { ...signup, email: "new@example.invalid", username: "NewName", password });
      assert.ok(invalid.status >= 400);
    }
    const missingUsername = await app.call("/auth/sign-up/email", { email: "no-name@example.invalid", name: "NoName", password: signup.password });
    assert.equal(missingUsername.status, 400);
    const login = await app.call("/auth/sign-in/username", { username: "FIXTUREWARRIOR", password: signup.password, rememberMe: true });
    assert.equal(login.status, 200);
    assert.ok(login.headers.get("set-auth-token"));
    const wrong = await app.call("/auth/sign-in/username", { username: signup.username, password: "Wrong password 123" });
    const absent = await app.call("/auth/sign-in/username", { username: "AbsentAccount", password: "Wrong password 123" });
    assert.equal(wrong.status, 401);
    assert.equal(absent.status, 401);
    assert.equal(wrong.body?.code, absent.body?.code);
    assert.equal((await app.call("/auth/update-user", { name: "Changed" }, token)).status, 404);
    assert.equal((await app.call("/auth/sign-jwt", { payload: { sub: "someone-else" } }, token)).status, 404);
    assert.equal((await app.call("/auth/sign-up/email", { ...signup, username: "AttackName" }, undefined, { origin: "https://untrusted.invalid" })).status, 403);
  } finally {
    await app.close();
  }
});

test("minimal RS256 game JWT, key persistence, remembered session and logout", async () => {
  const app = await fixture();
  try {
    const registered = await app.call("/auth/sign-up/email", signup);
    assert.equal(registered.status, 200);
    const session = registered.headers.get("set-auth-token");
    assert.ok(session);
    const metadata = await app.call("/auth/.well-known/openid-configuration");
    assert.equal(metadata.body?.issuer, app.config.issuer);
    assert.equal(metadata.body?.jwks_uri, `${app.config.issuer}/jwks`);
    assert.equal((await app.call("/.well-known/openid-configuration")).status, 200);
    const jwks = (await app.call("/auth/jwks")).body as unknown as JSONWebKeySet;
    assert.ok(jwks.keys.length);
    assert.ok(jwks.keys.every((key) => !key.d && !key.p && !key.q));
    assert.equal((await app.call("/auth/token")).status, 401);
    const issued = await app.call("/auth/token", undefined, session);
    assert.equal(issued.status, 200);
    const token = issued.body?.token;
    assert.equal(typeof token, "string");
    const verified = await jwtVerify(token as string, createLocalJWKSet(jwks), { issuer: app.config.issuer, audience: "mt2-game", algorithms: ["RS256"] });
    assert.deepEqual(Object.keys(verified.payload).sort(), ["aud", "exp", "iat", "iss", "sub"]);
    assert.equal((verified.payload.exp ?? 0) - (verified.payload.iat ?? 0), 300);
    assert.equal(verified.payload.sub, (registered.body?.user as Json).id);
    await assert.rejects(jwtVerify(token as string, createLocalJWKSet(jwks), { audience: "another-game" }));
    await assert.rejects(jwtVerify(token as string, createLocalJWKSet(jwks), { issuer: "https://wrong.invalid/auth" }));
    const kid = decodeProtectedHeader(token as string).kid;
    const secret = await readFile(join(app.config.dataDir, "auth.secret"));
    await app.restart();
    assert.ok((await app.call("/auth/get-session", undefined, session)).body?.user);
    const after = (await app.call("/auth/token", undefined, session)).body?.token;
    assert.equal(typeof after, "string");
    assert.equal(decodeProtectedHeader(after as string).kid, kid);
    assert.ok(secret.equals(await readFile(join(app.config.dataDir, "auth.secret"))));
    assert.equal((await stat(join(app.config.dataDir, "auth.secret"))).mode & 0o777, 0o600);
    assert.equal((await app.call("/auth/sign-out", {}, session)).status, 200);
    assert.equal((await app.call("/auth/get-session", undefined, session)).body, null);
    assert.equal((await app.call("/auth/token", undefined, session)).status, 401);
    // Logout revokes the session, while previously issued offline JWTs expire within five minutes.
    await jwtVerify(token as string, createLocalJWKSet(jwks), { issuer: app.config.issuer, audience: "mt2-game" });
    await app.restart();
    assert.equal((await app.call("/auth/get-session", undefined, session)).body, null);
  } finally {
    await app.close();
  }
});

test("expired sessions cannot mint tokens; JWT expiration is enforced", async () => {
  const app = await fixture({ sessionSeconds: 1, jwtSeconds: 1 });
  try {
    const registered = await app.call("/auth/sign-up/email", signup);
    const session = registered.headers.get("set-auth-token");
    assert.ok(session);
    const issued = await app.call("/auth/token", undefined, session);
    const token = issued.body?.token;
    assert.equal(typeof token, "string");
    const jwks = (await app.call("/auth/jwks")).body as unknown as JSONWebKeySet;
    await new Promise((resolve) => setTimeout(resolve, 1400));
    await assert.rejects(jwtVerify(token as string, createLocalJWKSet(jwks)), { code: "ERR_JWT_EXPIRED" });
    assert.equal((await app.call("/auth/get-session", undefined, session)).body, null);
    assert.equal((await app.call("/auth/token", undefined, session)).status, 401);
  } finally {
    await app.close();
  }
});

test("database rate limits survive restart and ignore forged forwarding headers", async () => {
  const app = await fixture({ loginLimit: 2, signupLimit: 2 });
  try {
    for (let index = 0; index < 2; index++) {
      assert.equal((await app.call("/auth/sign-in/username", { username: "UnknownAccount", password: "Wrong password 123" })).status, 401);
    }
    await app.restart();
    const rejected = await app.call("/auth/sign-in/username", { username: "UnknownAccount", password: "Wrong password 123" }, undefined, { "x-real-ip": "198.51.100.88", "x-forwarded-for": "198.51.100.89", "x-mt2-client-ip": "198.51.100.90" });
    assert.equal(rejected.status, 429);
    assert.ok(rejected.headers.get("x-retry-after"));
    const oversized = await fetch(app.address() + "/auth/sign-up/email", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ huge: "x".repeat(20_000) }) });
    assert.equal(oversized.status, 413);
  } finally {
    await app.close();
  }
});
