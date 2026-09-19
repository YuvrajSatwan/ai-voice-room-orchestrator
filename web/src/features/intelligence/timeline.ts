/** Turns real timeline items into short, readable lines for the Debug timeline. */
import { seconds } from '../../lib/format';
import { AI_PROFILES } from '../../lib/personas';
import type { TimelineItem } from '../../lib/roomFeed';
import { outcomeLabel, reasonLabel } from './labels';

export type TimelineTone = 'neutral' | 'live' | 'warn' | 'quiet';

export interface TimelineLine {
  title: string;
  detail?: string;
  tone: TimelineTone;
}

const name = (p: 'dost' | 'sathi') => AI_PROFILES[p].name;

export function describe(item: TimelineItem): TimelineLine | null {
  if (item.kind === 'reply')
    return { title: 'Response generated', detail: name(item.persona), tone: 'neutral' };
  if (item.kind === 'audio') return { title: `${name(item.persona)} audio started`, tone: 'live' };

  const e = item.event;
  switch (e.event) {
    case 'routed':
      return {
        title: `${e.speaker} ${e.channel === 'voice' ? 'spoke' : 'typed'}`,
        detail: e.bots.length
          ? `→ ${e.bots.map(name).join(' then ')} · ${reasonLabel(e.reason)}`
          : `no reply · ${reasonLabel(e.reason)}`,
        tone: e.bots.length ? 'neutral' : 'quiet',
      };
    case 'thinking':
      return { title: `${name(e.bot)} thinking`, tone: 'neutral' };
    case 'turn_done':
      return {
        title: e.outcome === 'spoken' ? 'Response complete' : outcomeLabel(e.outcome),
        detail: [
          name(e.bot),
          e.first_audio_ms !== undefined ? `voice in ${seconds(e.first_audio_ms)}` : undefined,
          e.llm_ms !== undefined ? `model ${seconds(e.llm_ms)}` : undefined,
        ]
          .filter(Boolean)
          .join(' · '),
        tone: e.outcome === 'spoken' ? 'live' : 'warn',
      };
    case 'interrupted':
      return { title: `${e.bot ? name(e.bot) : 'AI'} interrupted`, detail: `by ${e.by}`, tone: 'warn' };
    case 'llm_failed':
      return { title: 'Model call failed', detail: `${name(e.bot)} · ${e.error}`, tone: 'warn' };
    case 'tts_failed':
      return {
        title: 'Voice failed',
        detail: `${name(e.bot)} · reply sent as text · ${e.error}`,
        tone: 'warn',
      };
    case 'moderated':
      return {
        title: 'Message moderated',
        detail: `${e.speaker} · ${name(e.bot)} replied calmly`,
        tone: 'warn',
      };
    case 'summary_updated':
      return {
        title: 'Session summary updated',
        detail: `${e.turns_merged} older turns merged`,
        tone: 'quiet',
      };
    case 'stt_failed':
      return {
        title: 'Speech-to-text failed',
        detail: `${e.speaker} · ${e.error} · attempt ${e.attempt}, retry in ${e.retry_in_s} s`,
        tone: 'warn',
      };
    case 'stt_recovered':
      return { title: 'Speech-to-text recovered', detail: e.speaker, tone: 'live' };
    case 'failure_armed':
      return {
        title: 'Failure armed (demo)',
        detail: `next ${e.stage.toUpperCase()} call will fail`,
        tone: 'warn',
      };
    default:
      return null;
  }
}
