/** Who is in the room, split into the three roles the backend uses. */
import { useRemoteParticipants } from '@livekit/components-react';
import { type RemoteParticipant, RoomEvent } from 'livekit-client';
import { useMemo } from 'react';
import { isBrain, isHuman, personaOf } from '../lib/personas';
import type { Persona } from '../types/room';

export interface RoomPeople {
  bots: Partial<Record<Persona, RemoteParticipant>>;
  humans: RemoteParticipant[];
  brainPresent: boolean;
}

// Only the events that change who is who. Not active speakers, not audio levels.
const MEMBERSHIP_EVENTS = [
  RoomEvent.ParticipantConnected,
  RoomEvent.ParticipantDisconnected,
  RoomEvent.ParticipantAttributesChanged, // the brain sets its role just after joining
  RoomEvent.ParticipantNameChanged,
  RoomEvent.ConnectionStateChanged,
];

export function useRoomPeople(): RoomPeople {
  const remotes = useRemoteParticipants({ updateOnlyOn: MEMBERSHIP_EVENTS });
  return useMemo(() => {
    const bots: Partial<Record<Persona, RemoteParticipant>> = {};
    const humans: RemoteParticipant[] = [];
    let brainPresent = false;
    for (const p of remotes) {
      if (isBrain(p)) brainPresent = true;
      else if (isHuman(p)) humans.push(p);
      else {
        const persona = personaOf(p);
        if (persona) bots[persona] = p;
      }
    }
    return { bots, humans, brainPresent };
  }, [remotes]);
}
