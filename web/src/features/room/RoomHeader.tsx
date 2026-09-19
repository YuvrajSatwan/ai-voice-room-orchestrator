import { Activity, Check, Link2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { SessionPhase } from '../../hooks/useRoomSession';

function useCopy(): [boolean, (text: string) => void] {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 1600);
    return () => window.clearTimeout(timer);
  }, [copied]);
  const copy = (text: string) => {
    void navigator.clipboard?.writeText(text).then(() => setCopied(true));
  };
  return [copied, copy];
}

export function RoomHeader({
  room,
  phase,
  panelOpen,
  onTogglePanel,
}: {
  room: string;
  phase: SessionPhase;
  panelOpen: boolean;
  onTogglePanel: () => void;
}) {
  const [copied, copy] = useCopy();
  const invite = `${window.location.origin}${window.location.pathname}?room=${encodeURIComponent(room)}`;
  const live = phase === 'connected';

  return (
    <header className="room-header">
      <div className="room-header__id">
        <span className="wordmark">Roxstar</span>
        <span className="room-header__room" title={room}>
          {room}
        </span>
        <button
          type="button"
          className="icon-btn icon-btn--sm"
          onClick={() => copy(invite)}
          aria-label={copied ? 'Invite link copied' : 'Copy invite link'}
          data-tip={copied ? 'Copied' : 'Copy invite link'}
          data-tip-below=""
        >
          {copied ? (
            <Check size={15} strokeWidth={2} aria-hidden="true" />
          ) : (
            <Link2 size={15} strokeWidth={1.75} aria-hidden="true" />
          )}
        </button>
      </div>

      <div className="room-header__side">
        <span
          className="live"
          data-live={live || undefined}
          data-phase={phase}
          role="status"
          aria-label={live ? 'Connected, live' : phase === 'reconnecting' ? 'Reconnecting' : 'Connecting'}
        >
          <span className="live__dot" aria-hidden="true" />
          <span className="live__label">
            {live ? 'Live' : phase === 'reconnecting' ? 'Reconnecting' : 'Connecting'}
          </span>
        </span>
        <button
          type="button"
          className="btn btn--quiet room-header__panel-btn"
          aria-expanded={panelOpen}
          onClick={onTogglePanel}
        >
          <Activity size={16} strokeWidth={1.75} aria-hidden="true" />
          <span className="room-header__panel-label">Intelligence</span>
        </button>
      </div>
    </header>
  );
}
