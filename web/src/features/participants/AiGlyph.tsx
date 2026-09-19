/**
 * The AI presence mark: five capsules in a hairline ring, a small "living audio presence"
 * instead of an avatar.
 *
 * Each AI has its own silhouette (Kabir: a steady arch; Saraah: a livelier, uneven line), so
 * they're recognisable at rest. State comes from `data-state` (CSS does idle, listening,
 * thinking, interrupted, joining). While speaking, bar heights follow the participant's real
 * audio level: computed in requestAnimationFrame and written to CSS variables, never React state.
 */
import type { Participant } from 'livekit-client';
import { type CSSProperties, useEffect, useRef } from 'react';
import type { AiState } from '../../hooks/useAiState';
import type { Persona } from '../../types/room';

const BARS = 5;

/** Resting heights (0..1) and how strongly each bar answers the voice. */
export const SILHOUETTE: Record<Persona, { rest: number[]; gain: number[] }> = {
  dost: { rest: [0.2, 0.3, 0.38, 0.3, 0.2], gain: [0.55, 0.85, 1, 0.85, 0.55] },
  sathi: { rest: [0.3, 0.4, 0.24, 0.34, 0.2], gain: [0.7, 1, 0.6, 0.9, 0.5] },
};

interface Props {
  persona: Persona;
  state: AiState;
  participant?: Participant;
  size?: 'md' | 'sm' | 'xs';
}

export function AiGlyph({ persona, state, participant, size = 'md' }: Props) {
  const ref = useRef<HTMLSpanElement>(null);
  const { rest, gain } = SILHOUETTE[persona];
  const speaking = state === 'speaking' && participant !== undefined;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const bars = Array.from(el.querySelectorAll<HTMLElement>('.glyph__bar'));
    if (!speaking || !participant) {
      bars.forEach((bar) => bar.style.removeProperty('--live'));
      return;
    }
    let frame = 0;
    const smooth = rest.slice();
    const loop = (t: number) => {
      const level = Math.min(1, participant.audioLevel * 2.6);
      for (let i = 0; i < BARS; i++) {
        // Voice drives height; a slow per-bar phase keeps the motion organic, not mechanical.
        const sway = 0.78 + 0.22 * Math.sin(t / 170 + i * 1.7);
        const target = Math.min(1, rest[i] * 1.15 + level * gain[i] * sway);
        smooth[i] += (target - smooth[i]) * 0.28;
        bars[i].style.setProperty('--live', smooth[i].toFixed(3));
      }
      frame = requestAnimationFrame(loop);
    };
    frame = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(frame);
  }, [speaking, participant, rest, gain]);

  return (
    <span ref={ref} className={`glyph glyph--${size}`} data-state={state} aria-hidden="true">
      <span className="glyph__ring" />
      <span className="glyph__bars">
        {rest.map((h, i) => (
          <span
            key={i}
            className="glyph__bar"
            style={{ '--rest': h, '--gain': gain[i], '--i': i } as CSSProperties}
          />
        ))}
      </span>
    </span>
  );
}
