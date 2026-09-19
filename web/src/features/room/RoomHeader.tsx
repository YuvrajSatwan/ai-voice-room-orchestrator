import { Activity, Check, Copy, Link2 } from 'lucide-react';
import { useCopy } from '../../hooks/useCopy';
import type { SessionPhase } from '../../hooks/useRoomSession';
import { inviteLink } from '../../lib/roomCode';

export function RoomHeader({
  room,
  title,
  phase,
  panelOpen,
  onTogglePanel,
}: {
  room: string;
  title: string;
  phase: SessionPhase;
  panelOpen: boolean;
  onTogglePanel: () => void;
}) {
  const [codeCopied, copyCode] = useCopy();
  const [linkCopied, copyLink] = useCopy();
  const live = phase === 'connected';

  return (
    <header className="room-header">
      <div className="room-header__id">
        <span className="wordmark">Roxstar</span>
        <span className="room-header__room" title={title ? `${title} · ${room}` : room}>
          {title || room}
        </span>
        <button
          type="button"
          className="icon-btn icon-btn--sm"
          onClick={() => copyCode(room)}
          aria-label={codeCopied ? 'Room code copied' : `Copy room code ${room}`}
          data-tip={codeCopied ? 'Copied' : `Copy code · ${room}`}
          data-tip-below=""
        >
          {codeCopied ? (
            <Check size={15} strokeWidth={2} aria-hidden="true" />
          ) : (
            <Copy size={15} strokeWidth={1.75} aria-hidden="true" />
          )}
        </button>
        <button
          type="button"
          className="icon-btn icon-btn--sm"
          onClick={() => copyLink(inviteLink(room))}
          aria-label={linkCopied ? 'Invite link copied' : 'Copy invite link'}
          data-tip={linkCopied ? 'Copied' : 'Copy invite link'}
          data-tip-below=""
        >
          {linkCopied ? (
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
