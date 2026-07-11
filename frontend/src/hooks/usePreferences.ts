import { useSyncExternalStore } from "react"

export const PREFERENCES_STORAGE_KEY = "coachiq.device-preferences.v1"

export const HOME_SECTION_IDS = ["alerts", "scenes", "power", "zones"] as const

export type HomeSectionId = (typeof HOME_SECTION_IDS)[number]

export interface IHomePreferences {
  favoriteEntityIds: string[]
  sectionOrder: HomeSectionId[]
  hiddenSections: HomeSectionId[]
}

export interface IDevicePreferences {
  version: 1
  wallPanelEnabled: boolean
  home: IHomePreferences
}

type PreferencesUpdater = (current: IDevicePreferences) => IDevicePreferences
type PreferencesListener = () => void

export interface IPreferencesStore {
  getSnapshot: () => IDevicePreferences
  subscribe: (listener: PreferencesListener) => () => void
  update: (updater: PreferencesUpdater) => void
  replaceSerialized: (serialized: string | null) => void
}

export const DEFAULT_DEVICE_PREFERENCES: IDevicePreferences = {
  version: 1,
  wallPanelEnabled: false,
  home: {
    favoriteEntityIds: [],
    sectionOrder: [...HOME_SECTION_IDS],
    hiddenSections: [],
  },
}

function uniqueStrings(value: unknown): string[] {
  if (!Array.isArray(value)) return []

  return [
    ...new Set(
      value
        .filter((item): item is string => typeof item === "string")
        .map((item) => item.trim())
        .filter(Boolean)
    ),
  ]
}

function normalizeSectionIds(value: unknown): HomeSectionId[] {
  const allowed = new Set<string>(HOME_SECTION_IDS)
  return uniqueStrings(value).filter((item): item is HomeSectionId => allowed.has(item))
}

export function normalizeHomePreferences(value: unknown): IHomePreferences {
  const candidate = value && typeof value === "object"
    ? (value as Partial<IHomePreferences>)
    : {}
  const configuredOrder = normalizeSectionIds(candidate.sectionOrder)
  const missingSections = HOME_SECTION_IDS.filter(
    (section) => !configuredOrder.includes(section)
  )

  return {
    favoriteEntityIds: uniqueStrings(candidate.favoriteEntityIds),
    sectionOrder: [...configuredOrder, ...missingSections],
    hiddenSections: normalizeSectionIds(candidate.hiddenSections),
  }
}

export function normalizeDevicePreferences(value: unknown): IDevicePreferences {
  if (!value || typeof value !== "object") return structuredClone(DEFAULT_DEVICE_PREFERENCES)

  const candidate = value as Partial<IDevicePreferences>
  const homeCandidate =
    candidate.home && typeof candidate.home === "object"
      ? (candidate.home as Partial<IHomePreferences>)
      : {}

  return {
    version: 1,
    wallPanelEnabled: candidate.wallPanelEnabled === true,
    home: normalizeHomePreferences(homeCandidate),
  }
}

function parsePreferences(serialized: string | null): IDevicePreferences {
  if (!serialized) return structuredClone(DEFAULT_DEVICE_PREFERENCES)

  try {
    return normalizeDevicePreferences(JSON.parse(serialized) as unknown)
  } catch {
    return structuredClone(DEFAULT_DEVICE_PREFERENCES)
  }
}

function browserStorage(): Storage | null {
  if (typeof window === "undefined") return null

  try {
    return window.localStorage
  } catch {
    return null
  }
}

export function createPreferencesStore(storage: Storage | null): IPreferencesStore {
  let current = parsePreferences(storage?.getItem(PREFERENCES_STORAGE_KEY) ?? null)
  const listeners = new Set<PreferencesListener>()

  const emit = () => {
    listeners.forEach((listener) => listener())
  }

  const persist = () => {
    try {
      storage?.setItem(PREFERENCES_STORAGE_KEY, JSON.stringify(current))
    } catch {
      // Preferences remain usable for this tab when storage is unavailable or full.
    }
  }

  return {
    getSnapshot: () => current,
    subscribe: (listener) => {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
    update: (updater) => {
      current = normalizeDevicePreferences(updater(current))
      persist()
      emit()
    },
    replaceSerialized: (serialized) => {
      current = parsePreferences(serialized)
      emit()
    },
  }
}

const preferencesStore = createPreferencesStore(browserStorage())

if (typeof window !== "undefined") {
  window.addEventListener("storage", (event) => {
    if (event.key === PREFERENCES_STORAGE_KEY) {
      preferencesStore.replaceSerialized(event.newValue)
    }
  })
}

function updatePreferences(updater: PreferencesUpdater) {
  preferencesStore.update(updater)
}

export function setWallPanelEnabled(enabled: boolean) {
  updatePreferences((current) => ({ ...current, wallPanelEnabled: enabled }))
}

export function replaceHomePreferences(home: IHomePreferences) {
  updatePreferences((current) => ({
    ...current,
    home: normalizeHomePreferences(home),
  }))
}

export function setFavoriteEntityIds(entityIds: string[]) {
  updatePreferences((current) => ({
    ...current,
    home: { ...current.home, favoriteEntityIds: entityIds },
  }))
}

export function setHomeSectionVisible(section: HomeSectionId, visible: boolean) {
  updatePreferences((current) => ({
    ...current,
    home: {
      ...current.home,
      hiddenSections: visible
        ? current.home.hiddenSections.filter((item) => item !== section)
        : [...current.home.hiddenSections, section],
    },
  }))
}

export function moveHomeSection(section: HomeSectionId, direction: -1 | 1) {
  updatePreferences((current) => {
    const currentIndex = current.home.sectionOrder.indexOf(section)
    const targetIndex = currentIndex + direction
    if (
      currentIndex < 0 ||
      targetIndex < 0 ||
      targetIndex >= current.home.sectionOrder.length
    ) {
      return current
    }

    const target = current.home.sectionOrder.at(targetIndex)
    if (!target) return current

    const sectionOrder = current.home.sectionOrder.map((item, index) => {
      if (index === currentIndex) return target
      if (index === targetIndex) return section
      return item
    })
    return { ...current, home: { ...current.home, sectionOrder } }
  })
}

export function usePreferences() {
  return useSyncExternalStore(
    preferencesStore.subscribe,
    preferencesStore.getSnapshot,
    preferencesStore.getSnapshot
  )
}

export function useHomePreferences() {
  return usePreferences().home
}
