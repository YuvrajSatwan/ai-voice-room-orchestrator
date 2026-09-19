import { type FormEvent, useState } from 'react';
import { AI_ORDER, AI_PROFILES } from '../../lib/personas';
import { JoinError, requestSession } from '../../services/tokenService';
import type { Session } from '../../types/room';
import { AiGlyph } from '../participants/AiGlyph';
import { MicCheck } from './MicCheck';

export function JoinScreen({
  initialName,
  initialRoom,
  onJoined,
}: {
  initialName: string;
  initialRoom: string;
  onJoined: (session: Session) => void;
}) {
  const [name, setName] = useState(initialName);
  const [room, setRoom] = useState(initialRoom);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<JoinError | null>(null);
  const ready = name.trim().length > 0 && room.trim().length > 0 && !busy;

  const join = async (event: FormEvent) => {
    event.preventDefault();
    if (!ready) return;
    setBusy(true);
    setError(null);
    try {
      onJoined(await requestSession(name.trim(), room.trim()));
    } catch (e) {
      setError(e instanceof JoinError ? e : new JoinError('rejected', 'Something went wrong.'));
      setBusy(false);
    }
  };

  return (
    <main className="join">
      <div className="join__inner">
        <header className="join__intro">
          <p className="wordmark">Roxstar</p>
          <h1 className="join__title">AI Voice Room</h1>
          <p className="join__lead">Talk naturally. They'll listen.</p>
        </header>

        <form className="join__form" onSubmit={join} noValidate>
          <div className="field">
            <label className="field__label" htmlFor="join-name">
              Name
            </label>
            <input
              id="join-name"
              className="field__input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Rahul"
              autoComplete="given-name"
              maxLength={64}
              autoFocus={!initialName}
              required
            />
          </div>
          <div className="field">
            <label className="field__label" htmlFor="join-room">
              Room
            </label>
            <input
              id="join-room"
              className="field__input"
              value={room}
              onChange={(e) => setRoom(e.target.value)}
              placeholder="roxstar-demo"
              autoComplete="off"
              maxLength={128}
              required
            />
          </div>
          <div className="field">
            <span className="field__label">Microphone</span>
            <MicCheck />
          </div>

          <ul className="join__cast" aria-label="AI participants in every room">
            {AI_ORDER.map((persona) => (
              <li key={persona}>
                <AiGlyph persona={persona} state="listening" size="sm" />
                <span>
                  {AI_PROFILES[persona].name}
                  <span className="join__cast-meta"> · AI</span>
                </span>
              </li>
            ))}
          </ul>

          <button type="submit" className="btn btn--primary join__submit" disabled={!ready}>
            {busy ? (
              <>
                <span className="spinner" aria-hidden="true" /> Joining…
              </>
            ) : (
              'Join room'
            )}
          </button>

          {error && (
            <div className="join__error" role="alert">
              <p>{error.message}</p>
              {error.kind === 'unreachable' && (
                <p className="join__hint">
                  Start it with <code>python -m roxstar.token_server</code>, then try again.
                </p>
              )}
            </div>
          )}
        </form>
      </div>
    </main>
  );
}
