import { useEffect } from 'react';
import { useTick } from '../../hooks/useNow';
import { recheckRoomService, useRoomServiceStatus, watchRoomService } from '../../lib/serverStatus';

function elapsed(ms: number): string {
  const seconds = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}

/**
 * Shown only while the room service is waking up after sleeping, or if it never answered.
 * When the server is already awake this renders nothing.
 */
export function ServerWakeNotice() {
  const { phase, since } = useRoomServiceStatus();

  useEffect(() => {
    watchRoomService();
  }, []);

  if (phase === 'waking') return <Waking since={since} />;
  if (phase === 'down') {
    return (
      <div className="server-note server-note--down" role="alert">
        <p>
          <strong>The server isn't answering.</strong> It may still be starting, or it may be down.
        </p>
        <button type="button" className="server-note__retry" onClick={recheckRoomService}>
          Try again
        </button>
      </div>
    );
  }
  return null;
}

function Waking({ since }: { since: number }) {
  const now = useTick(1000);
  return (
    <div className="server-note" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <p>
        <strong>Waking up the server…</strong> Free hosting sleeps when nobody is using it, so this first
        start takes up to a minute. You can fill in the form meanwhile.
      </p>
      {/* Hidden from screen readers: a region announcing every tick would be noise. */}
      <span className="server-note__timer" aria-hidden="true">
        {elapsed(now - since)}
      </span>
    </div>
  );
}
