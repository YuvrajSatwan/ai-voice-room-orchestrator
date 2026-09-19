import type { RemoteParticipant } from 'livekit-client';
import { memo } from 'react';
import { AI_STATE_LABEL, useAiState } from '../../hooks/useAiState';
import { AI_PROFILES } from '../../lib/personas';
import type { Persona } from '../../types/room';
import { AiGlyph } from './AiGlyph';

interface Props {
  persona: Persona;
  participant?: RemoteParticipant;
  brainPresent: boolean;
}

/**
 * One AI participant. The name carries the weight; the glyph is a small living presence
 * that shows state by itself, and the state text reinforces it.
 */
export const AiPresence = memo(function AiPresence({ persona, participant, brainPresent }: Props) {
  const profile = AI_PROFILES[persona];
  const state = useAiState(persona, participant, brainPresent);
  const label = AI_STATE_LABEL[state];

  return (
    <article
      className="ai"
      data-state={state}
      aria-label={`${profile.name}, AI participant, ${profile.gender.toLowerCase()} voice. ${label}.`}
    >
      <AiGlyph persona={persona} state={state} participant={participant} />
      <div className="ai__text">
        <h3 className="ai__name">{profile.name}</h3>
        <p className="ai__meta">AI · {profile.gender}</p>
        <p className="ai__state">
          <span key={state} className="ai__state-label">
            {label}
          </span>
        </p>
      </div>
    </article>
  );
});
