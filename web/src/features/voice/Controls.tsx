import { useLocalParticipant, useMediaDeviceSelect } from '@livekit/components-react';
import { Check, Mic, MicOff, PhoneOff, SlidersHorizontal, Volume2, VolumeX } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';
import { useSession } from '../../app/context';
import { useStore } from '../../lib/store';
import { SpeakingRing } from '../participants/SpeakingRing';

const ICON = { size: 18, strokeWidth: 1.75 } as const;

export function Controls({
  outputMuted,
  onToggleOutput,
}: {
  outputMuted: boolean;
  onToggleOutput: () => void;
}) {
  const { mic, setMicEnabled, leave, phase, feed } = useSession();
  const { localParticipant } = useLocalParticipant();
  // The server can't turn *your* voice into text (e.g. the speech provider is down).
  const sttTrouble = useStore(feed.store, (s) => s.sttTrouble[localParticipant.identity]);
  const connected = phase === 'connected' || phase === 'reconnecting';

  const micLabel =
    mic === 'on'
      ? 'Mute microphone'
      : mic === 'denied'
        ? 'Microphone blocked. Click to ask again'
        : mic === 'unavailable'
          ? 'No microphone found. Click to retry'
          : mic === 'pending'
            ? 'Starting microphone'
            : 'Unmute microphone';

  const micProblem =
    mic === 'denied'
      ? 'Mic blocked by your browser. You can still type.'
      : mic === 'unavailable'
        ? 'No microphone found. You can still type.'
        : null;
  const voiceProblem =
    !micProblem && sttTrouble && mic === 'on'
      ? `Your voice isn't reaching the AI (speech service down). Retrying every ${sttTrouble.retryInS} s.`
      : null;

  return (
    <div className="controls-area">
      {micProblem && (
        <p className="mic-hint" role="alert">
          <span>{micProblem}</span>
          <button type="button" className="mic-hint__action" onClick={() => void setMicEnabled(true)}>
            Try again
          </button>
        </p>
      )}
      {voiceProblem && (
        <p className="mic-hint" role="status">
          <span>{voiceProblem}</span>
        </p>
      )}
      {/* Mic in the centre, secondary controls balanced either side: the same shape on a
          desktop column and in a phone's thumb zone. */}
      <div className="controls" role="group" aria-label="Voice controls">
        <div className="controls__side controls__side--start">
          <button
            type="button"
            className="icon-btn"
            onClick={onToggleOutput}
            aria-pressed={outputMuted}
            aria-label={outputMuted ? 'Unmute room audio' : 'Mute room audio'}
            data-tip={outputMuted ? 'Room audio off' : 'Room audio on'}
          >
            {outputMuted ? (
              <VolumeX {...ICON} aria-hidden="true" />
            ) : (
              <Volume2 {...ICON} aria-hidden="true" />
            )}
          </button>
          <DeviceMenu />
        </div>

        <span className="mic-wrap">
          {/* Your real input level, as a faint ring: proof you're being heard. */}
          <SpeakingRing className="mic-level" participant={localParticipant} active={mic === 'on'}>
            <span />
          </SpeakingRing>
          <button
            type="button"
            className="mic-btn"
            data-state={mic}
            onClick={() => void setMicEnabled(mic !== 'on')}
            disabled={!connected || mic === 'pending'}
            aria-pressed={mic === 'on'}
            aria-label={micLabel}
            data-tip={micLabel}
          >
            {mic === 'pending' ? (
              <span className="spinner" aria-hidden="true" />
            ) : mic === 'on' ? (
              <Mic {...ICON} aria-hidden="true" />
            ) : (
              <MicOff {...ICON} aria-hidden="true" />
            )}
          </button>
        </span>

        <div className="controls__side controls__side--end">
          <button
            type="button"
            className="leave-btn"
            onClick={() => void leave()}
            aria-label="Leave room"
            data-tip="Leave room"
          >
            <PhoneOff {...ICON} aria-hidden="true" />
            <span className="leave-btn__text">Leave</span>
          </button>
        </div>
      </div>
    </div>
  );
}

const canPickOutput = typeof HTMLMediaElement !== 'undefined' && 'setSinkId' in HTMLMediaElement.prototype;

function DeviceMenu() {
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    const onPointer = (e: PointerEvent) => {
      if (!wrap.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false);
        trigger.current?.focus();
      }
    };
    document.addEventListener('pointerdown', onPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('pointerdown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div className="device-menu" ref={wrap}>
      <button
        ref={trigger}
        type="button"
        className="icon-btn"
        aria-expanded={open}
        aria-controls={menuId}
        aria-label="Audio devices"
        data-tip={open ? undefined : 'Audio devices'}
        onClick={() => setOpen((o) => !o)}
      >
        <SlidersHorizontal {...ICON} aria-hidden="true" />
      </button>
      {open && (
        <div id={menuId} className="device-menu__panel" role="dialog" aria-label="Audio devices">
          <DeviceList kind="audioinput" title="Microphone" />
          {canPickOutput && <DeviceList kind="audiooutput" title="Speaker" />}
        </div>
      )}
    </div>
  );
}

function DeviceList({ kind, title }: { kind: MediaDeviceKind; title: string }) {
  const { devices, activeDeviceId, setActiveMediaDevice } = useMediaDeviceSelect({ kind });
  const usable = devices.filter((d) => d.deviceId);
  return (
    <fieldset className="device-list">
      <legend className="device-list__title">{title}</legend>
      {usable.length === 0 && <p className="device-list__empty">No devices found</p>}
      {usable.map((device) => {
        const active =
          device.deviceId === activeDeviceId || (activeDeviceId === '' && device.deviceId === 'default');
        return (
          <button
            key={device.deviceId}
            type="button"
            aria-pressed={active}
            className="device-list__item"
            onClick={() => void setActiveMediaDevice(device.deviceId)}
          >
            <span className="device-list__check">{active && <Check size={14} strokeWidth={2} />}</span>
            <span className="device-list__label">{device.label || 'Unnamed device'}</span>
          </button>
        );
      })}
    </fieldset>
  );
}
