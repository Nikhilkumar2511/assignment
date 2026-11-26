import { buildApp } from "./app";
import { config } from "./config";
import { JsonlSink, PostgresSink, Sink } from "./learning";
import { SnapshotHolder } from "./snapshot";

async function main() {
  const holder = new SnapshotHolder(config.snapshotDir);
  const kb = await holder.reload();
  const sink: Sink = config.databaseUrl ? new PostgresSink(config.databaseUrl) : new JsonlSink(config.learningLog);
  const app = await buildApp(config, holder, sink);
  app.log.info({ snapshot: config.snapshotDir, characters: kb.n, questions: kb.questions.length, source: kb.source },
    "snapshot loaded");
  process.on("SIGHUP", () => {
    holder.reload().then(
      (k) => app.log.info({ version: k.version, characters: k.n }, "snapshot reloaded"),
      (err) => app.log.error(err, "snapshot reload failed; keeping the old one"),
    );
  });
  const stop = async () => {
    await app.close();
    await sink.close();
    process.exit(0);
  };
  process.on("SIGTERM", stop);
  process.on("SIGINT", stop);
  await app.listen({ port: config.port, host: config.host });
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
