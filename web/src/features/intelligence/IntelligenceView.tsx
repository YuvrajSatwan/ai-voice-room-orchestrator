/**
 * The system inspector: what the room brain is doing, in plain words. Every value comes
 * from a backend event or LiveKit state; rows without real data are simply not shown.
 */
import { useSession } from '../../app/context';
import type { RoomPeople } from '../../hooks/useRoomPeople';
import { seconds } from '../../lib/format';
import { AI_ORDER, AI_PROFILES } from '../../lib/personas';
import type { Decision } from '../../lib/roomFeed';
import { useStore } from '../../lib/store';
import { excerpt, outcomeLabel, reasonLabel } from './labels';

const botNames = (d: Decision) => d.bots.map((b) => AI_PROFILES[b].name).join(' then ');

function routeText(d: Decision): string {
  return d.bots.length ? `${botNames(d)} · ${reasonLabel(d.reason)}` : `No reply · ${reasonLabel(d.reason)}`;
}

export function IntelligenceView({ people }: { people: RoomPeople }) {
  const { feed } = useSession();
  const decisions = useStore(feed.store, (s) => s.decisions);
  const activity = useStore(feed.store, (s) => s.activity);
  const summaryUpdates = useStore(feed.store, (s) => s.summaryUpdates);
  const latest = decisions.at(-1);

  const thinking = AI_ORDER.find((p) => activity[p].phase === 'thinking');
  const responding = AI_ORDER.find((p) => activity[p].phase === 'replying');
  const now = thinking
    ? `${AI_PROFILES[thinking].name} is thinking`
    : responding
      ? `${AI_PROFILES[responding].name} is responding`
      : people.brainPresent
        ? 'Listening to the room'
        : 'Waiting for the room brain';
  const busy = Boolean(thinking || responding);

  const lastReply = [...decisions]
    .reverse()
    .flatMap((d) => d.replies)
    .find((r) => r.firstAudioMs !== undefined);
  const humans = people.humans.length + 1;

  return (
    <div className="intel">
      <dl className="inspector">
        <div className="inspector__row" data-live={busy || undefined}>
          <dt>Now</dt>
          <dd>
            {busy && <span className="inspector__pulse" aria-hidden="true" />}
            {now}
          </dd>
        </div>
        {latest && (
          <div className="inspector__row">
            <dt>Speaker</dt>
            <dd>
              {latest.speaker}
              <span className="inspector__sub">{latest.channel === 'voice' ? 'spoken' : 'typed'}</span>
            </dd>
          </div>
        )}
        {people.brainPresent && (
          <div className="inspector__row">
            <dt>Context</dt>
            <dd>
              Shared memory
              <span className="inspector__sub">
                {humans} {humans === 1 ? 'person' : 'people'} on separate streams
                {summaryUpdates > 0 && ` · summary updated ${summaryUpdates}×`}
              </span>
            </dd>
          </div>
        )}
        {latest && (
          <div className="inspector__row">
            <dt>Routing</dt>
            <dd>{routeText(latest)}</dd>
          </div>
        )}
        {lastReply && (
          <div className="inspector__row">
            <dt>Latency</dt>
            <dd>
              {seconds(lastReply.firstAudioMs)} to voice
              {lastReply.llmMs !== undefined && (
                <span className="inspector__sub">model {seconds(lastReply.llmMs)}</span>
              )}
            </dd>
          </div>
        )}
      </dl>

      {!latest && (
        <p className="intel__note">
          Speak or type in the room. Who heard it, where it was routed, and how fast the answer came will
          appear here.
        </p>
      )}

      {decisions.length > 0 && (
        <section className="intel__section" aria-labelledby="intel-recent">
          <h2 id="intel-recent" className="intel__heading">
            Recent decisions
          </h2>
          <ol className="decisions">
            {[...decisions]
              .reverse()
              .slice(0, 8)
              .map((d) => (
                <li key={d.turnId} className="decision">
                  <p className="decision__who">
                    {d.speaker}
                    {d.text && <span className="decision__quote">“{excerpt(d.text, 56)}”</span>}
                  </p>
                  <p className="decision__route" data-silent={d.bots.length === 0 || undefined}>
                    {d.bots.length ? '→ ' : ''}
                    {routeText(d)}
                  </p>
                  {d.replies.map((r) => (
                    <p key={r.bot} className="decision__reply" data-ok={r.outcome === 'spoken' || undefined}>
                      {AI_PROFILES[r.bot].name}: {outcomeLabel(r.outcome).toLowerCase()}
                      {r.firstAudioMs !== undefined && ` · ${seconds(r.firstAudioMs)} to voice`}
                    </p>
                  ))}
                </li>
              ))}
          </ol>
        </section>
      )}
    </div>
  );
}
