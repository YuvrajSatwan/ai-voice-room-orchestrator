import { ConnectionQuality, type Participant, ParticipantEvent } from 'livekit-client';
import { MicOff, WifiLow } from 'lucide-react';
import { memo, useEffect, useState } from 'react';
import { useParticipantSpeaking } from '../../hooks/useAiState';
import { displayName, initials } from '../../lib/personas';
import { SpeakingRing } from './SpeakingRing';

const MIC_EVENTS = [
  ParticipantEvent.TrackMuted,
  ParticipantEvent.TrackUnmuted,
  ParticipantEvent.TrackPublished,
  ParticipantEvent.TrackUnpublished,
  ParticipantEvent.LocalTrackPublished,
  ParticipantEvent.LocalTrackUnpublished,
] as const;

function useMicMuted(participant: Participant): boolean {
  const [muted, setMuted] = useState(() => !participant.isMicrophoneEnabled);
  useEffect(() => {
    const update = () => setMuted(!participant.isMicrophoneEnabled);
    MIC_EVENTS.forEach((e) => participant.on(e, update));
    update();
    return () => MIC_EVENTS.forEach((e) => participant.off(e, update));
  }, [participant]);
  return muted;
}

/** LiveKit's own per-participant network quality. Only a poor or lost link is worth showing. */
function usePoorConnection(participant: Participant): boolean {
  const [poor, setPoor] = useState(false);
  useEffect(() => {
    const update = () =>
      setPoor(
        participant.connectionQuality === ConnectionQuality.Poor ||
          participant.connectionQuality === ConnectionQuality.Lost,
      );
    participant.on(ParticipantEvent.ConnectionQualityChanged, update);
    update();
    return () => {
      participant.off(ParticipantEvent.ConnectionQualityChanged, update);
    };
  }, [participant]);
  return poor;
}

export const HumanPresence = memo(function HumanPresence({
  participant,
  isYou,
}: {
  participant: Participant;
  isYou: boolean;
}) {
  const name = displayName(participant);
  const speaking = useParticipantSpeaking(participant);
  const muted = useMicMuted(participant);
  const poorNetwork = usePoorConnection(participant);

  const described = [
    name,
    isYou ? 'you' : null,
    speaking ? 'speaking' : null,
    muted ? 'microphone off' : null,
    poorNetwork ? 'weak connection' : null,
  ]
    .filter(Boolean)
    .join(', ');

  return (
    <li
      className="human"
      data-speaking={speaking || undefined}
      data-muted={muted || undefined}
      aria-label={described}
      title={described}
    >
      <SpeakingRing className="human__figure" participant={participant} active={speaking}>
        <span className="human__halo" />
        <span className="human__disc">{initials(name)}</span>
      </SpeakingRing>
      <span className="human__name">
        {name}
        {isYou && <span className="human__you"> · you</span>}
      </span>
      <span className="human__icons" aria-hidden="true">
        {poorNetwork && <WifiLow className="human__net" size={14} strokeWidth={1.75} />}
        {muted && <MicOff className="human__muted" size={14} strokeWidth={1.75} />}
      </span>
    </li>
  );
});
