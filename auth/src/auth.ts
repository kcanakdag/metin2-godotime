import { chmodSync } from "node:fs";
import { join } from "node:path";
import { betterAuth } from "better-auth";
import { APIError, createAuthMiddleware } from "better-auth/api";
import { getMigrations } from "better-auth/db/migration";
import { bearer, jwt, username } from "better-auth/plugins";
import Database from "better-sqlite3";
import type { AuthConfig } from "./config.js";

export async function createAuth(config: AuthConfig) {
  const database = new Database(join(config.dataDir, "auth.sqlite"));
  chmodSync(join(config.dataDir, "auth.sqlite"), 0o600);
  database.pragma("journal_mode = WAL");
  database.pragma("foreign_keys = ON");
  database.pragma("busy_timeout = 5000");
  const auth = betterAuth({
    appName: "MT2 Game",
    baseURL: new URL(config.issuer).origin,
    basePath: "/auth",
    secret: config.secret,
    database,
    trustedOrigins: [new URL(config.issuer).origin],
    logger: { disabled: true },
    telemetry: { enabled: false },
    emailAndPassword: {
      enabled: true,
      requireEmailVerification: false,
      autoSignIn: true,
      minPasswordLength: 8,
      maxPasswordLength: 128,
    },
    session: {
      expiresIn: config.sessionSeconds,
      updateAge: Math.min(24 * 60 * 60, config.sessionSeconds),
      cookieCache: { enabled: false },
    },
    account: { accountLinking: { enabled: false } },
    advanced: {
      useSecureCookies: config.issuer.startsWith("https:"),
      ipAddress: { ipAddressHeaders: ["x-mt2-client-ip"] },
    },
    rateLimit: {
      enabled: true,
      storage: "database",
      window: 60,
      max: 100,
      customRules: {
        "/sign-in/username": { window: 60, max: config.loginLimit },
        "/sign-up/email": { window: 300, max: config.signupLimit },
      },
    },
    hooks: {
      before: createAuthMiddleware(async (context) => {
        if (context.path === "/sign-up/email") {
          if (typeof context.body?.username !== "string" || !context.body.username) {
            throw new APIError("BAD_REQUEST", { code: "USERNAME_REQUIRED", message: "Username is required." });
          }
          // The account name is its chosen username; character names live in the game.
          context.body.name = context.body.username;
        }
      }),
    },
    plugins: [
      username({
        minUsernameLength: 3,
        maxUsernameLength: 24,
        usernameValidator: (value) => /^[a-zA-Z0-9_]+$/.test(value),
        immutableUsername: true,
        displayUsername: false,
      }),
      bearer({ requireSignature: true }),
      jwt({
        disableSettingJwtHeader: true,
        jwks: { keyPairConfig: { alg: "RS256", modulusLength: 2048 } },
        jwt: {
          issuer: config.issuer,
          audience: "mt2-game",
          expirationTime: `${config.jwtSeconds}s`,
          definePayload: () => ({}),
          getSubject: ({ user }) => user.id,
        },
      }),
    ],
  });
  try {
    const migrations = await getMigrations(auth.options);
    if (migrations.schemaProblems.length || migrations.unsafeChanges.length) {
      throw new Error("The authentication database needs an explicit schema migration.");
    }
    await migrations.runMigrations();
    await auth.$context;
    return { auth, database };
  } catch (error) {
    database.close();
    throw error;
  }
}
