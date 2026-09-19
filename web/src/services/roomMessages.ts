/** Decode and encode the backend's room data messages. */
import type { ChatMessage, RoomEvent } from '../types/room';

const decoder = new TextDecoder();
const encoder = new TextEncoder();

export type Incoming = { kind: 'chat'; message: ChatMessage } | { kind: 'event'; event: RoomEvent };

export function decode(payload: Uint8Array): Incoming | null {
  let data: unknown;
  try {
    data = JSON.parse(decoder.decode(payload));
  } catch {
    return null; // not ours
  }
  if (!data || typeof data !== 'object') return null;
  const record = data as Record<string, unknown>;
  if (record.type === 'roxstar.chat' && typeof record.text === 'string') {
    return { kind: 'chat', message: record as unknown as ChatMessage };
  }
  if (record.type === 'roxstar.event' && typeof record.event === 'string') {
    return { kind: 'event', event: record as unknown as RoomEvent };
  }
  return null;
}

/** A typed message, in the exact shape the worker's parse_chat() accepts. */
export function encodeChat(sender: string, text: string): Uint8Array<ArrayBuffer> {
  const message: ChatMessage = { type: 'roxstar.chat', sender, text, channel: 'text' };
  return encoder.encode(JSON.stringify(message));
}
