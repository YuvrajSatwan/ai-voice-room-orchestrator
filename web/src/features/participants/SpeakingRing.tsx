/**
 * Drives the `--level` CSS variable from a participant's real audio level.
 * Runs in requestAnimationFrame and writes straight to the DOM, so audio activity never
 * re-renders React. Only runs while the participant is actually speaking.
 */
import type { Participant } from 'livekit-client';
import { type ReactNode, useEffect, useRef } from 'react';

interface Props {
  participant?: Participant;
  active: boolean;
  className: string;
  children: ReactNode;
}

export function SpeakingRing({ participant, active, className, children }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (!active || !participant) {
      el.style.setProperty('--level', '0');
      return;
    }
    let frame = 0;
    let smooth = 0;
    const loop = () => {
      const target = Math.min(1, participant.audioLevel * 2.4);
      smooth += (target - smooth) * 0.2; // ease toward the level: lively, never jittery
      el.style.setProperty('--level', smooth.toFixed(3));
      frame = requestAnimationFrame(loop);
    };
    frame = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(frame);
  }, [active, participant]);

  return (
    <div ref={ref} className={className} aria-hidden="true">
      {children}
    </div>
  );
}
