/* eslint-disable sonarjs/no-os-command-from-path -- Type generation scripts intentionally run developer/CI tooling from PATH. */

import { execFileSync } from "node:child_process";

export function runOpenApiExport(repoRoot, outputDir) {
  const args = ["run", "python", "scripts/export_openapi.py", outputDir];
  try {
    execFileSync("poetry", args, { cwd: repoRoot, stdio: "inherit" });
  } catch (error) {
    if (error.code !== "ENOENT") {
      throw error;
    }
    execFileSync(
      "nix",
      ["develop", "--command", "poetry", ...args],
      { cwd: repoRoot, stdio: "inherit" }
    );
  }
}
