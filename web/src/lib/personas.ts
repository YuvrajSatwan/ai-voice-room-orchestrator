/** Who is who in the room, read from the attributes the backend sets on each participant. */
import type { Participant } from 'livekit-client';
import type { Persona } from '../types/room';

export interface AiProfile {
  persona: Persona;
  identity: string;
  name: string;
  gender: 'Male' | 'Female';
  initial: string;
}

// Mirrors src/roxstar/personas.py. The internal ids ('dost', 'sathi', 'ai-dost', 'ai-sathi')
// stay stable; only the names people see are Kabir (male voice) and Saraah (female voice).
export const AI_PROFILES: Record<Persona, AiProfile> = {
  dost: { persona: 'dost', identity: 'ai-dost', name: 'Kabir', gender: 'Male', initial: 'K' },
  sathi: { persona: 'sathi', identity: 'ai-sathi', name: 'Saraah', gender: 'Female', initial: 'S' },
};

export const AI_ORDER: Persona[] = ['dost', 'sathi'];

export function isBrain(p: Participant): boolean {
  return p.attributes['roxstar.role'] === 'brain';
}

export function personaOf(p: Participant): Persona | null {
  const fromAttr = p.attributes['roxstar.persona'];
  if (fromAttr === 'dost' || fromAttr === 'sathi') return fromAttr;
  return personaOfIdentity(p.identity);
}

export function personaOfIdentity(identity: string | undefined): Persona | null {
  if (identity === AI_PROFILES.dost.identity) return 'dost';
  if (identity === AI_PROFILES.sathi.identity) return 'sathi';
  return null;
}

export function isHuman(p: Participant): boolean {
  return !isBrain(p) && personaOf(p) === null;
}

/** Display name: "Kabir" / "Saraah" for bots, the typed name for humans. */
export function displayName(p: Participant): string {
  const persona = personaOf(p);
  if (persona) return AI_PROFILES[persona].name;
  return p.name || p.identity;
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const letters = parts.length > 1 ? parts[0][0] + parts[1][0] : name.slice(0, 1);
  return letters.toUpperCase();
}
