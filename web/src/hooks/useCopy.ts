import { useEffect, useState } from 'react';

/** Copy text to the clipboard; `copied` is true for a moment afterwards. */
export function useCopy(): [boolean, (text: string) => void] {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 1600);
    return () => window.clearTimeout(timer);
  }, [copied]);
  const copy = (text: string) => {
    void navigator.clipboard?.writeText(text).then(() => setCopied(true));
  };
  return [copied, copy];
}
