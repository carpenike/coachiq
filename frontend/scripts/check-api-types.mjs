/* eslint-disable sonarjs/no-os-command-from-path -- Type generation scripts intentionally run developer/CI tooling from PATH. */

import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { runOpenApiExport } from "./api-typegen-utils.mjs";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const frontendRoot = resolve(scriptDir, "..");
const repoRoot = resolve(frontendRoot, "..");
const generatedPath = join(frontendRoot, "src/api/generated/openapi-types.ts");
const tempDir = mkdtempSync(join(tmpdir(), "coachiq-openapi-"));
const tempTypesPath = join(tempDir, "openapi-types.ts");

try {
  runOpenApiExport(repoRoot, tempDir);
  execFileSync(
    "npx",
    [
      "openapi-typescript",
      join(tempDir, "openapi.json"),
      "--default-non-nullable",
      "false",
      "-o",
      tempTypesPath
    ],
    { cwd: frontendRoot, stdio: "inherit" }
  );

  const expected = readFileSync(tempTypesPath, "utf8");
  const current = readFileSync(generatedPath, "utf8");

  if (expected !== current) {
    console.error(
      "Generated OpenAPI types are stale. Run `npm run gen:api` from frontend/."
    );
    process.exitCode = 1;
  }
} finally {
  rmSync(tempDir, { recursive: true, force: true });
}
