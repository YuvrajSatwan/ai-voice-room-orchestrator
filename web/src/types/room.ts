/**
 * The contract with the existing backend. Mirrors exactly what it publishes into the room:
 * - `roxstar.chat`  (src/roxstar/voices.py, worker.py): transcript lines and bot replies
 * - `roxstar.event` (brain.py, listener.py via worker.py): orchestration state, no text
 */

export type Persona = 'dost' | 'sathi';
export type Channel = 'voice' | 'text';

export interface ChatMessage {
  type: 'roxstar.chat';
  sender: string;
  identity?: string;
  text: string;
  channel: Channel;
}

interface EventBase {
  type: 'roxstar.event';
  at: number; // server time, seconds
}

export type RoomEvent = EventBase &
  (
    | {
        event: 'routed';
        turn_id: string;
        speaker: string;
        channel: Channel;
        bots: Persona[];
        reason: string;
      }
    | { event: 'thinking'; turn_id: string; bot: Persona }
    | {
        event: 'turn_done';
        turn_id: string;
        speaker: string;
        channel: Channel;
        bot: Persona;
        outcome: string;
        floor_ms?: number;
        llm_ms?: number;
        chat_posted_ms?: number;
        first_audio_ms?: number;
        total_ms?: number;
      }
    | { event: 'interrupted'; bot: Persona | null; by: string }
    | { event: 'llm_failed'; turn_id: string; bot: Persona; error: string }
    | { event: 'tts_failed'; turn_id: string; bot: Persona; error: string }
    | { event: 'moderated'; turn_id: string; speaker: string; bot: Persona }
    | { event: 'summary_updated'; turns_merged: number }
    | { event: 'failure_armed'; stage: string }
    | { event: 'stt_failed'; speaker: string; error: string; attempt: number; retry_in_s: number }
    | { event: 'stt_recovered'; speaker: string }
  );

export type RoomEventName = RoomEvent['event'];

export interface Session {
  url: string;
  token: string;
  name: string;
  room: string;
}
