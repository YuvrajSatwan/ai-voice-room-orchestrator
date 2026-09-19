/**
 * At most one calm, short-lived notice at a time, most important first: connection,
 * reconnection, browser autoplay, bots missing. Microphone problems live next to the mic
 * (see Controls) so a lasting condition never covers the conversation.
 */
import { CheckCircle2, TriangleAlert, Volume2, WifiOff } from 'lucide-react';
import type { ReactNode } from 'react';
import { useSession } from '../../app/context';
import { useExpiry } from '../../hooks/useNow';

const ICON = { size: 16, strokeWidth: 1.75, 'aria-hidden': true } as const;
const BOTS_GRACE_MS = 25_000;

export function RoomNotice({ botsPresent }: { botsPresent: boolean }) {
  const { phase, reconnectedAt, audioBlocked, startAudio, joinedAt } = useSession();
  const justReconnected = !useExpiry(reconnectedAt ? reconnectedAt + 2800 : undefined);
  const botsLate = useExpiry(joinedAt + BOTS_GRACE_MS);

  let notice: { tone: 'warn' | 'ok' | 'info'; icon: ReactNode; text: string; action?: ReactNode } | null =
    null;

  if (phase === 'reconnecting') {
    notice = { tone: 'warn', icon: <WifiOff {...ICON} />, text: 'Connection interrupted. Reconnecting…' };
  } else if (justReconnected && phase === 'connected') {
    notice = { tone: 'ok', icon: <CheckCircle2 {...ICON} />, text: "You're back. The room carried on." };
  } else if (audioBlocked) {
    notice = {
      tone: 'info',
      icon: <Volume2 {...ICON} />,
      text: 'Your browser paused room audio.',
      action: (
        <button type="button" className="notice__action" onClick={() => void startAudio()}>
          Turn on audio
        </button>
      ),
    };
  } else if (phase === 'connected' && !botsPresent && botsLate) {
    notice = {
      tone: 'warn',
      icon: <TriangleAlert {...ICON} />,
      text: "Kabir and Saraah haven't joined. Check that the Roxstar worker is running, then rejoin.",
    };
  }

  return (
    <div className="notice-slot" aria-live="polite">
      {notice && (
        <div
          key={notice.text}
          className="notice"
          data-tone={notice.tone}
          role={notice.tone === 'warn' ? 'alert' : 'status'}
        >
          {notice.icon}
          <span>{notice.text}</span>
          {notice.action}
        </div>
      )}
    </div>
  );
}
