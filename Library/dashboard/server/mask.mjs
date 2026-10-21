// mask.mjs: what Codex turns and events may carry that must never reach the
// page: keys, tokens, passwords and long encoded runs (spec, "Transcripts are
// shown masked"). An over-eager pattern hides a harmless string; that is the
// accepted cost (owner's ruling R2-10).
export const MASK = '[masked]';
// A name holding one of these words: DB_PASSWORD, GITHUB_TOKEN, "api_key", APP_KEY.
const SECRET_NAME = /password|passwd|pwd|secret|token|(?:api|access|private|encryption|signing|master|app)[_-]?key/i;
// Every run has an upper bound: an open-ended one overflows V8's regexp stack
// on a run of megabytes and throws. A longer run is masked a piece at a time.
const PATTERNS = [
  // A key file whole; its body holds no '-', so a BEGIN without an END stops at once.
  /-----BEGIN [A-Z0-9 ]{0,40}PRIVATE KEY-----[^-]{0,16384}-----END [A-Z0-9 ]{0,40}PRIVATE KEY-----/g,
  /\bsk-[A-Za-z0-9_-]{20,4096}/g,
  /\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,4096}/g, // Stripe
  /\bhf_[A-Za-z0-9]{30,4096}/g, // Hugging Face
  /\bglpat-[A-Za-z0-9_-]{20,4096}/g, // GitLab
  /\bnpm_[A-Za-z0-9]{36}\b/g, // npm
  /\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,4096}/g,
  /\bgithub_pat_[A-Za-z0-9_]{20,4096}/g,
  /\bxox[abprs]-[A-Za-z0-9-]{10,4096}/g,
  /\b(?:AKIA|ASIA)[0-9A-Z]{16}\b/g, // long-term and temporary AWS key ids
  /\bAIza[0-9A-Za-z_-]{35}/g,
  /\beyJ[A-Za-z0-9_-]{8,4096}\.[A-Za-z0-9_-]{8,4096}\.[A-Za-z0-9_-]{8,4096}/g,
  // In an Authorization header or JSON field any scheme's value goes, whatever its case or length.
  /(\bAuthorization\\?["']?\s*[:=]\s*\\?["']?(?:[A-Za-z][\w.-]{0,30}\s+)?)[^\s"',;\\]{1,4096}/gi,
  /(\bBearer\s+)[A-Za-z0-9._~+/=-]{8,4096}/gi,
  /(\bBasic\s+)[A-Za-z0-9+/=]{8,4096}/g, // case kept: "a basic implementation" is prose
  /(\b[a-z][a-z0-9+.-]{1,20}:\/\/[^\s:@/]{0,256}:)[^\s@/]{1,256}(?=@)/gi, // postgres://user:password@host
  // A password as its own argument, curl's user:password, a Cookie header.
  /(\s--?(?:password|passwd|pwd)\s+)\S{1,4096}/gi,
  // curl's -u or --user up to 1,024 characters on, past a run of headers.
  /(\bcurl\b[^\n]{0,1024}?\s(?:-u\s+|--user[\s=]+)[^\s:]{1,256}:)\S{1,4096}/g,
  /(\bCookie\s*:\s*)[^\r\n]{1,4096}/gi,
  // A name and its value, in JSON, in JSON inside JSON (\"password\":\"x\"), or bare: PASSWORD=x;
  // "auth" whole too (Docker's base64 or a plain user:password). A flat object as the value goes whole.
  new RegExp(String.raw`((?:\\?["'])?(?:\b\w{0,64}?(?:${SECRET_NAME.source})\w{0,64}|\bauth\b)(?:\\?["'])?\s*(?:[:?]?=|:)\s*)`
    + String.raw`(?:\\"(?:\\\\\\"|[^"\\]|\\[^"]){0,4096}\\"|"(?:[^"\\]|\\.){0,4096}"|'[^']*'|\{[^{}]{0,4096}\}|\S+)`, 'gi'),
  /[A-Za-z0-9+/]{80,4096}={0,2}/g,
  // A run wrapped at 60 to 79 columns, as `base64` and key files print it, with its short last line.
  // After the one-line rule, which leaves no run this long to backtrack over.
  /[A-Za-z0-9+/]{60,4096}(?:\r?\n[A-Za-z0-9+/]{60,4096}={0,2}){1,4096}(?:\r?\n[A-Za-z0-9+/]{1,4096}={0,2})?/g,
];

// A key longer than one bounded run leaves its tail beside the mask; the tail
// goes too, in one pass along the text, and masks side by side read as one.
const KEY_CHAR = /[A-Za-z0-9_+/=-]/;
const RUN = /(?:\[masked\]){2,}/g;

function dropTails(text) {
  let out = '';
  let from = 0;
  for (let at; (at = text.indexOf(MASK, from)) !== -1;) {
    let end = at + MASK.length;
    while (end < text.length && KEY_CHAR.test(text[end])) end++;
    out += text.slice(from, at) + MASK;
    from = end;
  }
  return out + text.slice(from);
}

function maskText(text) {
  const t = PATTERNS.reduce((s, re) => s.replace(re, (m, keep) => (typeof keep === 'string' ? keep + MASK : MASK)), text);
  return dropTails(t).replace(RUN, MASK);
}

// Under a secret's name every string goes, and under a password or secret name
// a number too; a count under a token name (tokens: 12) stays.
const STRONG = /pass(?:word|wd)?|pwd|secret/i;
function underSecret(name, value) {
  if (typeof value === 'string') return MASK;
  if (typeof value === 'number' || typeof value === 'bigint') return STRONG.test(name) ? MASK : value;
  if (Array.isArray(value)) return value.map((v) => underSecret(name, v));
  if (value === null || typeof value !== 'object') return value;
  return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, underSecret(name, v)]));
}

export function mask(value) {
  if (typeof value === 'string') return maskText(value);
  if (Array.isArray(value)) return value.map(mask);
  if (value === null || typeof value !== 'object') return value;
  // "auth" is matched whole: as part of a name it is author or oauth, not a secret.
  return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, SECRET_NAME.test(k) || k.toLowerCase() === 'auth' ? underSecret(k, v) : mask(v)]));
}
