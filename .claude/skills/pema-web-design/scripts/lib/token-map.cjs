// Maps computed styles of the old web to the names of pema-agent/frontend/src/ui/tokens.json (light values).
// A colour with no token within DELTA_E (CIEDE2000) is reported as `unmatched`: it is input for the W3 canvas tokens.
const fs = require('fs');
const path = require('path');
const { REPO } = require('./pw.cjs');

const DELTA_E = 3;
const TOKENS_PATH = path.join(REPO, 'pema-agent', 'frontend', 'src', 'ui', 'tokens.json');
// when several tokens hold the same value, the first one in this list names it
const PREFER = ['ink', 'ink-soft', 'heading', 'link', 'surface', 'canvas', 'canvas-alt', 'line', 'line-strong', 'tile', 'field', 'table-head', 'row-hover', 'success', 'success-soft', 'success-line', 'info', 'info-soft', 'info-line', 'warning', 'warning-soft', 'warning-line', 'danger', 'danger-soft', 'danger-line', 'accent', 'accent-strong', 'focus', 'plate', 'brand-500', 'brand-600', 'brand-400', 'brand-200', 'brand-100', 'brand-50', 'brand-700'];

function loadTokens() {
  return JSON.parse(fs.readFileSync(TOKENS_PATH, 'utf8').replace(/^﻿/, ''));
}

function parseColor(s) {
  const m = /^rgba?\(([^)]+)\)$/.exec(String(s).trim());
  if (!m) return null;
  const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number);
  let [r, g, b, a] = [p[0], p[1], p[2], p.length > 3 ? p[3] : 1];
  if ([r, g, b].some((x) => Number.isNaN(x))) return null;
  if (a === 0) return null;
  if (a < 1) {
    // composite over white: the old web paints on a white or very light page
    r = Math.round(r * a + 255 * (1 - a));
    g = Math.round(g * a + 255 * (1 - a));
    b = Math.round(b * a + 255 * (1 - a));
  }
  return [r, g, b];
}

const hex = ([r, g, b]) => '#' + [r, g, b].map((x) => x.toString(16).padStart(2, '0')).join('');
function fromHex(h) {
  const m = /^#([0-9a-f]{6})$/i.exec(h);
  if (m) return [0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16));
  const m3 = /^#([0-9a-f]{3})$/i.exec(h);
  if (m3) return [...m3[1]].map((c) => parseInt(c + c, 16));
  const rgb = /^rgb\((\d+) (\d+) (\d+)(?: \/ ([\d.]+)%?)?\)$/.exec(h);
  if (rgb) {
    const a = rgb[4] === undefined ? 1 : Number(rgb[4]) / (rgb[4] > 1 ? 100 : 1);
    return [0, 1, 2].map((i) => Math.round(Number(rgb[i + 1]) * a + 255 * (1 - a)));
  }
  return null;
}

function toLab([r, g, b]) {
  const lin = (c) => {
    c /= 255;
    return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  };
  const [R, G, B] = [lin(r), lin(g), lin(b)];
  const X = (R * 0.4124564 + G * 0.3575761 + B * 0.1804375) / 0.95047;
  const Y = R * 0.2126729 + G * 0.7151522 + B * 0.072175;
  const Z = (R * 0.0193339 + G * 0.119192 + B * 0.9503041) / 1.08883;
  const f = (t) => (t > 216 / 24389 ? Math.cbrt(t) : (24389 / 27 * t + 16) / 116);
  const [fx, fy, fz] = [f(X), f(Y), f(Z)];
  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
}

/** CIEDE2000 */
function deltaE(l1, l2) {
  const [L1, a1, b1] = l1;
  const [L2, a2, b2] = l2;
  const rad = Math.PI / 180;
  const C1 = Math.hypot(a1, b1);
  const C2 = Math.hypot(a2, b2);
  const Cm = (C1 + C2) / 2;
  const G = 0.5 * (1 - Math.sqrt(Math.pow(Cm, 7) / (Math.pow(Cm, 7) + Math.pow(25, 7))));
  const a1p = (1 + G) * a1;
  const a2p = (1 + G) * a2;
  const C1p = Math.hypot(a1p, b1);
  const C2p = Math.hypot(a2p, b2);
  const h = (b, a) => {
    if (b === 0 && a === 0) return 0;
    const x = Math.atan2(b, a) / rad;
    return x >= 0 ? x : x + 360;
  };
  const h1p = h(b1, a1p);
  const h2p = h(b2, a2p);
  const dLp = L2 - L1;
  const dCp = C2p - C1p;
  let dhp = 0;
  if (C1p * C2p !== 0) {
    dhp = h2p - h1p;
    if (dhp > 180) dhp -= 360;
    else if (dhp < -180) dhp += 360;
  }
  const dHp = 2 * Math.sqrt(C1p * C2p) * Math.sin((dhp * rad) / 2);
  const Lpm = (L1 + L2) / 2;
  const Cpm = (C1p + C2p) / 2;
  let hpm = h1p + h2p;
  if (C1p * C2p !== 0) {
    if (Math.abs(h1p - h2p) > 180) hpm += h1p + h2p < 360 ? 360 : -360;
    hpm /= 2;
  }
  const T = 1 - 0.17 * Math.cos((hpm - 30) * rad) + 0.24 * Math.cos(2 * hpm * rad) + 0.32 * Math.cos((3 * hpm + 6) * rad) - 0.2 * Math.cos((4 * hpm - 63) * rad);
  const dTheta = 30 * Math.exp(-Math.pow((hpm - 275) / 25, 2));
  const Rc = 2 * Math.sqrt(Math.pow(Cpm, 7) / (Math.pow(Cpm, 7) + Math.pow(25, 7)));
  const Sl = 1 + (0.015 * Math.pow(Lpm - 50, 2)) / Math.sqrt(20 + Math.pow(Lpm - 50, 2));
  const Sc = 1 + 0.045 * Cpm;
  const Sh = 1 + 0.015 * Cpm * T;
  const Rt = -Math.sin(2 * dTheta * rad) * Rc;
  return Math.sqrt(Math.pow(dLp / Sl, 2) + Math.pow(dCp / Sc, 2) + Math.pow(dHp / Sh, 2) + Rt * (dCp / Sc) * (dHp / Sh));
}

function colorIndex(tokens) {
  const entries = Object.entries(tokens.color.light).map(([name, v]) => ({ name, rgb: fromHex(v), v })).filter((e) => e.rgb);
  entries.forEach((e) => (e.lab = toLab(e.rgb)));
  entries.sort((a, b) => {
    const ia = PREFER.indexOf(a.name);
    const ib = PREFER.indexOf(b.name);
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
  });
  return entries;
}

function nearestColor(index, rgb) {
  const lab = toLab(rgb);
  let best = null;
  for (const e of index) {
    const d = deltaE(lab, e.lab);
    if (!best || d < best.d - 1e-9) best = { name: e.name, d, v: e.v };
  }
  return best;
}

const num = (s) => parseFloat(String(s));

/**
 * raw: {color, bg, border, radius, font, shadow, family} → {color:{token:n}, ..., unmatched:{...}}
 * Each raw entry is {n, ex}. Text colour, background and border colour share the colour tokens.
 */
function mapRaw(raw, tokens, index) {
  const out = { color: {}, background: {}, border: {}, radius: {}, text: {}, family: {}, shadow_n: 0, unmatched: { color: [], radius: [], text: [] } };
  const colorPart = (key, target, role) => {
    for (const [css, info] of Object.entries(raw[key] || {})) {
      const rgb = parseColor(css);
      if (!rgb) continue;
      const near = nearestColor(index, rgb);
      if (near.d <= DELTA_E) out[target][near.name] = (out[target][near.name] || 0) + info.n;
      else out.unmatched.color.push({ hex: hex(rgb), role, n: info.n, ex: info.ex, nearest: near.name, dE: Math.round(near.d * 10) / 10 });
    }
  };
  colorPart('color', 'color', 'text');
  colorPart('bg', 'background', 'background');
  colorPart('border', 'border', 'border');
  const named = (group, value) => {
    const v = num(value);
    let best = null;
    for (const [name, t] of Object.entries(tokens[group])) {
      const d = Math.abs(num(t) - v);
      if (!best || d < best.d) best = { name, d };
    }
    return best;
  };
  for (const [css, info] of Object.entries(raw.radius || {})) {
    const near = named('radius', css);
    if (near && near.d < 0.5) out.radius[near.name] = (out.radius[near.name] || 0) + info.n;
    else out.unmatched.radius.push({ px: num(css), n: info.n, ex: info.ex, nearest: near ? near.name : '' });
  }
  for (const [css, info] of Object.entries(raw.font || {})) {
    const near = named('text', css);
    if (near && near.d < 0.5) out.text[near.name] = (out.text[near.name] || 0) + info.n;
    else out.unmatched.text.push({ px: num(css), n: info.n, ex: info.ex, nearest: near ? near.name : '' });
  }
  for (const [fam, info] of Object.entries(raw.family || {})) out.family[fam] = (out.family[fam] || 0) + info.n;
  out.shadow_n = Object.values(raw.shadow || {}).reduce((a, b) => a + b.n, 0);
  const sortObj = (o) => Object.fromEntries(Object.entries(o).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])));
  for (const k of ['color', 'background', 'border', 'radius', 'text', 'family']) out[k] = sortObj(out[k]);
  out.unmatched.color.sort((a, b) => b.n - a.n || a.hex.localeCompare(b.hex));
  return out;
}

module.exports = { loadTokens, colorIndex, mapRaw, parseColor, hex, nearestColor, DELTA_E, TOKENS_PATH };
