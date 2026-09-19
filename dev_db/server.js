// Local development database: a real PostgreSQL (via PGlite/WASM) listening on TCP.
// Data is persisted to ./data so it survives restarts. NOT for production.
//
//   cd dev_db && npm install && npm start
//
// Then connect with: postgresql://postgres:postgres@127.0.0.1:55432/postgres?sslmode=disable
const { PGlite } = require("@electric-sql/pglite");
const { PGLiteSocketServer } = require("@electric-sql/pglite-socket");
const path = require("path");

const PORT = Number(process.env.PGLITE_PORT || 55432);
// PGLITE_MEMORY=1 gives a throwaway in-memory database (used by the test suite).
const DATA_DIR = process.env.PGLITE_MEMORY ? undefined : path.join(__dirname, "data");

async function main() {
  const db = new PGlite(DATA_DIR);
  await db.waitReady;
  // Several clients (the app's connection pool, tests, a SQL shell) may connect
  // at once; queries are still executed one at a time internally.
  const server = new PGLiteSocketServer({ db, host: "127.0.0.1", port: PORT, maxConnections: 20 });
  await server.start();
  console.log(`Dev PostgreSQL ready on 127.0.0.1:${PORT} (${DATA_DIR ? "data in " + DATA_DIR : "in-memory"})`);

  const shutdown = async () => {
    await server.stop();
    await db.close();
    process.exit(0);
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
  // A client dropping its socket abruptly must not take the whole server down.
  const CLIENT_ERRORS = new Set(["ECONNRESET", "EPIPE", "ECONNABORTED", "ETIMEDOUT"]);
  process.on("uncaughtException", (err) => {
    if (err && CLIENT_ERRORS.has(err.code)) return;
    console.error(err);
    process.exit(1);
  });
}

main().catch((err) => {
  console.error("Failed to start dev database:", err);
  process.exit(1);
});
