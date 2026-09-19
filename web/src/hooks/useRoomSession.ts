/**
 * Owns the LiveKit connection for one visit to a room: connect, microphone, reconnects,
 * browser autoplay rules, and routing every data message into the RoomFeed.
 */
import { ConnectionState, DisconnectReason, type Participant, Room, RoomEvent } from 'livekit-client';
import { useCallback, useEffect, useState } from 'react';
import { isHuman, personaOf } from '../lib/personas';
import { RoomFeed } from '../lib/roomFeed';
import { decode } from '../services/roomMessages';
import type { Session } from '../types/room';

export type SessionPhase = 'connecting' | 'connected' | 'reconnecting' | 'lost' | 'failed' | 'left';
export type MicState = 'pending' | 'on' | 'off' | 'denied' | 'unavailable';

export interface RoomSession {
  room: Room;
  feed: RoomFeed;
  phase: SessionPhase;
  mic: MicState;
  reconnectedAt?: number;
  joinedAt: number;
  audioBlocked: boolean;
  setMicEnabled(enabled: boolean): Promise<void>;
  startAudio(): Promise<void>;
  leave(): Promise<void>;
}

function micErrorState(error: unknown): MicState {
  const name = error instanceof Error ? error.name : '';
  return name === 'NotAllowedError' || name === 'SecurityError' ? 'denied' : 'unavailable';
}

export function useRoomSession(session: Session): RoomSession {
  const [room] = useState(
    () =>
      new Room({
        adaptiveStream: true,
        dynacast: true,
        audioCaptureDefaults: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      }),
  );
  const [feed] = useState(() => new RoomFeed());
  const [phase, setPhase] = useState<SessionPhase>('connecting');
  const [mic, setMic] = useState<MicState>('pending');
  const [reconnectedAt, setReconnectedAt] = useState<number>();
  const [audioBlocked, setAudioBlocked] = useState(false);
  const [joinedAt] = useState(() => Date.now());

  useEffect(() => {
    let active = true;
    // Dev only: lets you exercise real LiveKit edge cases from the console,
    // e.g. __roxstarRoom.simulateScenario('signal-reconnect').
    if (import.meta.env.DEV) Object.assign(window, { __roxstarRoom: room });

    const onData = (payload: Uint8Array, participant?: Participant) => {
      const incoming = decode(payload);
      if (!incoming) return;
      feed.handle(
        incoming,
        participant && {
          identity: participant.identity,
          name: participant.name || participant.identity,
          human: isHuman(participant),
        },
      );
    };
    const onState = (state: ConnectionState) => {
      if (state === ConnectionState.Reconnecting || state === ConnectionState.SignalReconnecting) {
        setPhase('reconnecting');
      } else if (state === ConnectionState.Connected) {
        setPhase('connected');
      }
    };
    const onReconnected = () => setReconnectedAt(Date.now());
    const onDisconnected = (reason?: DisconnectReason) => {
      setPhase(reason === DisconnectReason.CLIENT_INITIATED ? 'left' : 'lost');
    };
    const onAudio = () => setAudioBlocked(!room.canPlaybackAudio);
    const onMicChange = () => setMic(room.localParticipant.isMicrophoneEnabled ? 'on' : 'off');
    const onSpeakers = (speakers: Participant[]) => {
      for (const p of speakers) {
        const persona = personaOf(p);
        if (persona) feed.noteAudioStarted(persona);
      }
    };

    room
      .on(RoomEvent.DataReceived, onData)
      .on(RoomEvent.ConnectionStateChanged, onState)
      .on(RoomEvent.Reconnected, onReconnected)
      .on(RoomEvent.Disconnected, onDisconnected)
      .on(RoomEvent.AudioPlaybackStatusChanged, onAudio)
      .on(RoomEvent.TrackMuted, onMicChange)
      .on(RoomEvent.TrackUnmuted, onMicChange)
      .on(RoomEvent.ActiveSpeakersChanged, onSpeakers);

    room
      .connect(session.url, session.token)
      .then(async () => {
        if (!active) return;
        setPhase('connected');
        setAudioBlocked(!room.canPlaybackAudio);
        try {
          await room.localParticipant.setMicrophoneEnabled(true);
          if (active) setMic('on');
        } catch (error) {
          if (active) setMic(micErrorState(error));
        }
      })
      .catch(() => active && setPhase('failed'));

    return () => {
      active = false;
      room.removeAllListeners();
      void room.disconnect();
    };
  }, [room, feed, session.url, session.token]);

  const setMicEnabled = useCallback(
    async (enabled: boolean) => {
      setMic('pending');
      try {
        await room.localParticipant.setMicrophoneEnabled(enabled);
        setMic(enabled ? 'on' : 'off');
      } catch (error) {
        setMic(micErrorState(error));
      }
    },
    [room],
  );

  const startAudio = useCallback(async () => {
    await room.startAudio();
    setAudioBlocked(!room.canPlaybackAudio);
  }, [room]);

  const leave = useCallback(async () => {
    await room.disconnect();
    setPhase('left');
  }, [room]);

  return {
    room,
    feed,
    phase,
    mic,
    reconnectedAt,
    joinedAt,
    audioBlocked,
    setMicEnabled,
    startAudio,
    leave,
  };
}
