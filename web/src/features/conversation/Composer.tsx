import { ArrowUp } from 'lucide-react';
import { type FormEvent, useState } from 'react';
import { useSession } from '../../app/context';
import { encodeChat } from '../../services/roomMessages';

/** Typed messages go into the same room conversation the backend reads (worker.parse_chat). */
export function Composer({ name }: { name: string }) {
  const { room, feed, phase } = useSession();
  const [text, setText] = useState('');
  const [error, setError] = useState(false);
  const [sending, setSending] = useState(false);
  const connected = phase === 'connected';
  const canSend = connected && text.trim().length > 0 && !sending;

  const send = async (event: FormEvent) => {
    event.preventDefault();
    const message = text.trim();
    if (!message || !connected || sending) return;
    setSending(true);
    try {
      await room.localParticipant.publishData(encodeChat(name, message), { reliable: true });
      feed.addOwnMessage(name, room.localParticipant.identity, message);
      setText('');
      setError(false);
    } catch {
      setError(true); // keep the text so nothing typed is lost
    } finally {
      setSending(false);
    }
  };

  return (
    <form className="composer" onSubmit={send}>
      <label htmlFor="composer-input" className="visually-hidden">
        Message the room
      </label>
      <input
        id="composer-input"
        className="composer__input"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={connected ? 'Message the room…' : 'Waiting for connection…'}
        autoComplete="off"
        maxLength={500}
        disabled={!connected}
        aria-invalid={error || undefined}
        aria-describedby={error ? 'composer-error' : undefined}
      />
      {/* Tapping send must not take focus from the input: on a phone that would close the
          keyboard and bring the controls back, moving this button before the tap lands. */}
      <button
        type="submit"
        className="composer__send"
        disabled={!canSend}
        aria-label="Send message"
        onMouseDown={(e) => e.preventDefault()}
      >
        {sending ? (
          <span className="spinner" aria-hidden="true" />
        ) : (
          <ArrowUp size={16} strokeWidth={2} aria-hidden="true" />
        )}
      </button>
      {error && (
        <p id="composer-error" className="composer__error" role="alert">
          Couldn't send. Check your connection and try again.
        </p>
      )}
    </form>
  );
}
