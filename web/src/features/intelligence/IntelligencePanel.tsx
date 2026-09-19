import { X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import type { RoomPeople } from '../../hooks/useRoomPeople';
import { DebugView } from './DebugView';
import { IntelligenceView } from './IntelligenceView';

type Tab = 'intelligence' | 'debug';

export function IntelligencePanel({
  open,
  onClose,
  people,
  name,
}: {
  open: boolean;
  onClose: () => void;
  people: RoomPeople;
  name: string;
}) {
  const [tab, setTab] = useState<Tab>('intelligence');
  const panel = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!open) return;
    panel.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  return (
    <>
      <div className="panel-backdrop" data-open={open || undefined} onClick={onClose} aria-hidden="true" />
      <aside
        ref={panel}
        className="panel"
        data-open={open || undefined}
        aria-label="Room intelligence"
        aria-hidden={!open}
        inert={!open}
        tabIndex={-1}
      >
        <header className="panel__head">
          <div className="segmented" role="tablist" aria-label="Panel view">
            {(['intelligence', 'debug'] as const).map((t) => (
              <button
                key={t}
                type="button"
                role="tab"
                id={`panel-tab-${t}`}
                aria-controls="panel-view"
                aria-selected={tab === t}
                className="segmented__item"
                onClick={() => setTab(t)}
              >
                {t === 'intelligence' ? 'Intelligence' : 'Debug'}
              </button>
            ))}
          </div>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close panel">
            <X size={18} strokeWidth={1.75} aria-hidden="true" />
          </button>
        </header>
        <div className="panel__body" role="tabpanel" id="panel-view" aria-labelledby={`panel-tab-${tab}`}>
          {open &&
            (tab === 'intelligence' ? (
              <IntelligenceView people={people} />
            ) : (
              <DebugView people={people} name={name} />
            ))}
        </div>
      </aside>
    </>
  );
}
