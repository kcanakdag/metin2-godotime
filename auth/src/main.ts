import { loadConfig } from "./config.js";
import { startAuthServer } from "./server.js";

process.umask(0o077);
try {
  const config = loadConfig();
  const service = await startAuthServer(config);
  console.info(`MT2 auth listening on ${config.host}:${config.port}`);
  let closing = false;
  const close = async () => {
    if (closing) return;
    closing = true;
    await service.close();
  };
  process.once("SIGTERM", close);
  process.once("SIGINT", close);
} catch {
  console.error("MT2 auth could not start; check configuration, file permissions, and database compatibility.");
  process.exitCode = 1;
}
