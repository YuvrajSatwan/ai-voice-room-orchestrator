import { useEffect, useState } from 'react';

/**
 * Re-render once `until` (a timestamp) has passed. Used to let a real event's label
 * (e.g. "Interrupted") settle back after a moment, without polling.
 */
export function useExpiry(until: number | undefined): boolean {
  const [, force] = useState(0);
  const expired = until === undefined || Date.now() >= until;
  useEffect(() => {
    if (until === undefined) return;
    const wait = until - Date.now();
    if (wait <= 0) return;
    const timer = window.setTimeout(() => force((n) => n + 1), wait + 16);
    return () => window.clearTimeout(timer);
  }, [until]);
  return expired;
}

/** A clock that ticks every `intervalMs`: for "12 s ago" style labels only. */
export function useTick(intervalMs: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(timer);
  }, [intervalMs]);
  return now;
}
