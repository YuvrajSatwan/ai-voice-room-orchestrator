import { useLocalParticipant } from '@livekit/components-react';
import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useSession } from '../../app/context';
import { useTick } from '../../hooks/useNow';
import type { RoomPeople } from '../../hooks/useRoomPeople';
import { ago, clockTime, median, seconds } from '../../lib/format';
import { AI_ORDER, AI_PROFILES } from '../../lib/personas';
import type { TimelineItem } from '../../lib/roomFeed';
import { useStore } from '../../lib/store';
import { encodeChat } from '../../services/roomMessages';
import type { RoomEvent } from '../../types/room';
import { describe } from './timeline';

const PHASE_LABEL = {
  connecting: 'Connecting',
  connected: 'Connected',
  reconnecting: 'Reconnecting',
  lost: 'Disconnected',
  failed: 'Failed',
  left: 'Left',
} as const;

function Row({ label, value, tone }: { label: string; value: string; tone?: 'ok' | 'warn' }) {
  return (
    <div className="kv" data-tone={tone}>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

/** Newest backend event matching `test`, from the real timeline. */
function lastEvent(log: TimelineItem[], test: (e: RoomEvent) => boolean): RoomEvent | undefined {
  for (let i = log.length - 1; i >= 0; i--) {
    const item = log[i];
    if (item.kind === 'event' && test(item.event)) return item.event;
  }
  return undefined;
}

export function DebugView({ people, name }: { people: RoomPeople; name: string }) {
  const { room, feed, phase } = useSession();
  const { localParticipant } = useLocalParticipant();
  const log = useStore(feed.store, (s) => s.log);
  const lastHeardAt = useStore(feed.store, (s) => s.lastHeardAt);
  const sttTrouble = useStore(feed.store, (s) => s.sttTrouble);
  const failing = Object.entries(sttTrouble);
  const now = useTick(5_000);
  const [sent, setSent] = useState<string>();

  const stats = useMemo(() => {
    const llm = lastEvent(
      log,
      (e) => e.event === 'llm_failed' || (e.event === 'turn_done' && e.llm_ms !== undefined),
    );
    const tts = lastEvent(
      log,
      (e) => e.event === 'tts_failed' || (e.event === 'turn_done' && e.first_audio_ms !== undefined),
    );
    const spoken = log.flatMap((i) =>
      i.kind === 'event' && i.event.event === 'turn_done' && i.event.outcome === 'spoken' ? [i.event] : [],
    );
    const firstAudio = spoken.flatMap((e) => (e.first_audio_ms !== undefined ? [e.first_audio_ms] : []));
    const armed = lastEvent(log, (e) => e.event === 'failure_armed');
    return { llm, tts, last: spoken.at(-1), firstAudio, armed };
  }, [log]);

  const armFailure = async (stage: 'llm' | 'tts') => {
    await room.localParticipant.publishData(encodeChat(name, `/fail ${stage}`), { reliable: true });
    setSent(stage);
  };

  return (
    <div className="debug">
      <section className="intel__section">
        <h2 className="intel__heading">Timeline</h2>
        <Timeline log={log} />
      </section>

      <section className="intel__section">
        <h2 className="intel__heading">Response time</h2>
        <dl className="kvs">
          <Row
            label="Last reply"
            value={
              stats.last
                ? `${AI_PROFILES[stats.last.bot].name} · voice in ${seconds(stats.last.first_audio_ms)} · model ${seconds(stats.last.llm_ms)}`
                : '—'
            }
          />
          <Row
            label="Session median"
            value={
              stats.firstAudio.length
                ? `${seconds(median(stats.firstAudio))} to voice · ${stats.firstAudio.length} ${stats.firstAudio.length === 1 ? 'reply' : 'replies'}`
                : '—'
            }
          />
        </dl>
        <p className="intel__note">
          Server-measured, from the moment a turn reaches the room brain to the bot's first audio.
        </p>
      </section>

      <section className="intel__section">
        <h2 className="intel__heading">Pipeline</h2>
        <dl className="kvs">
          <Row
            label="Speech-to-text"
            value={
              failing.length
                ? `Failing for ${failing.map(([who]) => who).join(', ')} · ${failing[0][1].error} · retry every ${failing[0][1].retryInS} s`
                : lastHeardAt
                  ? `Last transcript ${ago(lastHeardAt, now)}`
                  : 'No speech heard yet'
            }
            tone={failing.length ? 'warn' : lastHeardAt ? 'ok' : undefined}
          />
          <Row
            label="Language model"
            value={
              !stats.llm
                ? 'No replies yet'
                : stats.llm.event === 'llm_failed'
                  ? `Failed · ${stats.llm.error}`
                  : stats.llm.event === 'turn_done'
                    ? `OK · ${seconds(stats.llm.llm_ms)}`
                    : '—'
            }
            tone={!stats.llm ? undefined : stats.llm.event === 'llm_failed' ? 'warn' : 'ok'}
          />
          <Row
            label="Voice"
            value={
              !stats.tts
                ? 'No replies yet'
                : stats.tts.event === 'tts_failed'
                  ? `Failed · ${stats.tts.error}`
                  : 'OK'
            }
            tone={!stats.tts ? undefined : stats.tts.event === 'tts_failed' ? 'warn' : 'ok'}
          />
          <Row label="LiveKit" value={PHASE_LABEL[phase]} tone={phase === 'connected' ? 'ok' : 'warn'} />
          {room.serverInfo?.region && <Row label="Region" value={room.serverInfo.region} />}
        </dl>
      </section>

      <section className="intel__section">
        <h2 className="intel__heading">Participants</h2>
        <ul className="people">
          <li>
            <span>{localParticipant.identity}</span>
            <span>human · you</span>
          </li>
          {people.humans.map((p) => (
            <li key={p.identity}>
              <span>{p.identity}</span>
              <span>human</span>
            </li>
          ))}
          {AI_ORDER.map((b) => {
            const bot = people.bots[b];
            return (
              bot && (
                <li key={b}>
                  <span>{bot.identity}</span>
                  <span>AI · {AI_PROFILES[b].gender.toLowerCase()} voice</span>
                </li>
              )
            );
          })}
          {people.brainPresent && (
            <li>
              <span>room brain</span>
              <span>listens · routes · never speaks</span>
            </li>
          )}
        </ul>
      </section>

      <section className="intel__section">
        <h2 className="intel__heading">Failure demo</h2>
        <p className="intel__note">
          Fails the next call through the real error handling. Needs the worker started with
          ROXSTAR_DEMO_CONTROLS=true.
        </p>
        <div className="debug__actions">
          <button type="button" className="btn btn--outline" onClick={() => void armFailure('llm')}>
            Fail next model call
          </button>
          <button type="button" className="btn btn--outline" onClick={() => void armFailure('tts')}>
            Fail next voice reply
          </button>
        </div>
        {sent && (
          <p className="intel__note" role="status">
            {stats.armed?.event === 'failure_armed' && stats.armed.stage === sent
              ? `Armed. The next ${sent === 'llm' ? 'model call' : 'voice reply'} will fail.`
              : 'Sent. If nothing is armed, demo controls are off on the worker.'}
          </p>
        )}
      </section>
    </div>
  );
}

function Timeline({ log }: { log: TimelineItem[] }) {
  const scroller = useRef<HTMLOListElement>(null);
  const lines = useMemo(
    () =>
      log.slice(-60).flatMap((item) => {
        const line = describe(item);
        return line ? [{ item, line }] : [];
      }),
    [log],
  );

  // Newest at the bottom, like the room itself; keep it scrolled to the latest.
  useLayoutEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines.length]);

  if (lines.length === 0) {
    return <p className="intel__note">Nothing yet. Speak or type in the room and each step lands here.</p>;
  }
  return (
    <ol ref={scroller} className="timeline" aria-label="Orchestration timeline">
      {lines.map(({ item, line }) => (
        <li key={item.id} className="timeline__item" data-tone={line.tone}>
          <time className="timeline__time">{clockTime(item.at)}</time>
          <span className="timeline__dot" aria-hidden="true" />
          <span className="timeline__text">
            <span className="timeline__title">{line.title}</span>
            {line.detail && <span className="timeline__detail">{line.detail}</span>}
          </span>
        </li>
      ))}
    </ol>
  );
}
