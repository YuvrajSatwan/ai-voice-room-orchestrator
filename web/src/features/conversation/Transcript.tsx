import { ArrowDown, Keyboard, Mic } from 'lucide-react';
import { memo, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useSession } from '../../app/context';
import { clockTime } from '../../lib/format';
import { AI_ORDER, AI_PROFILES } from '../../lib/personas';
import { AiGlyph } from '../participants/AiGlyph';
import type { TranscriptEntry } from '../../lib/roomFeed';
import { useStore } from '../../lib/store';

const GROUP_GAP_MS = 90_000;
const NEAR_BOTTOM_PX = 96;

interface Group {
  key: string;
  first: TranscriptEntry;
  lines: TranscriptEntry[];
}

function speakerKey(e: TranscriptEntry): string {
  return `${e.kind}:${e.persona ?? e.identity ?? e.name}:${e.channel}`;
}

function groupEntries(entries: TranscriptEntry[]): Group[] {
  const groups: Group[] = [];
  for (const entry of entries) {
    const last = groups.at(-1);
    const lastLine = last?.lines.at(-1);
    if (
      last &&
      lastLine &&
      entry.kind !== 'system' &&
      speakerKey(last.first) === speakerKey(entry) &&
      entry.at - lastLine.at < GROUP_GAP_MS
    ) {
      last.lines.push(entry);
    } else {
      groups.push({ key: entry.id, first: entry, lines: [entry] });
    }
  }
  return groups;
}

export function Transcript({ botsPresent }: { botsPresent: boolean }) {
  const { feed } = useSession();
  const entries = useStore(feed.store, (s) => s.entries);
  const activity = useStore(feed.store, (s) => s.activity);
  const groups = useMemo(() => groupEntries(entries), [entries]);
  const thinking = AI_ORDER.filter((p) => activity[p].phase === 'thinking');
  // The reply an AI is voicing right now: its latest line, while it is responding.
  const liveIds = useMemo(() => {
    const ids = new Set<string>();
    for (const persona of AI_ORDER) {
      if (activity[persona].phase !== 'replying') continue;
      const last = entries.findLast((e) => e.kind === 'ai' && e.persona === persona);
      if (last) ids.add(last.id);
    }
    return ids;
  }, [entries, activity]);

  const scroller = useRef<HTMLDivElement>(null);
  const atBottom = useRef(true);
  const [unseen, setUnseen] = useState(false);

  const scrollToBottom = (behavior: ScrollBehavior) => {
    const el = scroller.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior });
  };

  // Follow the conversation only if the reader is already at the bottom.
  useLayoutEffect(() => {
    if (atBottom.current) scrollToBottom(entries.length > 1 ? 'smooth' : 'auto');
    else if (entries.length) setUnseen(true);
  }, [entries.length, thinking.length]);

  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const onScroll = () => {
      atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX;
      if (atBottom.current) setUnseen(false);
    };
    // When the space shrinks (a phone keyboard opening), keep the newest message in view
    // if that's where the reader was.
    const resize = new ResizeObserver(() => {
      if (atBottom.current) el.scrollTop = el.scrollHeight;
    });
    el.addEventListener('scroll', onScroll, { passive: true });
    resize.observe(el);
    return () => {
      el.removeEventListener('scroll', onScroll);
      resize.disconnect();
    };
  }, []);

  return (
    <div className="transcript">
      <div ref={scroller} className="transcript__scroll">
        {groups.length === 0 ? (
          <EmptyConversation botsPresent={botsPresent} />
        ) : (
          <ol className="transcript__list" role="log" aria-live="polite" aria-label="Room conversation">
            {groups.map((group) => (
              <TranscriptGroup
                key={group.key}
                group={group}
                liveId={group.lines.find((l) => liveIds.has(l.id))?.id}
              />
            ))}
          </ol>
        )}
        {thinking.map((persona) => (
          <p key={persona} className="transcript__thinking" role="status">
            <AiGlyph persona={persona} state="thinking" size="xs" />
            {AI_PROFILES[persona].name} is thinking
          </p>
        ))}
      </div>
      {unseen && (
        <button
          type="button"
          className="transcript__jump"
          onClick={() => {
            scrollToBottom('smooth');
            setUnseen(false);
          }}
        >
          <ArrowDown size={14} strokeWidth={1.75} aria-hidden="true" />
          New messages
        </button>
      )}
    </div>
  );
}

/**
 * Memoised: a new line only renders its own group. Groups are rebuilt on every update, so
 * compare what matters: the same line objects (entries are immutable) and the same live line.
 */
const TranscriptGroup = memo(
  function TranscriptGroup({ group, liveId }: { group: Group; liveId?: string }) {
    const { first } = group;
    if (first.kind === 'system') {
      return (
        <li className="line line--system">
          <p>{first.text}</p>
        </li>
      );
    }
    const ChannelIcon = first.channel === 'voice' ? Mic : Keyboard;
    const isAi = first.kind === 'ai';
    return (
      <li className={`group${isAi ? ' group--ai' : ''}`} data-persona={first.persona}>
        <header className="group__head">
          <span className="group__name">{first.mine ? 'You' : first.name}</span>
          {isAi ? (
            <span className="group__tag">AI</span>
          ) : (
            <ChannelIcon
              className="group__channel"
              size={12}
              strokeWidth={1.75}
              aria-label={first.channel === 'voice' ? 'spoken' : 'typed'}
            />
          )}
          <time className="group__time" dateTime={new Date(first.at).toISOString()}>
            {clockTime(first.at)}
          </time>
        </header>
        {group.lines.map((line) => (
          <p key={line.id} className="line" data-live={line.id === liveId || undefined}>
            {line.text}
            {line.interrupted && <span className="line__interrupted"> — interrupted</span>}
          </p>
        ))}
      </li>
    );
  },
  (prev, next) =>
    prev.liveId === next.liveId &&
    prev.group.lines.length === next.group.lines.length &&
    prev.group.lines.every((line, i) => line === next.group.lines[i]),
);

function EmptyConversation({ botsPresent }: { botsPresent: boolean }) {
  if (!botsPresent) {
    return (
      <div className="empty">
        <div className="empty__glyphs">
          <AiGlyph persona="dost" state="joining" size="sm" />
          <AiGlyph persona="sathi" state="joining" size="sm" />
        </div>
        <p className="empty__title">Bringing Dost and Sathi in</p>
        <p className="empty__body">They'll join the room in a moment.</p>
      </div>
    );
  }
  return (
    <div className="empty">
      <p className="empty__title">Everyone's here.</p>
      <p className="empty__body">
        Start talking whenever you're ready. Say “Dost” or “Sathi” to choose who answers.
      </p>
    </div>
  );
}
