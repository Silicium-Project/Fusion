import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

if (process.env.SILICIUM_SKIP_FRONTEND_BUILD === "1") {
  console.log("Skipping frontend build; reusing the existing dist/ output.");
  process.exit(0);
}

const isWindows = process.platform === "win32";
// Windows treats .cmd files as shell scripts. Spawning npm.cmd directly with
// shell:false makes Node return EINVAL on the hosted Windows runner, while
// invoking it through cmd.exe keeps the process behavior explicit on both
// local and CI builds.
const command = isWindows ? (process.env.ComSpec || "cmd.exe") : "npm";
const args = isWindows ? ["/d", "/s", "/c", "npm.cmd run build"] : ["run", "build"];
const appRoot = fileURLToPath(new URL("..", import.meta.url));
const result = spawnSync(command, args, {
  cwd: appRoot,
  stdio: "inherit",
  shell: false,
});

if (result.error) {
  console.error(`Unable to start ${command}: ${result.error.message}`);
  process.exit(1);
}

process.exit(result.status ?? 1);
