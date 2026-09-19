import { RoomAudioRenderer, RoomContext, useLocalParticipant } from '@livekit/components-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { SessionContext, useSession } from '../../app/context';
import { type RoomPeople, useRoomPeople } from '../../hooks/useRoomPeople';
import { useRoomSession } from '../../hooks/useRoomSession';
import { AI_ORDER } from '../../lib/personas';
import type { Session } from '../../types/room';
import { Composer } from '../conversation/Composer';
import { Transcript } from '../conversation/Transcript';
import { IntelligencePanel } from '../intelligence/IntelligencePanel';
import { AiGlyph } from '../participants/AiGlyph';
import { AiPresence } from '../participants/AiPresence';
import { HumanPresence } from '../participants/HumanPresence';
import { Controls } from '../voice/Controls';
import { RoomHeader } from './RoomHeader';
import { RoomNotice } from './RoomNotice';
import { RoomStatus } from './RoomStatus';

export function RoomScreen({
  session,
  onLeave,
  onRejoin,
}: {
  session: Session;
  onLeave: () => void;
  onRejoin: () => void;
}) {
  const roomSession = useRoomSession(session);
  const { phase } = roomSession;

  useEffect(() => {
    if (phase === 'left') onLeave();
  }, [phase, onLeave]);

  return (
    <SessionContext.Provider value={roomSession}>
      <RoomContext.Provider value={roomSession.room}>
        {phase === 'connecting' ? (
          <Joining room={session.title || session.room} />
        ) : phase === 'lost' || phase === 'failed' ? (
          <RoomEnded failed={phase === 'failed'} onRejoin={onRejoin} onLeave={onLeave} />
        ) : (
          <RoomLayout session={session} />
        )}
      </RoomContext.Provider>
    </SessionContext.Provider>
  );
}

function RoomLayout({ session }: { session: Session }) {
  const people = useRoomPeople();
  const { phase } = useSession();
  const { localParticipant } = useLocalParticipant();
  const [outputMuted, setOutputMuted] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const panelTrigger = useRef<HTMLElement | null>(null);
  const botsPresent = AI_ORDER.every((p) => people.bots[p]);

  const togglePanel = useCallback(() => {
    setPanelOpen((open) => {
      if (!open) panelTrigger.current = document.activeElement as HTMLElement;
      return !open;
    });
  }, []);
  const closePanel = useCallback(() => {
    setPanelOpen(false);
    panelTrigger.current?.focus(); // focus returns to where it came from
  }, []);

  return (
    <div className="room" data-panel={panelOpen || undefined}>
      <RoomHeader
        room={session.room}
        title={session.title}
        phase={phase}
        panelOpen={panelOpen}
        onTogglePanel={togglePanel}
      />
      <RoomNotice botsPresent={botsPresent} />

      <main className="room__body">
        <section className="stage" aria-label="People in the room">
          <RoomStatus brainPresent={people.brainPresent} botsPresent={botsPresent} />
          <div className="stage__cluster">
            <div className="stage__ai">
              {AI_ORDER.map((persona) => (
                <AiPresence
                  key={persona}
                  persona={persona}
                  participant={people.bots[persona]}
                  brainPresent={people.brainPresent}
                />
              ))}
            </div>
            <Humans people={people} local={localParticipant} />
          </div>
        </section>

        <section className="conversation" aria-label="Conversation">
          <Transcript botsPresent={botsPresent} />
          <div className="conversation__composer">
            <Composer name={session.name} />
          </div>
        </section>

        <div className="room__controls">
          <Controls outputMuted={outputMuted} onToggleOutput={() => setOutputMuted((m) => !m)} />
        </div>
      </main>

      <IntelligencePanel open={panelOpen} onClose={closePanel} people={people} name={session.name} />
      <RoomAudioRenderer muted={outputMuted} />
    </div>
  );
}

function Humans({
  people,
  local,
}: {
  people: RoomPeople;
  local: ReturnType<typeof useLocalParticipant>['localParticipant'];
}) {
  const count = people.humans.length + 1;
  return (
    <div className="stage__humans">
      <h2 className="stage__label">
        <span className="stage__label-text">In the room</span>
        <span className="stage__count" aria-label={`${count} ${count === 1 ? 'person' : 'people'}`}>
          {count}
        </span>
      </h2>
      <ul className="humans">
        <HumanPresence participant={local} isYou />
        {people.humans.map((p) => (
          <HumanPresence key={p.identity} participant={p} isYou={false} />
        ))}
      </ul>
    </div>
  );
}

function Joining({ room }: { room: string }) {
  return (
    <div className="fullscreen" role="status">
      <div className="fullscreen__glyphs">
        <AiGlyph persona="dost" state="joining" size="sm" />
        <AiGlyph persona="sathi" state="joining" size="sm" />
      </div>
      <p className="fullscreen__title">Joining {room}</p>
      <p className="fullscreen__body">Connecting you to the room…</p>
    </div>
  );
}

function RoomEnded({
  failed,
  onRejoin,
  onLeave,
}: {
  failed: boolean;
  onRejoin: () => void;
  onLeave: () => void;
}) {
  return (
    <div className="fullscreen" role="alert">
      <p className="fullscreen__title">{failed ? "Couldn't connect to the room" : 'Connection lost'}</p>
      <p className="fullscreen__body">
        {failed
          ? 'The room service answered, but the connection did not go through.'
          : 'The room is still there. You can rejoin.'}
      </p>
      <div className="fullscreen__actions">
        <button type="button" className="btn btn--primary" onClick={onRejoin}>
          Rejoin
        </button>
        <button type="button" className="btn btn--quiet" onClick={onLeave}>
          Back
        </button>
      </div>
    </div>
  );
}
