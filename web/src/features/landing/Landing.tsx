import { ArrowLeft, ArrowRight, Check, Copy, Link2, LogIn, Plus } from 'lucide-react';
import { type FormEvent, type ReactNode, useState } from 'react';
import { navigate, roomPath } from '../../app/router';
import { useCopy } from '../../hooks/useCopy';
import { AI_ORDER, AI_PROFILES } from '../../lib/personas';
import { cleanName, inviteLink, NAME_MAX, roomCodeFromInput, TITLE_MAX } from '../../lib/roomCode';
import { createRoom, JoinError } from '../../services/tokenService';
import { MicCheck } from '../join/MicCheck';
import { AiGlyph } from '../participants/AiGlyph';
import { JoinErrorNote } from '../join/JoinErrorNote';
import { rememberName, storedName } from '../join/nameStore';

type View = 'home' | 'create' | 'join' | { created: { room: string; title: string } };

export function Landing() {
  const [view, setView] = useState<View>('home');
  const [name, setName] = useState(storedName);
  const home = () => setView('home');

  const enter = (room: string) => {
    rememberName(cleanName(name));
    navigate(roomPath(room), { name: cleanName(name) });
  };

  return (
    <main className="join">
      <div className="join__inner">
        <header className="join__intro">
          <p className="wordmark">Echo</p>
          <h1 className="join__title">AI Voice Room Assistant</h1>
          <p className="join__lead">Real-time conversations with AI participants.</p>
        </header>

        {view === 'home' && (
          <>
            <Cast />
            <div className="landing__actions">
              <button
                type="button"
                className="btn btn--primary join__submit"
                onClick={() => setView('create')}
              >
                <Plus size={17} strokeWidth={2} aria-hidden="true" /> Create room
              </button>
              <button
                type="button"
                className="btn btn--secondary join__submit"
                onClick={() => setView('join')}
              >
                <LogIn size={17} strokeWidth={1.75} aria-hidden="true" /> Join room
              </button>
            </div>
          </>
        )}
        {view === 'create' && (
          <CreateForm
            name={name}
            setName={setName}
            onBack={home}
            onCreated={(created) => setView({ created })}
          />
        )}
        {view === 'join' && <JoinForm name={name} setName={setName} onBack={home} onJoin={enter} />}
        {typeof view === 'object' && (
          <RoomCreated {...view.created} onEnter={() => enter(view.created.room)} onBack={home} />
        )}
      </div>
    </main>
  );
}

/** The two AI participants every room gets. */
function Cast() {
  return (
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
  );
}

function BackLink({ onBack }: { onBack: () => void }) {
  return (
    <button type="button" className="landing__back" onClick={onBack}>
      <ArrowLeft size={15} strokeWidth={1.75} aria-hidden="true" /> Back
    </button>
  );
}

function NameField({ name, setName }: { name: string; setName: (name: string) => void }) {
  return (
    <div className="field">
      <label className="field__label" htmlFor="entry-name">
        Your name
      </label>
      <input
        id="entry-name"
        className="field__input"
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Rahul"
        autoComplete="given-name"
        maxLength={NAME_MAX}
        autoFocus={!name}
        required
      />
    </div>
  );
}

function SubmitButton({
  busy,
  disabled,
  children,
}: {
  busy: boolean;
  disabled: boolean;
  children: ReactNode;
}) {
  return (
    <button type="submit" className="btn btn--primary join__submit" disabled={disabled || busy}>
      {busy ? <span className="spinner" aria-hidden="true" /> : null}
      {children}
    </button>
  );
}

function CreateForm({
  name,
  setName,
  onBack,
  onCreated,
}: {
  name: string;
  setName: (name: string) => void;
  onBack: () => void;
  onCreated: (created: { room: string; title: string }) => void;
}) {
  const [title, setTitle] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<JoinError | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!cleanName(name) || busy) return;
    setBusy(true);
    setError(null);
    try {
      rememberName(cleanName(name));
      onCreated(await createRoom(title.trim()));
    } catch (e) {
      setError(e instanceof JoinError ? e : new JoinError('rejected', 'Something went wrong.'));
      setBusy(false);
    }
  };

  return (
    <form className="join__form" onSubmit={submit} noValidate aria-label="Create a room">
      <BackLink onBack={onBack} />
      <NameField name={name} setName={setName} />
      <div className="field">
        <label className="field__label" htmlFor="entry-title">
          Room name <span className="field__optional">optional</span>
        </label>
        <input
          id="entry-title"
          className="field__input"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Tech Talk"
          autoComplete="off"
          maxLength={TITLE_MAX}
        />
      </div>
      <div className="field">
        <span className="field__label">Microphone</span>
        <MicCheck />
      </div>
      <SubmitButton busy={busy} disabled={!cleanName(name)}>
        {busy ? 'Creating…' : 'Create room'}
      </SubmitButton>
      {error && <JoinErrorNote error={error} />}
    </form>
  );
}

function RoomCreated({
  room,
  title,
  onEnter,
  onBack,
}: {
  room: string;
  title: string;
  onEnter: () => void;
  onBack: () => void;
}) {
  const [codeCopied, copyCode] = useCopy();
  const [linkCopied, copyLink] = useCopy();

  return (
    <section className="join__form landing__created" aria-labelledby="created-title">
      <div>
        <p id="created-title" className="landing__created-title" role="status">
          <Check size={16} strokeWidth={2.25} aria-hidden="true" /> Room created
        </p>
        {title && <p className="landing__created-name">{title}</p>}
      </div>
      <div className="landing__code">
        <span className="field__label">Room code</span>
        <code className="landing__code-value">{room}</code>
      </div>
      <div className="landing__copy-row">
        <button type="button" className="btn btn--secondary" onClick={() => copyCode(room)}>
          {codeCopied ? <Check size={15} aria-hidden="true" /> : <Copy size={15} aria-hidden="true" />}
          {codeCopied ? 'Copied' : 'Copy code'}
        </button>
        <button type="button" className="btn btn--secondary" onClick={() => copyLink(inviteLink(room))}>
          {linkCopied ? <Check size={15} aria-hidden="true" /> : <Link2 size={15} aria-hidden="true" />}
          {linkCopied ? 'Copied' : 'Copy invite link'}
        </button>
      </div>
      <p className="landing__note">Share the code or link. Kabir and Saraah join when you enter.</p>
      <button type="button" className="btn btn--primary join__submit" onClick={onEnter} autoFocus>
        Enter room <ArrowRight size={17} strokeWidth={2} aria-hidden="true" />
      </button>
      <BackLink onBack={onBack} />
    </section>
  );
}

function JoinForm({
  name,
  setName,
  onBack,
  onJoin,
}: {
  name: string;
  setName: (name: string) => void;
  onBack: () => void;
  onJoin: (room: string) => void;
}) {
  const [code, setCode] = useState('');
  const [touched, setTouched] = useState(false);
  const room = roomCodeFromInput(code);
  const invalid = touched && code.trim() !== '' && !room;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setTouched(true);
    if (room && cleanName(name)) onJoin(room);
  };

  return (
    <form className="join__form" onSubmit={submit} noValidate aria-label="Join a room">
      <BackLink onBack={onBack} />
      <NameField name={name} setName={setName} />
      <div className="field">
        <label className="field__label" htmlFor="entry-code">
          Room code
        </label>
        <input
          id="entry-code"
          className="field__input"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          onBlur={() => setTouched(true)}
          placeholder="tech-talk-8f3k"
          autoComplete="off"
          autoCapitalize="none"
          spellCheck={false}
          aria-invalid={invalid || undefined}
          aria-describedby={invalid ? 'entry-code-error' : undefined}
          autoFocus={Boolean(name)}
          required
        />
        {invalid && (
          <p id="entry-code-error" className="field__error">
            That doesn't look like a room code. It's like tech-talk-8f3k, or paste the invite link.
          </p>
        )}
      </div>
      <div className="field">
        <span className="field__label">Microphone</span>
        <MicCheck />
      </div>
      <SubmitButton busy={false} disabled={!room || !cleanName(name)}>
        Join room
      </SubmitButton>
    </form>
  );
}
