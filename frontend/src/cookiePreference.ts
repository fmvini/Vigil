import { POLICY_VERSION } from './legalContent';

export const COOKIE_PREFERENCE_KEY = 'vigil.cookie-preference';
export const COOKIE_PREFERENCE_LIFETIME = 180 * 24 * 60 * 60 * 1000;
export type CookieChoice = 'accepted' | 'refused';
export interface CookiePreference {
  version: string;
  choice: CookieChoice;
  timestamp: string;
  expires_at: string;
}

export function parseCookiePreference(raw: string | null, now = Date.now()): CookiePreference | null {
  if (!raw) return null;
  try {
    const value = JSON.parse(raw);
    if (!value || value.version !== POLICY_VERSION || !['accepted', 'refused'].includes(value.choice)
      || typeof value.timestamp !== 'string' || typeof value.expires_at !== 'string') return null;
    const timestamp = Date.parse(value.timestamp), expiry = Date.parse(value.expires_at);
    if (!Number.isFinite(timestamp) || !Number.isFinite(expiry) || timestamp > now
      || expiry <= now || expiry - timestamp !== COOKIE_PREFERENCE_LIFETIME) return null;
    return value;
  } catch { return null; }
}

export function readCookiePreference(): CookiePreference | null {
  try { return parseCookiePreference(window.localStorage.getItem(COOKIE_PREFERENCE_KEY)); }
  catch { return null; }
}

export function createCookiePreference(choice: CookieChoice, now = Date.now()): CookiePreference {
  return { version: POLICY_VERSION, choice, timestamp: new Date(now).toISOString(), expires_at: new Date(now + COOKIE_PREFERENCE_LIFETIME).toISOString() };
}
