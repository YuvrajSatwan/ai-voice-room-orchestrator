/** Optional pre-join microphone check: a real level meter from getUserMedia, nothing faked. */
import { Mic, MicOff } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

type State = 'idle' | 'starting' | 'live' | 'denied' | 'unavailable';

export function MicCheck() {
  const [state, setState] = useState<State>('idle');
  const bar = useRef<HTMLSpanElement>(null);
  const cleanup = useRef<() => void>(undefined);

  useEffect(() => () => cleanup.current?.(), []);

  const start = async () => {
    setState('starting');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const ctx = new AudioContext();
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      ctx.createMediaStreamSource(stream).connect(analyser);
      const data = new Uint8Array(analyser.fftSize);
      let frame = 0;
      let smooth = 0;
      const loop = () => {
        analyser.getByteTimeDomainData(data);
        let peak = 0;
        for (const v of data) peak = Math.max(peak, Math.abs(v - 128));
        smooth += (Math.min(1, (peak / 128) * 2.2) - smooth) * 0.25;
        bar.current?.style.setProperty('--level', smooth.toFixed(3));
        frame = requestAnimationFrame(loop);
      };
      loop();
      cleanup.current = () => {
        cancelAnimationFrame(frame);
        stream.getTracks().forEach((t) => t.stop());
        void ctx.close();
      };
      setState('live');
    } catch (error) {
      const name = error instanceof Error ? error.name : '';
      setState(name === 'NotAllowedError' ? 'denied' : 'unavailable');
    }
  };

  if (state === 'live') {
    return (
      <div className="mic-check" data-state="live">
        <Mic size={16} strokeWidth={1.75} aria-hidden="true" />
        <span className="mic-check__meter" aria-hidden="true">
          <span ref={bar} className="mic-check__level" />
        </span>
        <span className="mic-check__text">Say something</span>
      </div>
    );
  }
  if (state === 'denied' || state === 'unavailable') {
    return (
      <div className="mic-check" data-state="blocked" role="alert">
        <MicOff size={16} strokeWidth={1.75} aria-hidden="true" />
        <span className="mic-check__text">
          {state === 'denied'
            ? 'Microphone blocked. Allow it in the address bar. You can still join and type.'
            : 'No microphone found. You can still join and type.'}
        </span>
      </div>
    );
  }
  return (
    <button
      type="button"
      className="mic-check mic-check--button"
      onClick={start}
      disabled={state === 'starting'}
    >
      {state === 'starting' ? (
        <span className="spinner" aria-hidden="true" />
      ) : (
        <Mic size={16} strokeWidth={1.75} aria-hidden="true" />
      )}
      <span className="mic-check__text">Check your microphone</span>
    </button>
  );
}
