/* eslint-disable sonarjs/no-os-command-from-path -- Type generation scripts intentionally run developer/CI tooling from PATH. */

import { execFileSync } from "node:child_process";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { runOpenApiExport } from "./api-typegen-utils.mjs";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const frontendRoot = resolve(scriptDir, "..");
const repoRoot = resolve(frontendRoot, "..");

runOpenApiExport(repoRoot, join(repoRoot, "docs/api"));
execFileSync(
  "npx",
  [
    "openapi-typescript",
    join(repoRoot, "docs/api/openapi.json"),
    "--default-non-nullable",
    "false",
    "-o",
    join(frontendRoot, "src/api/generated/openapi-types.ts")
  ],
  { cwd: frontendRoot, stdio: "inherit" }
);
