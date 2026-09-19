import { useEffect } from 'react';
import { Landing } from '../features/landing/Landing';
import { RoomPage } from '../features/room/RoomPage';
import { navigate, roomPath, useRoute } from './router';

/** "/" is the landing page; "/room/:code" is a room. */
export function App() {
  const route = useRoute();

  useEffect(() => {
    // Old invite links looked like /?room=abc. Send them to /room/abc.
    const legacy = new URLSearchParams(window.location.search).get('room')?.trim();
    if (route.page === 'home' && legacy) navigate(roomPath(legacy), undefined, { replace: true });
  }, [route.page]);

  return route.page === 'room' ? <RoomPage code={route.code} /> : <Landing />;
}
