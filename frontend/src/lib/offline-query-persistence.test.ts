import { dehydrate, QueryClient } from "@tanstack/react-query";
import type { PersistedClient, Persister } from "@tanstack/react-query-persist-client";
import { describe, expect, it, vi } from "vitest";

import {
  entityCacheDehydrateOptions,
  guardAuthoritativeEntityPersister,
  hasUnconfirmedEntityCommand
} from "@/lib/offline-query-persistence";

const persistedClient: PersistedClient = {
  timestamp: 1,
  buster: "test",
  clientState: { queries: [], mutations: [] }
};

describe("offline entity persistence", () => {
  it("dehydrates successful entity reads but excludes lifecycle and unrelated data", () => {
    const queryClient = new QueryClient();
    queryClient.setQueryData(["entities", "collections", undefined], { entities: [] });
    queryClient.setQueryData(["entities", "entity", "light-1"], { entity_id: "light-1" });
    queryClient.setQueryData(["entities", "command-lifecycle", "light-1", "power"], {
      phase: "confirmed"
    });
    queryClient.setQueryData(["auth", "status"], { enabled: true });

    const dehydrated = dehydrate(queryClient, entityCacheDehydrateOptions);

    expect(dehydrated.mutations).toEqual([]);
    expect(dehydrated.queries.map((query) => query.queryKey)).toEqual([
      ["entities", "collections", undefined],
      ["entities", "entity", "light-1"]
    ]);
  });

  it("preserves the prior snapshot while a command is unconfirmed", async () => {
    const queryClient = new QueryClient();
    const persistClient = vi.fn();
    const persister: Persister = {
      persistClient,
      restoreClient: vi.fn(),
      removeClient: vi.fn()
    };
    const guarded = guardAuthoritativeEntityPersister(queryClient, persister);
    const lifecycleKey = ["entities", "command-lifecycle", "light-1", "power"];

    queryClient.setQueryData(lifecycleKey, { phase: "pending" });
    expect(hasUnconfirmedEntityCommand(queryClient)).toBe(true);
    await guarded.persistClient(persistedClient);
    expect(persistClient).not.toHaveBeenCalled();

    queryClient.setQueryData(lifecycleKey, { phase: "confirmed" });
    await guarded.persistClient(persistedClient);
    expect(persistClient).toHaveBeenCalledWith(persistedClient);
  });
});
