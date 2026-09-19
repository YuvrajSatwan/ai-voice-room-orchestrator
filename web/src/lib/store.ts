/**
 * A tiny external store. Components subscribe to a *slice* with a selector, so a new
 * transcript line doesn't re-render participants, and an AI state change doesn't
 * re-render the transcript. (High-frequency audio levels never enter React state at all.)
 */
import { useSyncExternalStore } from 'react';

export interface Store<T> {
  get(): T;
  update(fn: (state: T) => T): void;
  subscribe(listener: () => void): () => void;
}

export function createStore<T>(initial: T): Store<T> {
  let state = initial;
  const listeners = new Set<() => void>();
  return {
    get: () => state,
    update(fn) {
      const next = fn(state);
      if (next === state) return;
      state = next;
      listeners.forEach((listener) => listener());
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

/** Selectors must return stored references (or primitives) so snapshots stay stable. */
export function useStore<T, S>(store: Store<T>, selector: (state: T) => S): S {
  return useSyncExternalStore(store.subscribe, () => selector(store.get()));
}
