export function useRegisterSW() {
  return {
    offlineReady: [false, () => undefined] as const,
    needRefresh: [false, () => undefined] as const,
    updateServiceWorker: async () => undefined
  }
}
