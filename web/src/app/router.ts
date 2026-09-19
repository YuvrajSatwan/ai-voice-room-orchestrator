/**
 * Two routes, so no router library: "/" (landing) and "/room/:code".
 * Built on the History API; the static host rewrites every path to index.html.
 */
import { useSyncExternalStore } from 'react';

export type Route = { page: 'home' } | { page: 'room'; code: string };

/** Set when the landing page sends someone into a room they just created or asked to join. */
export interface EnterIntent {
  name: string;
}

const CHANGE = 'roxstar:navigate';

export function parseRoute(pathname: string): Route {
  const match = /^\/room\/([^/]+)\/?$/.exec(pathname);
  if (match) return { page: 'room', code: decodeURIComponent(match[1]) };
  return { page: 'home' };
}

export function roomPath(code: string): string {
  return `/room/${encodeURIComponent(code)}`;
}

export function navigate(path: string, intent?: EnterIntent, { replace = false } = {}): void {
  const state = intent ? { enter: intent } : null;
  if (replace) window.history.replaceState(state, '', path);
  else window.history.pushState(state, '', path);
  window.dispatchEvent(new Event(CHANGE));
}

/** The intent passed by `navigate`, consumed once so a refresh doesn't auto-join again. */
export function takeEnterIntent(): EnterIntent | null {
  const intent = (window.history.state as { enter?: EnterIntent } | null)?.enter ?? null;
  if (intent) window.history.replaceState(null, '', window.location.href);
  return intent;
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener('popstate', onChange);
  window.addEventListener(CHANGE, onChange);
  return () => {
    window.removeEventListener('popstate', onChange);
    window.removeEventListener(CHANGE, onChange);
  };
}

const currentPath = () => window.location.pathname;

export function useRoute(): Route {
  return parseRoute(useSyncExternalStore(subscribe, currentPath));
}
