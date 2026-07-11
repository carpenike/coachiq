import { beforeEach, describe, expect, it } from "vitest"

import {
  DEFAULT_DEVICE_PREFERENCES,
  PREFERENCES_STORAGE_KEY,
  createPreferencesStore,
} from "@/hooks/usePreferences"

describe("preferences store", () => {
  beforeEach(() => localStorage.clear())

  it("persists favorite ordering and compact section configuration", () => {
    const store = createPreferencesStore(localStorage)

    store.update((current) => ({
      ...current,
      wallPanelEnabled: true,
      home: {
        favoriteEntityIds: [" light.kitchen ", "tank.fresh", "light.kitchen"],
        sectionOrder: ["zones", "alerts", "power", "scenes"],
        hiddenSections: ["alerts"],
      },
    }))

    expect(store.getSnapshot()).toEqual({
      version: 1,
      wallPanelEnabled: true,
      home: {
        favoriteEntityIds: ["light.kitchen", "tank.fresh"],
        sectionOrder: ["zones", "alerts", "power", "scenes"],
        hiddenSections: ["alerts"],
      },
    })

    const reloaded = createPreferencesStore(localStorage)
    expect(reloaded.getSnapshot()).toEqual(store.getSnapshot())
    expect(localStorage.getItem(PREFERENCES_STORAGE_KEY)).toContain("light.kitchen")
  })

  it("repairs malformed and partial stored preferences", () => {
    localStorage.setItem(
      PREFERENCES_STORAGE_KEY,
      JSON.stringify({
        wallPanelEnabled: "yes",
        home: {
          favoriteEntityIds: [null, "valid", "valid"],
          sectionOrder: ["zones", "invalid"],
          hiddenSections: ["power", "invalid"],
        },
      })
    )

    expect(createPreferencesStore(localStorage).getSnapshot()).toEqual({
      version: 1,
      wallPanelEnabled: false,
      home: {
        favoriteEntityIds: ["valid"],
        sectionOrder: ["zones", "alerts", "scenes", "power"],
        hiddenSections: ["power"],
      },
    })

    localStorage.setItem(PREFERENCES_STORAGE_KEY, "not-json")
    expect(createPreferencesStore(localStorage).getSnapshot()).toEqual(
      DEFAULT_DEVICE_PREFERENCES
    )
  })
})
