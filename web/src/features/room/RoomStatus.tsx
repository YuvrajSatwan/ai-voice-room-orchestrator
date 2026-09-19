/**
 * One quiet line that answers "what's happening right now?". The only component that
 * listens to active-speaker changes; everything it says comes from LiveKit or backend events.
 */
import { useSpeakingParticipants } from '@livekit/components-react';
import { useSession } from '../../app/context';
import { AI_ORDER, AI_PROFILES, displayName, isBrain } from '../../lib/personas';
import { useStore } from '../../lib/store';

export function RoomStatus({ brainPresent, botsPresent }: { brainPresent: boolean; botsPresent: boolean }) {
  const { feed, phase } = useSession();
  const speakers = useSpeakingParticipants();
  const activity = useStore(feed.store, (s) => s.activity);

  const speaker = speakers.find((p) => !isBrain(p));
  const thinking = AI_ORDER.find((p) => activity[p].phase === 'thinking');
  const responding = AI_ORDER.find((p) => activity[p].phase === 'replying');

  let tone: 'live' | 'quiet' | 'warn' = 'quiet';
  let text: string;
  if (phase === 'connecting') text = 'Connecting…';
  else if (phase === 'reconnecting') {
    tone = 'warn';
    text = 'Reconnecting…';
  } else if (speaker) {
    tone = 'live';
    text = speaker.isLocal ? "You're speaking" : `${displayName(speaker)} is speaking`;
  } else if (thinking) text = `${AI_PROFILES[thinking].name} is thinking`;
  else if (responding) {
    tone = 'live';
    text = `${AI_PROFILES[responding].name} is responding`;
  } else if (!botsPresent) text = 'Waiting for Dost and Sathi';
  else if (brainPresent) text = 'Listening to the room';
  else text = 'Getting the room ready';

  return (
    <p className="status" data-tone={tone} role="status">
      <span className="status__dot" aria-hidden="true" />
      <span key={text} className="status__text">
        {text}
      </span>
    </p>
  );
}
