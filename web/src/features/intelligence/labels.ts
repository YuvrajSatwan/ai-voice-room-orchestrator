/** Plain-language labels for the backend's routing reasons and reply outcomes. */

export const REASON_LABEL: Record<string, string> = {
  named: 'called by name',
  follow_up: 'follow-up',
  answer: 'an answer to its question',
  question: 'a question',
  not_for_bots: 'not for the AI',
  asked_another_human: 'asked another person',
  moderated: 'abusive language',
  empty: 'nothing said',
};

export const OUTCOME_LABEL: Record<string, string> = {
  spoken: 'Answered',
  fallback_spoken: 'Apologized: the model was unavailable',
  text_only: 'Answered in text: voice failed',
  interrupted: 'Interrupted',
  interrupted_before_speaking: 'Stopped before speaking',
};

export function reasonLabel(reason: string): string {
  return REASON_LABEL[reason] ?? reason.replaceAll('_', ' ');
}

export function outcomeLabel(outcome: string): string {
  return OUTCOME_LABEL[outcome] ?? outcome.replaceAll('_', ' ');
}

export function excerpt(text: string | undefined, max = 64): string | undefined {
  if (!text) return undefined;
  return text.length > max ? `${text.slice(0, max - 1).trimEnd()}…` : text;
}
