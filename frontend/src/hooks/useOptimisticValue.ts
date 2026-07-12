/**
 * Optimistic local echo for a control bound to server state.
 *
 * Entity commands get this for free from the command lifecycle's cache
 * patching (entity-command-lifecycle.ts); this hook is for controls that
 * talk to endpoints outside that system (e.g. the Victron power controls).
 *
 * The control stays live while a command is in flight — the UI shows the
 * user's intent immediately and reconciles when the server state catches
 * up, when the caller reports failure, or after a settle timeout (so a
 * command that "succeeds" without ever changing state can't wedge the UI
 * on a wrong value).
 */

import { useEffect, useRef, useState } from "react";

const DEFAULT_SETTLE_MS = 10_000;

interface IOptimisticValue<T> {
  /** Value to render: the pending echo if one is live, else the server value. */
  shown: T;
  /** Echo a value the user just chose; starts the settle timeout. */
  setPending: (value: T) => void;
  /** Drop the echo (call on command error or non-success result). */
  clearPending: () => void;
}

export function useOptimisticValue<T>(
  serverValue: T,
  settleMs = DEFAULT_SETTLE_MS
): IOptimisticValue<T> {
  const [pending, setPendingBox] = useState<{ value: T } | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimer = () => {
    if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
    }
  };

  // Server state caught up with the echo — the echo has served its purpose.
  useEffect(() => {
    if (pending !== null && Object.is(serverValue, pending.value)) {
      setPendingBox(null);
      clearTimer();
    }
  }, [pending, serverValue]);

  useEffect(() => clearTimer, []);

  const setPending = (value: T) => {
    setPendingBox({ value });
    clearTimer();
    timer.current = setTimeout(() => {
      setPendingBox(null);
      timer.current = null;
    }, settleMs);
  };

  const clearPending = () => {
    setPendingBox(null);
    clearTimer();
  };

  return { shown: pending === null ? serverValue : pending.value, setPending, clearPending };
}
