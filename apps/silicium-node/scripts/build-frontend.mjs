import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

if (process.env.SILICIUM_SKIP_FRONTEND_BUILD === "1") {
  console.log("Skipping frontend build; reusing the existing dist/ output.");
  process.exit(0);
}

const npm = process.platform === "win32" ? "npm.cmd" : "npm";
const appRoot = fileURLToPath(new URL("..", import.meta.url));
const result = spawnSync(npm, ["run", "build"], {
  cwd: appRoot,
  stdio: "inherit",
  shell: false,
});

if (result.error) {
  console.error(`Unable to start ${npm}: ${result.error.message}`);
  process.exit(1);
}

process.exit(result.status ?? 1);
