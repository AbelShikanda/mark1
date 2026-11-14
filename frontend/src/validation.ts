// Shared input rules. These mirror the backend validators in models.py so the
// form rejects bad values before the request is sent.

const SCHEME_RE = /^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//;
const PHONE_RE = /^\+?[0-9][0-9\s().-]{5,24}$/;

/**
 * Return a URL with an http(s) scheme. Bare hosts such as "example.com" are
 * upgraded to "https://example.com"; empty input stays empty.
 */
export function normalizeUrl(value: string): string {
  const text = value.trim();
  if (!text) return '';
  return SCHEME_RE.test(text) ? text : `https://${text}`;
}

/** True when the value is an empty string or a valid http(s) URL. */
export function isValidUrl(value: string): boolean {
  const text = value.trim();
  if (!text) return true;
  const candidate = normalizeUrl(text);
  try {
    const parsed = new URL(candidate);
    return (
      (parsed.protocol === 'http:' || parsed.protocol === 'https:') &&
      Boolean(parsed.hostname) &&
      parsed.hostname.includes('.')
    );
  } catch {
    return false;
  }
}

/** True when the value is an empty string, an upload path, or a valid URL. */
export function isValidMediaUrl(value: string): boolean {
  const text = value.trim();
  if (!text) return true;
  if (text.startsWith('/uploads/') || text.startsWith('data:')) return true;
  return isValidUrl(text);
}

/** Normalise a media URL while leaving upload paths and data URLs untouched. */
export function normalizeMediaUrl(value: string): string {
  const text = value.trim();
  if (!text || text.startsWith('/uploads/') || text.startsWith('data:')) return text;
  return normalizeUrl(text);
}

/** True when the value looks like a phone number (7-15 digits). */
export function isValidPhone(value: string): boolean {
  const text = value.trim();
  if (!text || !PHONE_RE.test(text)) return false;
  const digits = text.replace(/\D/g, '');
  return digits.length >= 7 && digits.length <= 15;
}
