/**
 * /room/:code. The code IS the LiveKit room name.
 *
 * Coming from the landing page: joins straight away with the name given there.
 * Opening an invite link: asks for a name first. Errors (room ended, name taken, service
 * unreachable) come back from the room service and are shown here.
 */
import { type FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { navigate, roomPath, takeEnterIntent } from '../../app/router';
import { cleanName, NAME_MAX, normalizeRoomCode } from '../../lib/roomCode';
import { JoinError, requestSession } from '../../services/tokenService';
import type { Session } from '../../types/room';
import { JoinErrorNote } from '../join/JoinErrorNote';
import { MicCheck } from '../join/MicCheck';
import { rememberName, storedName } from '../join/nameStore';
import { AiGlyph } from '../participants/AiGlyph';
import { RoomScreen } from './RoomScreen';

const goHome = () => navigate('/');

export function RoomPage({ code: rawCode }: { code: string }) {
  const code = normalizeRoomCode(rawCode);

  useEffect(() => {
    // Keep one canonical URL per room (/room/TECH-TALK-8F3K -> /room/tech-talk-8f3k).
    if (code && code !== rawCode) navigate(roomPath(code), undefined, { replace: true });
  }, [code, rawCode]);

  if (!code) {
    return (
      <div className="fullscreen" role="alert">
        <p className="fullscreen__title">That room link isn't valid</p>
        <p className="fullscreen__body">
          Room codes look like tech-talk-8f3k. Check the link, or start from the home page.
        </p>
        <div className="fullscreen__actions">
          <button type="button" className="btn btn--primary" onClick={goHome}>
            Go to home
          </button>
        </div>
      </div>
    );
  }
  return <RoomEntry key={code} code={code} />;
}

function RoomEntry({ code }: { code: string }) {
  const [session, setSession] = useState<Session | null>(null);
  const [visit, setVisit] = useState(0); // a new key per join, so each visit gets a fresh Room
  const [joining, setJoining] = useState(false);
  const [error, setError] = useState<JoinError | null>(null);
  const [name, setName] = useState(storedName);
  const started = useRef(false);

  const join = useCallback(
    async (who: string, mode: 'join' | 'rejoin' = 'join') => {
      setJoining(true);
      setError(null);
      try {
        const next = await requestSession(who, code, mode);
        rememberName(who);
        setVisit((v) => v + 1);
        setSession(next);
      } catch (e) {
        setSession(null);
        setError(e instanceof JoinError ? e : new JoinError('rejected', 'Something went wrong.'));
      } finally {
        setJoining(false);
      }
    },
    [code],
  );

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const intent = takeEnterIntent();
    if (intent?.name) void join(intent.name);
  }, [join]);

  if (session) {
    return (
      <RoomScreen
        key={visit}
        session={session}
        onLeave={goHome}
        onRejoin={() => void join(session.name, 'rejoin')}
      />
    );
  }

  if (joining) {
    return (
      <div className="fullscreen" role="status">
        <div className="fullscreen__glyphs">
          <AiGlyph persona="dost" state="joining" size="sm" />
          <AiGlyph persona="sathi" state="joining" size="sm" />
        </div>
        <p className="fullscreen__title">Opening {code}</p>
        <p className="fullscreen__body">Getting the room ready and bringing in Kabir and Saraah…</p>
      </div>
    );
  }

  if (error?.kind === 'not_found') {
    return (
      <div className="fullscreen" role="alert">
        <p className="fullscreen__title">Room not found</p>
        <p className="fullscreen__body">
          <strong>{code}</strong> doesn't exist or has ended. Rooms close a little while after everyone
          leaves.
        </p>
        <div className="fullscreen__actions">
          <button type="button" className="btn btn--primary" onClick={goHome}>
            Create or join a room
          </button>
        </div>
      </div>
    );
  }

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const who = cleanName(name);
    if (who) void join(who);
  };

  return (
    <main className="join">
      <div className="join__inner">
        <header className="join__intro">
          <p className="wordmark">Echo</p>
          <h1 className="join__title">Join the room</h1>
          <p className="join__lead">
            Room code <code className="entry__code">{code}</code>
          </p>
        </header>
        <form className="join__form" onSubmit={submit} noValidate aria-label="Join this room">
          <div className="field">
            <label className="field__label" htmlFor="room-entry-name">
              Your name
            </label>
            <input
              id="room-entry-name"
              className="field__input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Priya"
              autoComplete="given-name"
              maxLength={NAME_MAX}
              autoFocus
              required
            />
          </div>
          <div className="field">
            <span className="field__label">Microphone</span>
            <MicCheck />
          </div>
          <button type="submit" className="btn btn--primary join__submit" disabled={!cleanName(name)}>
            Join room
          </button>
          {error && <JoinErrorNote error={error} />}
          <button type="button" className="landing__back" onClick={goHome}>
            Back to home
          </button>
        </form>
      </div>
    </main>
  );
}
