/**
 * The only HTTP call the frontend makes: the existing token service
 * (src/roxstar/token_server.py). POST /token also brings the AI worker into the room.
 */
import type { Session } from '../types/room';

const RAW_URL = (import.meta.env.VITE_TOKEN_URL as string | undefined) ?? 'http://127.0.0.1:8000';
const BASE_URL =
  RAW_URL.startsWith('http://') || RAW_URL.startsWith('https://') ? RAW_URL : `https://${RAW_URL}`;

export class JoinError extends Error {
  constructor(
    readonly kind: 'unreachable' | 'rejected',
    message: string,
  ) {
    super(message);
  }
}

export async function requestSession(name: string, room: string): Promise<Session> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, room }),
    });
  } catch {
    throw new JoinError('unreachable', "Can't reach the Roxstar room service.");
  }

  const body = (await response.json().catch(() => ({}))) as {
    token?: string;
    url?: string;
    error?: string;
  };
  if (!response.ok || !body.token || !body.url) {
    throw new JoinError('rejected', body.error ?? 'The room service could not start a session.');
  }
  return { url: body.url, token: body.token, name, room };
}
