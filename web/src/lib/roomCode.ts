/** Room codes and names, checked the same way the room service checks them. */

const ROOM_CODE = /^[a-z0-9][a-z0-9-]{1,46}[a-z0-9]$/;
export const NAME_MAX = 32;
export const TITLE_MAX = 40;

/** "  TECH-TALK-8F3K " -> "tech-talk-8f3k" (null if it can't be a room code). */
export function normalizeRoomCode(raw: string): string | null {
  const code = raw.trim().toLowerCase().replace(/\s+/g, '-');
  return ROOM_CODE.test(code) && !code.includes('--') ? code : null;
}

/** Accepts a pasted invite link too: ".../room/tech-talk-8f3k" -> "tech-talk-8f3k". */
export function roomCodeFromInput(raw: string): string | null {
  const fromLink = /\/room\/([^/?#\s]+)/.exec(raw);
  return normalizeRoomCode(fromLink ? decodeURIComponent(fromLink[1]) : raw);
}

export function cleanName(raw: string): string {
  return raw.replace(/\s+/g, ' ').trim();
}

export function inviteLink(code: string): string {
  return `${window.location.origin}/room/${encodeURIComponent(code)}`;
}
