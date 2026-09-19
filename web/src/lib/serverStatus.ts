/**
 * Is the room service awake? Free hosting (Render) puts the backend to sleep when nobody uses
 * it, and the first request after that takes 30-60 s while it starts again.
 *
 * The page checks /health as soon as it opens, which also starts the wake-up while the person
 * types their name. A healthy server answers well within SLOW_MS, so nothing is ever shown.
 * Only if it doesn't do we switch to "waking" and the UI shows a notice with a timer.
 */
import { pingRoomService } from '../services/tokenService';
import { createStore, useStore } from './store';

export type ServerPhase = 'checking' | 'ready' | 'waking' | 'down';

interface ServerState {
  phase: ServerPhase;
  since: number; // when the current check started (for the timer)
}

const SLOW_MS = 2_500; // slower than this: it's asleep and starting up
const RETRY_MS = 3_000; // between checks while it starts (it may answer 502 meanwhile)
const PING_TIMEOUT_MS = 30_000; // one check may be held open while the server boots
const GIVE_UP_MS = 120_000;

const store = createStore<ServerState>({ phase: 'checking', since: Date.now() });
let running = false;

const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

async function check(): Promise<void> {
  if (running) return;
  running = true;
  const since = Date.now();
  store.update(() => ({ phase: 'checking', since }));
  const slow = window.setTimeout(() => {
    store.update((s) => (s.phase === 'checking' ? { phase: 'waking', since } : s));
  }, SLOW_MS);
  try {
    while (Date.now() - since < GIVE_UP_MS) {
      const abort = new AbortController();
      const timeout = window.setTimeout(() => abort.abort(), PING_TIMEOUT_MS);
      const up = await pingRoomService(abort.signal);
      window.clearTimeout(timeout);
      if (up) {
        store.update(() => ({ phase: 'ready', since }));
        return;
      }
      await wait(RETRY_MS);
    }
    store.update(() => ({ phase: 'down', since }));
  } finally {
    window.clearTimeout(slow);
    running = false;
  }
}

/** Start the first check (once per page load). Safe to call from every screen. */
export function watchRoomService(): void {
  if (store.get().phase === 'checking' && !running) void check();
}

/** Check again after giving up ("Try again"). */
export function recheckRoomService(): void {
  void check();
}

export function useRoomServiceStatus(): ServerState {
  return useStore(store, (s) => s);
}
