import { describe, expect, it } from "vitest"

import { clearProtectedQueries, createQueryClient, queryKeys } from "@/lib/query-client"

describe("clearProtectedQueries", () => {
  it("retains auth status while removing session-bound data", () => {
    const queryClient = createQueryClient()
    const authStatus = { enabled: true, mode: "multi" }
    queryClient.setQueryData(queryKeys.auth.status(), authStatus)
    queryClient.setQueryData(queryKeys.auth.user(), { user_id: "user-1" })
    queryClient.setQueryData(queryKeys.entities.lists(), [{ entity_id: "light-1" }])

    clearProtectedQueries(queryClient)

    expect(queryClient.getQueryData(queryKeys.auth.status())).toEqual(authStatus)
    expect(queryClient.getQueryData(queryKeys.auth.user())).toBeUndefined()
    expect(queryClient.getQueryData(queryKeys.entities.lists())).toBeUndefined()
  })
})
