import { useCallback, useState } from 'react';
import { JoinScreen } from '../features/join/JoinScreen';
import { RoomScreen } from '../features/room/RoomScreen';
import { requestSession } from '../services/tokenService';
import type { Session } from '../types/room';

const NAME_KEY = 'roxstar.name';

function storedName(): string {
  try {
    return localStorage.getItem(NAME_KEY) ?? '';
  } catch {
    return '';
  }
}

function roomFromUrl(): string {
  return new URLSearchParams(window.location.search).get('room')?.trim() || 'roxstar-demo';
}

export function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [visit, setVisit] = useState(0); // a new key per join, so each visit gets a fresh Room

  const join = useCallback((next: Session) => {
    try {
      localStorage.setItem(NAME_KEY, next.name);
    } catch {
      /* private mode: remembering the name is only a convenience */
    }
    setVisit((v) => v + 1);
    setSession(next);
  }, []);

  const leave = useCallback(() => setSession(null), []);

  const rejoin = useCallback(async () => {
    if (!session) return;
    try {
      join(await requestSession(session.name, session.room)); // fresh token, bots re-dispatched
    } catch {
      setSession(null);
    }
  }, [session, join]);

  if (!session) {
    return <JoinScreen initialName={storedName()} initialRoom={roomFromUrl()} onJoined={join} />;
  }
  return <RoomScreen key={visit} session={session} onLeave={leave} onRejoin={() => void rejoin()} />;
}
