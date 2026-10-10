// Start the model separately from the web app: each terminal has one clear job.
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

if (existsSync(".env.local")) process.loadEnvFile(".env.local");
const command = process.argv[2];
if (!["serve", "pull"].includes(command)) throw new Error("Choose serve or pull.");
const directory = join(homedir(), "Library", "Application Support", "June");
const localBinary = join(directory, "runtime", "ollama");
const binary = existsSync(localBinary) ? localBinary : "ollama";
const url = new URL(process.env.OLLAMA_BASE_URL || "http://127.0.0.1:11434");
if (url.protocol !== "http:" || !["127.0.0.1", "localhost", "[::1]"].includes(url.hostname)) {
  throw new Error("June's model server must use a local HTTP address.");
}
const child = spawn(binary, command === "pull" ? ["pull", process.env.JUNE_MODEL || "qwen3:0.6b"] : ["serve"], {
  stdio: "inherit",
  env: {
    ...process.env,
    OLLAMA_HOST: url.host,
    OLLAMA_MODELS: join(directory, "models"),
    OLLAMA_NO_CLOUD: "1",
    OLLAMA_CONTEXT_LENGTH: "4096",
    OLLAMA_NUM_PARALLEL: "1",
    OLLAMA_MAX_LOADED_MODELS: "1",
    OLLAMA_FLASH_ATTENTION: "0",
  },
});
child.on("error", () => {
  console.error("Ollama could not start. See the README's model setup instructions.");
  process.exitCode = 1;
});
child.on("exit", code => { process.exitCode = code || 0; });
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => child.kill(signal));
