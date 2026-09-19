import { createContext, useContext } from 'react';
import type { RoomSession } from '../hooks/useRoomSession';

export const SessionContext = createContext<RoomSession | null>(null);

export function useSession(): RoomSession {
  const session = useContext(SessionContext);
  if (!session) throw new Error('useSession must be used inside a room');
  return session;
}
