import { readFile } from "node:fs/promises";

const workerUrl = new URL("../dist/coachiq-sw.js", import.meta.url);
const worker = await readFile(workerUrl, "utf8");
const recoveryUrl = new URL("../dist/stale-asset-recovery.js", import.meta.url);
const recovery = await readFile(recoveryUrl, "utf8");

const requiredMarkers = [
  "NetworkFirst",
  "PrecacheFallbackPlugin",
  "coachiq-navigation-v1"
];

for (const marker of requiredMarkers) {
  if (!worker.includes(marker)) {
    throw new Error(`Generated service worker is missing ${marker}`);
  }
}

if (worker.includes("NavigationRoute")) {
  throw new Error("Generated service worker must not use a precached NavigationRoute");
}

for (const marker of ["registration.update()", "resetServiceWorker", "window.location.reload()"]) {
  if (!recovery.includes(marker)) {
    throw new Error(`Stale asset recovery module is missing ${marker}`);
  }
}

console.log("Verified network-first PWA navigation and stale-asset recovery");
