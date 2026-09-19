/**
 * One AI participant's visible state, resolved from real signals only:
 *
 *   room connection      -> reconnecting
 *   participant present? -> joining / not in the room
 *   LiveKit audio        -> speaking
 *   backend events       -> interrupted / thinking / replying
 *   brain present        -> listening
 */
import { useConnectionState } from '@livekit/components-react';
import { ConnectionState, type Participant, type RemoteParticipant } from 'livekit-client';
import { useEffect, useState } from 'react';
import { useSession } from '../app/context';
import { useStore } from '../lib/store';
import type { Persona } from '../types/room';
import { useExpiry } from './useNow';

export type AiState =
  | 'reconnecting'
  | 'joining'
  | 'absent'
  | 'speaking'
  | 'interrupted'
  | 'thinking'
  | 'replying'
  | 'listening'
  | 'idle';

export const AI_STATE_LABEL: Record<AiState, string> = {
  reconnecting: 'Reconnecting',
  joining: 'Joining',
  absent: 'Not in the room',
  speaking: 'Speaking',
  interrupted: 'Interrupted',
  thinking: 'Thinking',
  replying: 'Responding',
  listening: 'Listening',
  idle: 'Idle',
};

const JOIN_GRACE_MS = 25_000; // how long "joining" is believable before "not in the room"
const INTERRUPTED_HOLD_MS = 2_400; // keep the real "interrupted" event readable
const SPEAKING_HOLD_MS = 450; // bridge the tiny gaps between spoken sentences

export function useAiState(
  persona: Persona,
  participant: RemoteParticipant | undefined,
  brainPresent: boolean,
): AiState {
  const { feed, joinedAt } = useSession();
  const connection = useConnectionState();
  const activity = useStore(feed.store, (s) => s.activity[persona]);
  const speaking = useSpeakingWithHold(participant);

  const interruptedFresh = !useExpiry(
    activity.phase === 'interrupted' ? activity.at + INTERRUPTED_HOLD_MS : undefined,
  );
  const stillJoining = !useExpiry(joinedAt + JOIN_GRACE_MS);

  if (connection === ConnectionState.Reconnecting || connection === ConnectionState.SignalReconnecting) {
    return 'reconnecting';
  }
  if (!participant) return stillJoining ? 'joining' : 'absent';
  if (speaking) return 'speaking';
  if (activity.phase === 'interrupted' && interruptedFresh) return 'interrupted';
  if (activity.phase === 'thinking') return 'thinking';
  if (activity.phase === 'replying') return 'replying';
  return brainPresent ? 'listening' : 'idle';
}

function useSpeakingWithHold(participant: RemoteParticipant | undefined): boolean {
  const live = useParticipantSpeaking(participant);
  const [held, setHeld] = useState(false);
  useEffect(() => {
    if (live) {
      setHeld(true);
      return;
    }
    const timer = window.setTimeout(() => setHeld(false), SPEAKING_HOLD_MS);
    return () => window.clearTimeout(timer);
  }, [live]);
  return live || held;
}

/** LiveKit's own speaking detection, safe to call before a participant has joined. */
export function useParticipantSpeaking(participant: Participant | undefined): boolean {
  const [speaking, setSpeaking] = useState(false);
  useEffect(() => {
    if (!participant) {
      setSpeaking(false);
      return;
    }
    const update = () => setSpeaking(participant.isSpeaking);
    update();
    participant.on('isSpeakingChanged', update);
    return () => {
      participant.off('isSpeakingChanged', update);
    };
  }, [participant]);
  return speaking;
}
