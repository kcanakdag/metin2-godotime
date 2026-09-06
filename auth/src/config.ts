import { randomBytes } from "node:crypto";
import { chmodSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { isIP } from "node:net";
import { resolve } from "node:path";

export interface AuthConfig {
  host: string;
  port: number;
  issuer: string;
  dataDir: string;
  secret: string;
  trustProxy: boolean;
  sessionSeconds: number;
  jwtSeconds: number;
  loginLimit: number;
  signupLimit: number;
}

function integer(value: string | undefined, fallback: number, minimum: number, maximum: number): number {
  const parsed = value === undefined ? fallback : Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < minimum || parsed > maximum) {
    throw new Error("An authentication service numeric setting is outside its permitted range.");
  }
  return parsed;
}

export function loadConfig(environment: NodeJS.ProcessEnv = process.env): AuthConfig {
  const host = environment.AUTH_HOST ?? "127.0.0.1";
  if (!isIP(host)) throw new Error("AUTH_HOST must be an IP address.");
  const port = integer(environment.AUTH_PORT, 3219, 1, 65535);
  const issuer = (environment.AUTH_ISSUER ?? `http://127.0.0.1:${port}/auth`).replace(/\/$/, "");
  const url = new URL(issuer);
  const local = ["127.0.0.1", "localhost", "[::1]"].includes(url.hostname);
  if (url.pathname !== "/auth" || url.search || url.hash || url.username || url.password
    || (url.protocol !== "https:" && !(url.protocol === "http:" && local))) {
    throw new Error("AUTH_ISSUER must be an HTTPS URL ending in /auth (HTTP is allowed on loopback).");
  }
  const dataDir = resolve(environment.AUTH_DATA_DIR ?? "data");
  mkdirSync(dataDir, { recursive: true, mode: 0o700 });
  chmodSync(dataDir, 0o700);
  const secretPath = resolve(dataDir, "auth.secret");
  if (!existsSync(secretPath)) {
    writeFileSync(secretPath, randomBytes(48).toString("base64url"), { flag: "wx", mode: 0o600 });
  }
  const secret = readFileSync(secretPath, "utf8").trim();
  if (secret.length < 32) throw new Error("The persisted authentication secret is invalid.");
  chmodSync(secretPath, 0o600);
  return {
    host, port, issuer, dataDir, secret,
    trustProxy: environment.AUTH_TRUST_PROXY === "true",
    sessionSeconds: 30 * 24 * 60 * 60,
    jwtSeconds: 300,
    loginLimit: 5,
    signupLimit: 5,
  };
}
