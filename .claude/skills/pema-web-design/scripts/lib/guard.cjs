// Static completeness guard of the old Pema web (W6a). No browser needed: it reads prototype/ as text.
//
// It lists every "UI item" the code can show and checks that some inventory entry claims it:
//   token  data-nav / data-tab / data-modal / data-screen / data-finance-tab / data-action (and the other data-*
//          hooks the live walk already knows) found in HTML strings and selectors of the .js and .html files
//   id     element ids that end in -error, -empty or -toast
//   text   user-visible string literals with "Không có", "Chưa có", "Đã sạch", "Không còn", "Lỗi", "không thể"
//   fn     every function of prototype/shared/*.js and finance/finance.js that builds HTML
//
// An item is claimed when a screen lists it in `covers` (or, for fn, in `sources` as <file>#<name>), when a
// non_screens entry lists it in `covers` (with the reason and the grep that proves no UI path reaches it), or when
// it is on the `helpers` allow-list (with a reason each).
//
// Claim syntax (item key = `<kind>:<value>`; text keys are compared lower-cased, whitespace-collapsed, without
// the trailing . ! ? … :):
//   token  covers: 'screen:home'   'action:send-update'   (same format the live walk already uses)
//   id     covers: 'id:ops-error'
//   text   covers: 'text:Chưa có lịch hẹn'     exact sentence;  'text:Không tìm thấy*'  prefix
//   fn     sources: 'prototype/shared/patient.js#home'   or covers: 'fn:patient.js#home'
//
// The JS lexer below is small on purpose: strings, template literals (with nested ${}), comments, regex literals.
// The old web is plain ES2020 without JSX, which is all it has to read.

const fs = require('fs');
const path = require('path');

const KEYWORDS = new Set(['if', 'for', 'while', 'switch', 'catch', 'function', 'return', 'typeof', 'new', 'else', 'do', 'in', 'of', 'await', 'yield', 'throw', 'case', 'delete', 'void', 'with']);
const REGEX_PREV = new Set(['(', ',', '=', ':', '[', '!', '&', '|', '?', '{', '}', ';', '+', '-', '*', '%', '<', '>', '~', '^', '=>']);
const REGEX_KW = new Set(['return', 'typeof', 'case', 'do', 'else', 'in', 'of', 'delete', 'void', 'throw', 'new']);

/**
 * Lex JavaScript into tokens: {t, v, i, line}. t is one of
 *   word, num, punct, str, tpl-start, tpl-quasi, tpl-expr-start, tpl-expr-end, tpl-end, regex
 * str and tpl-quasi carry the cooked-enough text in v (escapes of \n \t \" \' \` \\ resolved, others kept).
 */
function lex(src) {
  const toks = [];
  let i = 0;
  let line = 1;
  const n = src.length;
  const stack = []; // template nesting: brace depth inside a ${ } expression
  const prevSig = () => toks.length ? toks[toks.length - 1] : null;
  const push = (t, v, at) => toks.push({ t, v, i: at, line });
  const unescape = (s) => s.replace(/\\(u\{[0-9a-fA-F]+\}|u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|.)/gs, (m, c) => {
    if (c === 'n') return '\n';
    if (c === 't') return '\t';
    if (c === 'r') return '';
    if (c[0] === 'u') return String.fromCodePoint(parseInt(c.replace(/[u{}]/g, ''), 16));
    if (c[0] === 'x' && c.length === 3) return String.fromCharCode(parseInt(c.slice(1), 16));
    return c;
  });

  function readTemplate() {
    // positioned just after the opening ` or after the closing } of a ${ } expression
    let buf = '';
    const start = i;
    while (i < n) {
      const c = src[i];
      if (c === '\\') { buf += src.slice(i, i + 2); if (src[i + 1] === '\n') line++; i += 2; continue; }
      if (c === '`') { push('tpl-quasi', unescape(buf), start); i++; push('tpl-end', '`', i - 1); return; }
      if (c === '$' && src[i + 1] === '{') {
        push('tpl-quasi', unescape(buf), start);
        i += 2;
        push('tpl-expr-start', '${', i - 2);
        stack.push(0);
        return;
      }
      if (c === '\n') line++;
      buf += c;
      i++;
    }
  }

  while (i < n) {
    const c = src[i];
    if (c === '\n') { line++; i++; continue; }
    if (c === ' ' || c === '\t' || c === '\r') { i++; continue; }
    if (c === '/' && src[i + 1] === '/') { while (i < n && src[i] !== '\n') i++; continue; }
    if (c === '/' && src[i + 1] === '*') {
      const e = src.indexOf('*/', i + 2);
      const stop = e < 0 ? n : e + 2;
      for (let k = i; k < stop; k++) if (src[k] === '\n') line++;
      i = stop;
      continue;
    }
    if (c === '"' || c === "'") {
      const q = c;
      const start = i;
      i++;
      let buf = '';
      while (i < n && src[i] !== q) {
        if (src[i] === '\\') { buf += src.slice(i, i + 2); if (src[i + 1] === '\n') line++; i += 2; continue; }
        if (src[i] === '\n') break; // unterminated: stop, never run away
        buf += src[i++];
      }
      i++;
      push('str', unescape(buf), start);
      continue;
    }
    if (c === '`') { push('tpl-start', '`', i); i++; readTemplate(); continue; }
    if (c === '{' && stack.length) { stack[stack.length - 1]++; push('punct', '{', i); i++; continue; }
    if (c === '}' && stack.length) {
      if (stack[stack.length - 1] === 0) {
        stack.pop();
        push('tpl-expr-end', '}', i);
        i++;
        readTemplate();
        continue;
      }
      stack[stack.length - 1]--;
      push('punct', '}', i);
      i++;
      continue;
    }
    if (/[A-Za-z_$]/.test(c) || c.charCodeAt(0) > 127) {
      const start = i;
      while (i < n && (/[\w$]/.test(src[i]) || src.charCodeAt(i) > 127)) i++;
      push('word', src.slice(start, i), start);
      continue;
    }
    if (/[0-9]/.test(c)) {
      const start = i;
      while (i < n && /[\w.]/.test(src[i])) i++;
      push('num', src.slice(start, i), start);
      continue;
    }
    if (c === '/') {
      const p = prevSig();
      const isRegex = !p || (p.t === 'punct' && REGEX_PREV.has(p.v)) || (p.t === 'word' && REGEX_KW.has(p.v)) || p.t === 'tpl-expr-start';
      if (isRegex) {
        const start = i;
        i++;
        let inClass = false;
        while (i < n) {
          if (src[i] === '\\') { i += 2; continue; }
          if (src[i] === '[') inClass = true;
          else if (src[i] === ']') inClass = false;
          else if (src[i] === '/' && !inClass) break;
          else if (src[i] === '\n') break;
          i++;
        }
        i++;
        while (i < n && /[a-z]/.test(src[i])) i++;
        push('regex', src.slice(start, i), start);
        continue;
      }
    }
    if (c === '=' && src[i + 1] === '>') { push('punct', '=>', i); i += 2; continue; }
    push('punct', c, i);
    i++;
  }
  return toks;
}

/** Index of the token that closes the bracket opened at toks[open]. */
function matchBracket(toks, open) {
  const pairs = { '(': ')', '[': ']', '{': '}' };
  const stack = [];
  for (let k = open; k < toks.length; k++) {
    const t = toks[k];
    if (t.t !== 'punct') continue;
    if (pairs[t.v]) stack.push(pairs[t.v]);
    else if (t.v === ')' || t.v === ']' || t.v === '}') {
      stack.pop();
      if (!stack.length) return k;
    }
  }
  return toks.length - 1;
}

/** End (exclusive token index) of an arrow function's expression body starting at toks[k]. */
function expressionEnd(toks, k) {
  let depth = 0;
  for (; k < toks.length; k++) {
    const t = toks[k];
    if (t.t === 'tpl-expr-start') depth++;
    else if (t.t === 'tpl-expr-end') depth--;
    else if (t.t === 'punct') {
      if (t.v === '(' || t.v === '[' || t.v === '{') depth++;
      else if (t.v === ')' || t.v === ']' || t.v === '}') {
        if (depth === 0) return k;
        depth--;
      } else if ((t.v === ',' || t.v === ';') && depth === 0) return k;
    }
  }
  return toks.length;
}

/** Named functions: [{name, from, to, line}] with from/to as token indexes (to exclusive). */
function findFunctions(toks) {
  const out = [];
  const isW = (k, v) => toks[k] && toks[k].t === 'word' && (v === undefined || toks[k].v === v);
  const isP = (k, v) => toks[k] && toks[k].t === 'punct' && toks[k].v === v;
  for (let k = 0; k < toks.length; k++) {
    const t = toks[k];
    // function name(...) {...}
    if (isW(k, 'function')) {
      let j = k + 1;
      if (isP(j, '*')) j++;
      if (isW(j) && !KEYWORDS.has(toks[j].v) && isP(j + 1, '(')) {
        const close = matchBracket(toks, j + 1);
        if (isP(close + 1, '{')) out.push({ name: toks[j].v, from: close + 1, to: matchBracket(toks, close + 1) + 1, line: toks[j].line });
      } else if (isP(j, '(')) {
        // anonymous function assigned: name = function(...) / name: function(...)
        const close = matchBracket(toks, j);
        const lhs = k - 1;
        if (isP(lhs, '=') || isP(lhs, ':')) {
          const nameTok = toks[lhs - 1];
          if (nameTok && (nameTok.t === 'word' || nameTok.t === 'str') && isP(close + 1, '{')) out.push({ name: nameTok.v, from: close + 1, to: matchBracket(toks, close + 1) + 1, line: nameTok.line });
        }
      }
      continue;
    }
    // name = (...) => ... | name = x => ... | name = async (...) => ... | name: (...) => ...
    if (t.t === 'word' && !KEYWORDS.has(t.v) && (isP(k + 1, '=') || isP(k + 1, ':')) && !isP(k + 2, '=')) {
      let j = k + 2;
      if (isW(j, 'async')) j++;
      let arrowAt = -1;
      if (isP(j, '(')) {
        const close = matchBracket(toks, j);
        if (isP(close + 1, '=>')) arrowAt = close + 1;
      } else if (isW(j) && !KEYWORDS.has(toks[j].v) && isP(j + 1, '=>')) arrowAt = j + 1;
      if (arrowAt > 0) {
        const bodyFrom = arrowAt + 1;
        if (isP(bodyFrom, '{')) out.push({ name: t.v, from: bodyFrom, to: matchBracket(toks, bodyFrom) + 1, line: t.line });
        else out.push({ name: t.v, from: bodyFrom, to: expressionEnd(toks, bodyFrom), line: t.line });
      }
      continue;
    }
    // method shorthand: name(...) { ... }   (object methods; never after . or function)
    if (t.t === 'word' && !KEYWORDS.has(t.v) && isP(k + 1, '(') && !isP(k - 1, '.') && !isW(k - 1, 'function')) {
      const close = matchBracket(toks, k + 1);
      if (isP(close + 1, '{') && (isP(k - 1, ',') || isP(k - 1, '{') || isP(k - 1, '}') || isW(k - 1, 'async') || isP(k - 1, ';'))) {
        out.push({ name: t.v, from: close + 1, to: matchBracket(toks, close + 1) + 1, line: t.line });
      }
    }
  }
  return out;
}

const ENTRY_NAME = /^(open|render|print|show)[A-Z_]\w*$/;
const HTML_START = /^\s*<[A-Za-z!/]/;

/** Functions (by name) that own a string or template literal starting with an HTML tag, innermost named function wins. */
function htmlFunctions(toks) {
  const fns = findFunctions(toks);
  const owner = new Array(toks.length).fill(-1);
  // inner functions overwrite outer ones: process the largest first
  const order = fns.map((f, idx) => idx).sort((a, b) => (fns[b].to - fns[b].from) - (fns[a].to - fns[a].from));
  for (const idx of order) for (let k = fns[idx].from; k < fns[idx].to; k++) owner[k] = idx;
  const hits = new Map();
  for (let k = 0; k < toks.length; k++) {
    const t = toks[k];
    const isHtml = (t.t === 'str' && HTML_START.test(t.v)) || (t.t === 'tpl-quasi' && toks[k - 1] && toks[k - 1].t === 'tpl-start' && HTML_START.test(t.v));
    if (!isHtml || owner[k] < 0) continue;
    const f = fns[owner[k]];
    if (!hits.has(f.name)) hits.set(f.name, f.line);
  }
  // entry functions count too, even when they only call another renderer: open*, render*, print*, show*
  for (const f of fns) if (ENTRY_NAME.test(f.name) && !hits.has(f.name)) hits.set(f.name, f.line);
  return hits;
}

// ---------------------------------------------------------------------------------------------------------------

const TOKEN_KEYS = {
  nav: 'nav', tab: 'tab', modal: 'modal', screen: 'screen', 'finance-tab': 'financeTab', action: 'action',
  ops: 'ops', crm: 'crm', 'care-action': 'careAction', 'care-nav': 'careNav', guide: 'guide', 'patient-filter': 'patientFilter',
  'followup-filter': 'followupFilter', 'today-filter': 'todayFilter', print: 'print', command: 'command',
};
const TOKEN_RE = new RegExp(`data-(${Object.keys(TOKEN_KEYS).join('|')})\\s*=\\s*\\\\?["']([^"'\\\\]+)\\\\?["']`, 'g');
const ID_RE = /\bid\s*=\s*\\?["']([\w${}.-]*-(?:error|empty|toast))\\?["']|#([\w-]+-(?:error|empty|toast))\b/g;
const TRIGGER = /(Không có|Chưa có|Đã sạch|Không còn|Lỗi|không thể)/i;

function normText(s) {
  return s.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').replace(/^[\s.!?…:·—-]+|[\s.!?…:]+$/g, '').trim();
}
function keyText(s) {
  return normText(s).toLowerCase();
}

/** Sentences of a literal that hold a trigger phrase. */
function triggerSentences(text) {
  const plain = text.replace(/<[^>]*>/g, '\n').replace(/\$\{[^}]*\}/g, '…');
  const out = [];
  for (const part of plain.split(/\n+/)) {
    for (const sentence of part.split(/(?<=[.!?])\s+/)) {
      if (TRIGGER.test(sentence)) {
        const s = normText(sentence);
        if (s) out.push(s);
      }
    }
  }
  return out;
}

function lineOf(src, at) {
  let n = 1;
  for (let k = 0; k < at && k < src.length; k++) if (src.charCodeAt(k) === 10) n++;
  return n;
}

const rel = (REPO, f) => path.relative(REPO, f).split(path.sep).join('/');

/** Every item the old code can show. Map<key, {kind, where: [file:line]}>. */
function scan(REPO) {
  const proto = path.join(REPO, 'prototype');
  const files = [];
  for (const dir of ['shared', 'finance']) {
    for (const f of fs.readdirSync(path.join(proto, dir))) if (f.endsWith('.js')) files.push(path.join(proto, dir, f));
  }
  const htmls = [];
  for (const dir of ['clinic-web', 'patient-mobile', 'order-review', 'finance', 'native-review']) {
    const f = path.join(proto, dir, 'index.html');
    if (fs.existsSync(f)) htmls.push(f);
  }
  const items = new Map();
  const add = (key, kind, where) => {
    if (!items.has(key)) items.set(key, { key, kind, where: [] });
    const it = items.get(key);
    if (it.where.length < 4 && !it.where.includes(where)) it.where.push(where);
  };

  for (const file of [...files, ...htmls]) {
    const src = fs.readFileSync(file, 'utf8');
    const name = rel(REPO, file);
    const base = path.basename(file);
    // tokens and ids work on the raw text: they appear in HTML strings and in selectors alike
    for (const m of src.matchAll(TOKEN_RE)) {
      if (m[2].includes('${')) continue; // dynamic value: the live walk sees the concrete values
      add(`${TOKEN_KEYS[m[1]]}:${m[2]}`, 'token', `${name}:${lineOf(src, m.index)}`);
    }
    for (const m of src.matchAll(ID_RE)) {
      const id = m[1] || m[2];
      if (id.includes('${')) continue;
      add(`id:${id}`, 'id', `${name}:${lineOf(src, m.index)}`);
    }
    if (file.endsWith('.js')) {
      const toks = lex(src);
      toks.forEach((t) => {
        if (t.t !== 'str' && t.t !== 'tpl-quasi') return;
        for (const s of triggerSentences(t.v)) add(`text:${s}`, 'text', `${name}:${t.line}`);
      });
      const inShared = file.includes(`${path.sep}shared${path.sep}`) || file.endsWith(path.join('finance', 'finance.js'));
      if (inShared) for (const [fn, line] of htmlFunctions(toks)) add(`fn:${base}#${fn}`, 'fn', `${name}:${line}`);
    } else {
      // html files: text nodes and the inline script
      const body = src.replace(/<script[\s\S]*?<\/script>/g, '').replace(/<style[\s\S]*?<\/style>/g, '');
      for (const s of triggerSentences(body)) add(`text:${s}`, 'text', name);
    }
  }
  return items;
}

/** Parse a claim token into a matcher over item keys. */
function claimMatches(claim, key) {
  if (claim === key) return true;
  if (claim.startsWith('text:') && key.startsWith('text:')) {
    const c = keyText(claim.slice(5));
    const k = keyText(key.slice(5));
    if (c.endsWith('*')) return k.startsWith(c.slice(0, -1).trim());
    return c === k;
  }
  return false;
}

/**
 * Claims = covers of every screen and non_screen entry, helpers, `sources` as fn claims, plus the live-walk actions map.
 * Returns {unclaimed: [{key, kind, where}], claimed: n, total: n, unusedClaims: [claim]}.
 */
function evaluate(items, catalog) {
  const claims = new Set();
  const fnClaims = new Set();
  const addSource = (s) => {
    const m = /([^/]+\.js)#([\w$]+)$/.exec(s);
    if (m) fnClaims.add(`fn:${m[1]}#${m[2]}`);
  };
  for (const s of catalog.screens) {
    (s.covers || []).forEach((c) => claims.add(c));
    (s.sources || []).forEach(addSource);
  }
  for (const n of catalog.non_screens) (n.covers || []).forEach((c) => claims.add(c));
  for (const h of catalog.helpers || []) {
    claims.add(h.key);
  }
  Object.keys(catalog.actions || {}).forEach((a) => claims.add(a));
  const textClaims = [...claims].filter((c) => c.startsWith('text:'));
  const used = new Set();
  const unclaimed = [];
  for (const it of items.values()) {
    let ok = false;
    if (it.kind === 'fn') ok = fnClaims.has(it.key) || claims.has(it.key);
    else if (it.kind === 'text') {
      const hit = textClaims.find((c) => claimMatches(c, it.key));
      if (hit) { ok = true; used.add(hit); }
    } else ok = claims.has(it.key);
    if (ok) used.add(it.key);
    if (!ok) unclaimed.push(it);
  }
  const unusedClaims = [...claims].filter((c) => /^(text|id|fn):/.test(c) && !used.has(c) && ![...items.keys()].some((k) => claimMatches(c, k)));
  return { unclaimed, total: items.size, unusedClaims };
}

module.exports = { lex, findFunctions, htmlFunctions, scan, evaluate, claimMatches, keyText, normText, triggerSentences };
