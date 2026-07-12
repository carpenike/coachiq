const recoveryKey = "coachiq:stale-asset-recovery";
const retryWindowMs = 15000;

function showRecoveryMessage() {
  const root = document.getElementById("root");
  if (!root) return;

  const message = document.createElement("p");
  message.textContent = "CoachIQ was updated. Close this tab, then reopen CoachIQ.";
  message.style.cssText = "margin:4rem auto;max-width:32rem;padding:1rem;font:16px sans-serif";
  root.replaceChildren(message);
}

async function resetServiceWorker() {
  const registrations = await navigator.serviceWorker.getRegistrations();
  await Promise.all(registrations.map((registration) => registration.unregister()));
  const cacheNames = await caches.keys();
  await Promise.all(cacheNames.map((cacheName) => caches.delete(cacheName)));
}

async function recoverStaleAsset() {
  const previousAttempt = Number(sessionStorage.getItem(recoveryKey) || "0");
  if (Date.now() - previousAttempt < retryWindowMs) {
    showRecoveryMessage();
    return;
  }
  sessionStorage.setItem(recoveryKey, String(Date.now()));

  const registration = await navigator.serviceWorker.getRegistration();
  if (!registration) {
    window.location.reload();
    return;
  }

  let controllerChanged = false;
  const controllerChange = new Promise((resolve) => {
    navigator.serviceWorker.addEventListener(
      "controllerchange",
      () => {
        controllerChanged = true;
        resolve(undefined);
      },
      { once: true }
    );
    window.setTimeout(() => resolve(undefined), 5000);
  });

  await registration.update();
  if (registration.waiting) registration.waiting.postMessage({ type: "SKIP_WAITING" });
  await controllerChange;
  if (!controllerChanged) await resetServiceWorker();
  window.location.reload();
}

recoverStaleAsset().catch(async () => {
  try {
    await resetServiceWorker();
    window.location.reload();
  } catch {
    showRecoveryMessage();
  }
});
