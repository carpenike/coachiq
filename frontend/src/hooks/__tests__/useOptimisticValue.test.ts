import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useOptimisticValue } from "@/hooks/useOptimisticValue";

describe("useOptimisticValue", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows the server value until a pending echo is set", () => {
    const { result, rerender } = renderHook(({ server }) => useOptimisticValue(server), {
      initialProps: { server: 30 },
    });

    expect(result.current.shown).toBe(30);

    act(() => result.current.setPending(50));
    expect(result.current.shown).toBe(50);

    // Server still reports the old value — the echo wins.
    rerender({ server: 30 });
    expect(result.current.shown).toBe(50);
  });

  it("drops the echo once the server value catches up", () => {
    const { result, rerender } = renderHook(({ server }) => useOptimisticValue(server), {
      initialProps: { server: 30 },
    });

    act(() => result.current.setPending(50));
    rerender({ server: 50 });
    expect(result.current.shown).toBe(50);

    // Echo is gone: a later server change shows through immediately.
    rerender({ server: 15 });
    expect(result.current.shown).toBe(15);
  });

  it("clears the echo on demand (command failure)", () => {
    const { result } = renderHook(({ server }) => useOptimisticValue(server), {
      initialProps: { server: "auto" },
    });

    act(() => result.current.setPending("high"));
    expect(result.current.shown).toBe("high");

    act(() => result.current.clearPending());
    expect(result.current.shown).toBe("auto");
  });

  it("reverts to the server value after the settle timeout", () => {
    const { result } = renderHook(({ server }) => useOptimisticValue(server, 5_000), {
      initialProps: { server: 30 },
    });

    act(() => result.current.setPending(50));
    expect(result.current.shown).toBe(50);

    act(() => {
      vi.advanceTimersByTime(5_000)
    });
    expect(result.current.shown).toBe(30);
  });

  it("restarts the settle timeout on each new echo", () => {
    const { result } = renderHook(({ server }) => useOptimisticValue(server, 5_000), {
      initialProps: { server: 30 },
    });

    act(() => result.current.setPending(50));
    act(() => {
      vi.advanceTimersByTime(4_000)
    });
    act(() => result.current.setPending(20));
    act(() => {
      vi.advanceTimersByTime(4_000)
    });

    // 8s after the first echo, but only 4s after the latest — still echoing.
    expect(result.current.shown).toBe(20);
  });
});
