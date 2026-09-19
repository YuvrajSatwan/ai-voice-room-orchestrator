/**
 * Turns the backend's room messages into UI state. Everything here comes from a real
 * message; nothing is guessed from timers:
 *
 *   roxstar.chat   -> transcript lines (spoken, typed, AI replies, system notes)
 *   roxstar.event  -> AI activity (thinking / replying / interrupted), routing decisions,
 *                     per-reply latency, failures, summary updates
 */
import type { Channel, ChatMessage, Persona, RoomEvent } from '../types/room';
import type { Incoming } from '../services/roomMessages';
import { AI_PROFILES, personaOfIdentity } from './personas';
import { createStore, type Store } from './store';

export interface TranscriptEntry {
  id: string;
  kind: 'human' | 'ai' | 'system';
  name: string;
  identity?: string;
  persona?: Persona;
  text: string;
  channel: Channel;
  at: number; // local ms
  mine?: boolean;
  interrupted?: boolean;
}

export type AiPhase = 'idle' | 'thinking' | 'replying' | 'interrupted';

export interface AiActivity {
  phase: AiPhase;
  at: number;
}

export interface ReplyResult {
  bot: Persona;
  outcome: string;
  llmMs?: number;
  firstAudioMs?: number;
  totalMs?: number;
}

export interface Decision {
  turnId: string;
  speaker: string;
  channel: Channel;
  text?: string;
  bots: Persona[];
  reason: string;
  at: number;
  replies: ReplyResult[];
}

/**
 * The Debug timeline. Every item is something that actually happened:
 * - event: a backend roxstar.event
 * - reply: the AI's reply text arrived in the room
 * - audio: LiveKit reported the AI's voice as active (first time for that reply)
 */
export type TimelineItem = { id: number; at: number } & (
  | { kind: 'event'; event: RoomEvent }
  | { kind: 'reply'; persona: Persona }
  | { kind: 'audio'; persona: Persona }
);

/** A person whose voice isn't reaching the room (their speech-to-text stream is failing). */
export interface SttTrouble {
  attempt: number;
  retryInS: number;
  error: string;
  at: number;
}

export interface FeedState {
  entries: TranscriptEntry[];
  activity: Record<Persona, AiActivity>;
  decisions: Decision[];
  log: TimelineItem[];
  lastHeardAt?: number; // last voice transcript: proof speech-to-text is working
  summaryUpdates: number;
  sttTrouble: Record<string, SttTrouble>; // by participant identity
}

const MAX_DECISIONS = 30;
const MAX_LOG = 120;
const LINK_WINDOW_MS = 20_000;

function without<T>(record: Record<string, T>, key: string | undefined): Record<string, T> {
  if (!key || !(key in record)) return record;
  const next = { ...record };
  delete next[key];
  return next;
}

let seq = 0;
const nextId = () => `${Date.now().toString(36)}-${(seq++).toString(36)}`;

export class RoomFeed {
  readonly store: Store<FeedState>;
  private awaitingAudio: Record<Persona, boolean> = { dost: false, sathi: false };

  constructor() {
    const idle = { phase: 'idle' as const, at: 0 };
    this.store = createStore<FeedState>({
      entries: [],
      activity: { dost: idle, sathi: idle },
      decisions: [],
      log: [],
      summaryUpdates: 0,
      sttTrouble: {},
    });
  }

  /** A data message from the room. `from` is the participant that sent it. */
  handle(incoming: Incoming, from?: { identity: string; name: string; human: boolean }): void {
    if (incoming.kind === 'chat') this.onChat(incoming.message, from);
    else this.onEvent(incoming.event);
  }

  /** LiveKit says this AI's voice is active. Logged once per reply. */
  noteAudioStarted(persona: Persona): void {
    if (!this.awaitingAudio[persona]) return;
    this.awaitingAudio[persona] = false;
    this.log({ kind: 'audio', persona });
  }

  private log(item: { kind: 'event'; event: RoomEvent } | { kind: 'reply' | 'audio'; persona: Persona }) {
    const entry = { id: seq++, at: Date.now(), ...item } as TimelineItem;
    this.store.update((s) => ({ ...s, log: [...s.log.slice(-(MAX_LOG - 1)), entry] }));
  }

  /** Our own typed message: the sender never receives its own data packet, so echo it. */
  addOwnMessage(name: string, identity: string, text: string): void {
    this.append({
      id: nextId(),
      kind: 'human',
      name,
      identity,
      text,
      channel: 'text',
      at: Date.now(),
      mine: true,
    });
  }

  private onChat(message: ChatMessage, from?: { identity: string; name: string; human: boolean }) {
    const now = Date.now();
    const persona = personaOfIdentity(message.identity) ?? personaOfIdentity(from?.identity);
    if (persona) {
      this.append({
        id: nextId(),
        kind: 'ai',
        name: AI_PROFILES[persona].name,
        identity: AI_PROFILES[persona].identity,
        persona,
        text: message.text,
        channel: 'voice',
        at: now,
      });
      // The reply text is posted just before its audio starts.
      this.setActivity(persona, 'replying', now);
      this.awaitingAudio[persona] = true;
      this.log({ kind: 'reply', persona });
      return;
    }
    if (message.sender === 'Room system') {
      this.append({
        id: nextId(),
        kind: 'system',
        name: 'Room',
        text: message.text,
        channel: 'text',
        at: now,
      });
      return;
    }
    // A human line: either a voice transcript relayed by the brain, or someone's typed message.
    const identity = message.identity ?? from?.identity;
    this.append({
      id: nextId(),
      kind: 'human',
      name: message.sender || identity || 'Someone',
      identity,
      text: message.text,
      channel: message.channel === 'voice' ? 'voice' : 'text',
      at: now,
    });
    if (message.channel === 'voice') {
      // A transcript is proof this person's voice is getting through again.
      this.store.update((s) => ({ ...s, lastHeardAt: now, sttTrouble: without(s.sttTrouble, identity) }));
    }
  }

  private onEvent(event: RoomEvent) {
    const now = Date.now();
    this.log({ kind: 'event', event });

    switch (event.event) {
      case 'routed': {
        const text = this.findRecentHumanLine(event.speaker, now)?.text;
        const decision: Decision = {
          turnId: event.turn_id,
          speaker: event.speaker,
          channel: event.channel,
          text,
          bots: event.bots,
          reason: event.reason,
          at: now,
          replies: [],
        };
        this.store.update((s) => ({
          ...s,
          decisions: [...s.decisions.slice(-(MAX_DECISIONS - 1)), decision],
        }));
        return;
      }
      case 'moderated': {
        const decision: Decision = {
          turnId: event.turn_id,
          speaker: event.speaker,
          channel: 'voice',
          bots: [event.bot],
          reason: 'moderated',
          at: now,
          replies: [],
        };
        this.store.update((s) => ({
          ...s,
          decisions: [...s.decisions.slice(-(MAX_DECISIONS - 1)), decision],
        }));
        return;
      }
      case 'thinking':
        this.setActivity(event.bot, 'thinking', now);
        return;
      case 'interrupted':
        if (event.bot) {
          this.setActivity(event.bot, 'interrupted', now);
          this.markLastReplyInterrupted(event.bot);
        }
        return;
      case 'turn_done': {
        const result: ReplyResult = {
          bot: event.bot,
          outcome: event.outcome,
          llmMs: event.llm_ms,
          firstAudioMs: event.first_audio_ms,
          totalMs: event.total_ms,
        };
        this.store.update((s) => {
          const activity = s.activity[event.bot];
          return {
            ...s,
            // Keep "interrupted" visible; everything else settles back to idle.
            activity:
              activity.phase === 'interrupted'
                ? s.activity
                : { ...s.activity, [event.bot]: { phase: 'idle', at: now } },
            decisions: s.decisions.map((d) =>
              d.turnId === event.turn_id ? { ...d, replies: [...d.replies, result] } : d,
            ),
          };
        });
        return;
      }
      case 'stt_failed':
        this.store.update((s) => ({
          ...s,
          sttTrouble: {
            ...s.sttTrouble,
            [event.speaker]: {
              attempt: event.attempt,
              retryInS: event.retry_in_s,
              error: event.error,
              at: now,
            },
          },
        }));
        return;
      case 'stt_recovered':
        this.store.update((s) => ({ ...s, sttTrouble: without(s.sttTrouble, event.speaker) }));
        return;
      case 'summary_updated':
        this.store.update((s) => ({ ...s, summaryUpdates: s.summaryUpdates + 1 }));
        return;
      default:
        return; // llm_failed, tts_failed, failure_armed: shown from the log
    }
  }

  private setActivity(persona: Persona, phase: AiPhase, at: number) {
    this.store.update((s) => ({ ...s, activity: { ...s.activity, [persona]: { phase, at } } }));
  }

  private append(entry: TranscriptEntry) {
    this.store.update((s) => ({ ...s, entries: [...s.entries, entry] }));
  }

  private findRecentHumanLine(identity: string, now: number): TranscriptEntry | undefined {
    const entries = this.store.get().entries;
    for (let i = entries.length - 1; i >= 0; i--) {
      const e = entries[i];
      if (now - e.at > LINK_WINDOW_MS) return undefined;
      if (e.kind === 'human' && e.identity === identity) return e;
    }
    return undefined;
  }

  private markLastReplyInterrupted(persona: Persona) {
    this.store.update((s) => {
      const index = s.entries.findLastIndex((e) => e.kind === 'ai' && e.persona === persona);
      if (index < 0 || s.entries[index].interrupted) return s;
      const entries = s.entries.slice();
      entries[index] = { ...entries[index], interrupted: true };
      return { ...s, entries };
    });
  }
}
