import type { JoinError } from '../../services/tokenService';

export function JoinErrorNote({ error }: { error: JoinError }) {
  return (
    <div className="join__error" role="alert">
      <p>{error.message}</p>
      {error.kind === 'unreachable' && import.meta.env.DEV && (
        <p className="join__hint">
          Start it with <code>python -m roxstar.token_server</code>, then try again.
        </p>
      )}
      {error.kind === 'unreachable' && !import.meta.env.DEV && (
        <p className="join__hint">It may be waking up. Wait a few seconds and try again.</p>
      )}
    </div>
  );
}
