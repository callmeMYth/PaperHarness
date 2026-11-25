import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  CheckCircle2,
  Download,
  ImagePlus,
  KeyRound,
  Loader2,
  Minus,
  Move,
  Plus,
  Presentation,
  RotateCcw,
  Sparkles,
  Trash2,
  Type,
  Upload,
  Wand2,
} from 'lucide-react';
import { api, downloadBlob, saveTextFile, streamDiagramAgents } from '../api';
import { I18nDict, Lang } from '../i18n';
import { DiagramBlueprint } from '../types';

export interface DiagramRefinementPayload {
  id: number;
  venue_theme?: string;
  custom_colors?: Record<string, string>;
  node_updates?: Array<{
    match?: string;
    label?: string;
    sublabel?: string;
    tone?: string;
    icon?: string;
    ai_image_b64?: string;
  }>;
}

interface Props {
  lang: Lang;
  t: I18nDict;
  templates: Record<string, DiagramBlueprint>;
  themes: string[];
  themeDefs?: Record<string, any>;
  manuscriptContent: string;
  workspaceFigures?: Array<{ rel: string; name: string }>;
  externalDiagram?: { id: number; blueprint: DiagramBlueprint } | null;
  externalRefinement?: DiagramRefinementPayload | null;
  onSendSvgToPatcher: (svg: string) => void;
  onOpenModelHub: () => void;
  onNotify: (msg: string) => void;
}

const ICONS = [
  ['conv_stack_3d', '3D 多层卷积特征'],
  ['conv_pyramid', '3D CNN 特征金字塔'],
  ['patch_grid', 'ViT 图像分块'],
  ['attn_grid', '自注意力矩阵'],
  ['cross_attn', '多模态跨注意力'],
  ['unet_trapezoid', 'U-Net 编解码'],
  ['moe_router', 'MoE 专家路由'],
  ['diffusion_steps', '扩散去噪轨迹'],
  ['tensor_cube', '3D 张量立方体'],
  ['encoder_stack', 'Transformer 堆叠'],
  ['token_strip', 'Token 序列'],
  ['gate_router', '门控融合'],
  ['merge_pool', '特征汇聚'],
  ['none', '无图标'],
];

const FALLBACK_THEME = {
  bg: '#FFFFFF',
  ink: '#16191F',
  muted: '#525A66',
  arrow: '#2C3B4E',
  group_bg: '#F7F9FC',
  group_border: '#B8C7D9',
  palette: {
    primary: ['#EAF1F8', '#1E3A5F', '#1E3A5F'],
    accent: ['#FDF0EA', '#C2410C', '#9A3412'],
    sage: ['#ECF7F0', '#1F6F4A', '#14532D'],
    violet: ['#F3EFFB', '#5B4B8A', '#3F3364'],
    neutral: ['#F4F3EF', '#7B7F88', '#2B303A'],
  },
};

function hexToRgb(hex: string): [number, number, number] {
  const clean = (hex || '').trim().replace(/^#/, '');
  if (!/^[0-9a-fA-F]{6}$/.test(clean)) return [30, 58, 95];
  return [parseInt(clean.slice(0, 2), 16), parseInt(clean.slice(2, 4), 16), parseInt(clean.slice(4, 6), 16)];
}

function rgbToHex(r: number, g: number, b: number): string {
  const c = (v: number) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0');
  return `#${c(r)}${c(g)}${c(b)}`;
}

function tintHex(hex: string, factor = 0.86): string {
  const [r, g, b] = hexToRgb(hex);
  return rgbToHex(r + (255 - r) * factor, g + (255 - g) * factor, b + (255 - b) * factor);
}

function darkenHex(hex: string, factor = 0.72): string {
  const [r, g, b] = hexToRgb(hex);
  return rgbToHex(r * factor, g * factor, b * factor);
}

function resolveTheme(bp: DiagramBlueprint, themeDefs?: Record<string, any>) {
  const base = (themeDefs && themeDefs[bp.venue_theme]) || FALLBACK_THEME;
  const custom = bp.custom_colors || {};
  const palette: Record<string, [string, string, string]> = {};
  for (const [k, v] of Object.entries(base.palette || FALLBACK_THEME.palette)) {
    palette[k] = [...(v as [string, string, string])] as [string, string, string];
  }
  for (const tone of ['primary', 'accent', 'sage', 'violet'] as const) {
    const val = (custom as Record<string, string | undefined>)[tone];
    if (val && /^#[0-9a-fA-F]{6}$/.test(val.trim())) {
      const h = val.trim();
      palette[tone] = [tintHex(h, 0.87), h, darkenHex(h, 0.72)];
    }
  }
  const hasPrimary = Boolean(custom.primary && /^#[0-9a-fA-F]{6}$/.test(custom.primary.trim()));
  return {
    ...base,
    arrow: hasPrimary ? darkenHex(custom.primary!.trim(), 0.82) : base.arrow,
    group_bg: hasPrimary ? tintHex(custom.primary!.trim(), 0.94) : base.group_bg,
    group_border: hasPrimary ? tintHex(custom.primary!.trim(), 0.56) : base.group_border,
    palette,
  };
}

function charWidthEm(ch: string): number {
  const code = ch.charCodeAt(0);
  if ((code >= 0x4e00 && code <= 0x9fff) || (code >= 0x3000 && code <= 0x303f) || (code >= 0xff00 && code <= 0xffef)) return 1.02;
  if ('MW@#%&'.includes(ch)) return 0.85;
  if (ch >= 'A' && ch <= 'Z') return 0.68;
  if ("ilI1.,|:;!'\" ".includes(ch)) return 0.34;
  return 0.56;
}

function textWidthPx(s: string, fs: number): number {
  let sum = 0;
  for (const ch of s) sum += charWidthEm(ch);
  return sum * fs;
}

function wrapLines(text: string, maxW: number, fs: number): string[] {
  const lim = Math.max(44, maxW);
  const out: string[] = [];
  for (const raw of (text || '').split('\n')) {
    const line = raw.trim();
    if (!line) continue;
    if (textWidthPx(line, fs) <= lim) {
      out.push(line);
      continue;
    }
    const toks: string[] = [];
    let buf = '';
    for (const ch of line) {
      const c = ch.charCodeAt(0);
      if (c >= 0x4e00 && c <= 0x9fff) {
        if (buf) { toks.push(buf); buf = ''; }
        toks.push(ch);
      } else if (ch === ' ') {
        if (buf) { toks.push(buf); buf = ''; }
        toks.push(' ');
      } else {
        buf += ch;
      }
    }
    if (buf) toks.push(buf);
    let cur = '';
    for (const tok of toks) {
      if (tok === ' ' && !cur) continue;
      if (textWidthPx(cur + tok, fs) <= lim || !cur) cur += tok;
      else {
        out.push(cur.trim());
        cur = tok === ' ' ? '' : tok;
      }
    }
    if (cur.trim()) out.push(cur.trim());
  }
  return out;
}

function fitNodeTypography(label: string, sublabel: string, w: number, h: number, baseFs: number, hasIcon: boolean) {
  const icoSz = hasIcon ? Math.min(36, Math.max(22, h - 26)) : 0;
  const availW = Math.max(54, hasIcon ? w - icoSz - 28 : w - 24);
  let fs = baseFs;
  let subFs = Math.max(9.5, fs - 2.6);
  let lines = wrapLines(label, availW, fs);
  let subLines = sublabel ? wrapLines(sublabel, availW, subFs) : [];
  while (fs > 9.5) {
    const totalH = lines.length * fs * 1.28 + subLines.length * subFs * 1.25 + (subLines.length ? 4 : 0);
    const maxW = Math.max(...lines.map((l) => textWidthPx(l, fs)), ...subLines.map((l) => textWidthPx(l, subFs)), 0);
    if (totalH <= h - 14 && maxW <= availW + 2) break;
    fs -= 0.8;
    subFs = Math.max(8.5, fs - 2.4);
    lines = wrapLines(label, availW, fs);
    subLines = sublabel ? wrapLines(sublabel, availW, subFs) : [];
  }
  return { fs, subFs, lines, subLines, icoSz, availW };
}

function fitGroupLabel(label: string, gw: number, baseFs: number) {
  const availW = Math.max(80, gw - 24);
  let fs = Math.max(10.5, baseFs - 1.6);
  let lines = wrapLines(label, availW, fs);
  while (fs > 9.0 && (lines.length > 2 || lines.some((l) => textWidthPx(l, fs) > availW + 1))) {
    fs -= 0.7;
    lines = wrapLines(label, availW, fs);
  }
  return { fs, lines: lines.slice(0, 2) };
}

function rectOverlap(a: [number, number, number, number], b: [number, number, number, number]): boolean {
  return a[0] < b[2] && a[2] > b[0] && a[1] < b[3] && a[3] > b[1];
}

function rangesOverlap(a0: number, a1: number, b0: number, b1: number, pad = 4): boolean {
  return Math.min(a0, a1) - pad < Math.max(b0, b1) && Math.max(a0, a1) + pad > Math.min(b0, b1);
}

function segHitsNodes(
  x1: number,
  y1: number,
  x2: number,
  y2: number,
  nodes: DiagramBlueprint['nodes'],
  exclude: Set<string>,
  margin = 7,
): boolean {
  const sx0 = Math.min(x1, x2), sx1 = Math.max(x1, x2);
  const sy0 = Math.min(y1, y2), sy1 = Math.max(y1, y2);
  for (const n of nodes) {
    if (exclude.has(n.id)) continue;
    if (sx0 <= n.x + n.w + margin && sx1 >= n.x - margin && sy0 <= n.y + n.h + margin && sy1 >= n.y - margin) return true;
  }
  return false;
}

/** Obstacle-aware, global-lane-separated orthogonal arrow router — 1:1 identical to backend SVG & PPTX. */
function computeRoutedEdges(bp: DiagramBlueprint) {
  const nodes = bp.nodes;
  const nodeMap = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const lblFs = Math.max(10, bp.font_size - 3);

  // Deduplicate edges & strip self-loops
  const seen = new Set<string>();
  const cleanEdges: DiagramBlueprint['edges'] = [];
  for (const e of bp.edges) {
    const key = `${e.from}->${e.to}`;
    if (!e.from || !e.to || e.from === e.to || !nodeMap[e.from] || !nodeMap[e.to] || seen.has(key)) continue;
    seen.add(key);
    cleanEdges.push(e);
  }

  const minNodeY = nodes.length ? Math.min(...nodes.map((n) => n.y)) : 90;
  const maxNodeBot = nodes.length ? Math.max(...nodes.map((n) => n.y + n.h)) : bp.height - 60;
  const minGroupY = bp.groups.length ? Math.min(...bp.groups.map((g) => g.y)) : minNodeY - 26;
  const maxGroupBot = bp.groups.length ? Math.max(...bp.groups.map((g) => g.y + g.h)) : maxNodeBot + 16;

  const specs: Array<{ idx: number; edge: DiagramBlueprint['edges'][0]; sSide: string; dSide: string; mode: string }> = [];
  const sideOut: Record<string, number[]> = {};
  const sideIn: Record<string, number[]> = {};

  cleanEdges.forEach((edge, idx) => {
    const src = nodeMap[edge.from];
    const dst = nodeMap[edge.to];
    const scx = src.x + src.w / 2, scy = src.y + src.h / 2;
    const dcx = dst.x + dst.w / 2, dcy = dst.y + dst.h / 2;
    const hGapR = dst.x - (src.x + src.w);
    const hGapL = src.x - (dst.x + dst.w);
    const vGapD = dst.y - (src.y + src.h);
    const vGapU = src.y - (dst.y + dst.h);

    const betweenH = nodes.some(
      (n) =>
        n.id !== src.id &&
        n.id !== dst.id &&
        n.x + n.w > Math.min(src.x + src.w, dst.x + dst.w) + 6 &&
        n.x < Math.max(src.x, dst.x) - 6 &&
        rangesOverlap(n.y, n.y + n.h, Math.min(src.y, dst.y) - 10, Math.max(src.y + src.h, dst.y + dst.h) + 10),
    );
    const betweenV = nodes.some(
      (n) =>
        n.id !== src.id &&
        n.id !== dst.id &&
        n.y + n.h > Math.min(src.y + src.h, dst.y + dst.h) + 4 &&
        n.y < Math.max(src.y, dst.y) - 4 &&
        rangesOverlap(n.x, n.x + n.w, Math.min(src.x, dst.x) - 6, Math.max(src.x + src.w, dst.x + dst.w) + 6),
    );

    let mode = 'normal';
    let sSide = 'right';
    let dSide = 'left';
    if ((hGapR >= 18 || hGapL >= 18) && betweenH) {
      if ((scy + dcy) / 2 <= (minNodeY + maxNodeBot) / 2) {
        mode = 'bypass_top'; sSide = 'top'; dSide = 'top';
      } else {
        mode = 'bypass_bottom'; sSide = 'bottom'; dSide = 'bottom';
      }
    } else if (hGapR >= 18) { sSide = 'right'; dSide = 'left'; }
    else if (hGapL >= 18) { sSide = 'left'; dSide = 'right'; }
    else if ((vGapD >= 10 || vGapU >= 10) && betweenV) {
      mode = 'side_gutter'; sSide = 'right'; dSide = 'right';
    } else if (vGapD >= 10) { sSide = 'bottom'; dSide = 'top'; }
    else if (vGapU >= 10) { sSide = 'top'; dSide = 'bottom'; }
    else if (Math.abs(dcx - scx) >= Math.abs(dcy - scy)) {
      sSide = dcx >= scx ? 'right' : 'left';
      dSide = dcx >= scx ? 'left' : 'right';
    } else {
      sSide = dcy >= scy ? 'bottom' : 'top';
      dSide = dcy >= scy ? 'top' : 'bottom';
    }

    specs.push({ idx, edge, sSide, dSide, mode });
    (sideOut[`${src.id}:${sSide}`] ||= []).push(idx);
    (sideIn[`${dst.id}:${dSide}`] ||= []).push(idx);
  });

  Object.entries(sideOut).forEach(([k, arr]) => {
    const side = k.split(':')[1];
    arr.sort((a, b) => (side === 'left' || side === 'right' ? nodeMap[cleanEdges[a].to].y - nodeMap[cleanEdges[b].to].y : nodeMap[cleanEdges[a].to].x - nodeMap[cleanEdges[b].to].x));
  });
  Object.entries(sideIn).forEach(([k, arr]) => {
    const side = k.split(':')[1];
    arr.sort((a, b) => (side === 'left' || side === 'right' ? nodeMap[cleanEdges[a].from].y - nodeMap[cleanEdges[b].from].y : nodeMap[cleanEdges[a].from].x - nodeMap[cleanEdges[b].from].x));
  });

  const portXY = (n: DiagramBlueprint['nodes'][0], side: string, rank: number, total: number, inset: number): [number, number] => {
    const frac = total <= 1 ? 0.5 : 0.22 + 0.56 * (rank / (total - 1));
    if (side === 'right') return [n.x + n.w + inset, n.y + n.h * frac];
    if (side === 'left') return [n.x - inset, n.y + n.h * frac];
    if (side === 'bottom') return [n.x + n.w * frac, n.y + n.h + inset];
    return [n.x + n.w * frac, n.y - inset];
  };

  const usedVLanes: Array<[number, number, number]> = [];
  const usedHLanes: Array<[number, number, number]> = [];

  const pickClearX = (idealX: number, loX: number, hiX: number, yA: number, yB: number, excl: Set<string>): number => {
    const y0 = Math.min(yA, yB), y1 = Math.max(yA, yB);
    const offsets = [0];
    for (let k = 1; k <= 8; k++) offsets.push(-k * 14, k * 14);
    for (const off of offsets) {
      const cand = idealX + off;
      if (cand < loX || cand > hiX) continue;
      if (segHitsNodes(cand, y0, cand, y1, nodes, excl, 6)) continue;
      if (usedVLanes.some(([ux, uy0, uy1]) => Math.abs(cand - ux) < 12 && rangesOverlap(y0, y1, uy0, uy1))) continue;
      usedVLanes.push([cand, y0, y1]);
      return cand;
    }
    const clamped = Math.max(loX, Math.min(hiX, idealX));
    usedVLanes.push([clamped, y0, y1]);
    return clamped;
  };

  const pickClearY = (idealY: number, dir: number, xA: number, xB: number, excl: Set<string>): number => {
    const x0 = Math.min(xA, xB), x1 = Math.max(xA, xB);
    for (let k = 0; k < 10; k++) {
      const cand = Math.max(46, Math.min(bp.height - 14, idealY + dir * k * 15));
      if (segHitsNodes(x0, cand, x1, cand, nodes, excl, 5)) continue;
      if (usedHLanes.some(([uy, ux0, ux1]) => Math.abs(cand - uy) < 13 && rangesOverlap(x0, x1, ux0, ux1))) continue;
      usedHLanes.push([cand, x0, x1]);
      return cand;
    }
    usedHLanes.push([idealY, x0, x1]);
    return idealY;
  };

  const rawRouted = specs.map(({ idx, edge, sSide, dSide, mode }) => {
    const src = nodeMap[edge.from];
    const dst = nodeMap[edge.to];
    const excl = new Set([src.id, dst.id]);
    const oList = sideOut[`${src.id}:${sSide}`];
    const iList = sideIn[`${dst.id}:${dSide}`];
    const [x1, y1] = portXY(src, sSide, oList.indexOf(idx), oList.length, 1.0);
    const [x2, y2] = portXY(dst, dSide, iList.indexOf(idx), iList.length, 3.5);

    let pts: Array<[number, number]>;
    if (mode === 'bypass_top') {
      const busY = pickClearY(Math.max(48, Math.min(minGroupY - 10, minNodeY - 22)), -1, x1, x2, excl);
      pts = [[x1, y1], [x1, busY], [x2, busY], [x2, y2]];
    } else if (mode === 'bypass_bottom') {
      const busY = pickClearY(Math.min(bp.height - 18, Math.max(maxGroupBot + 10, maxNodeBot + 20)), 1, x1, x2, excl);
      pts = [[x1, y1], [x1, busY], [x2, busY], [x2, y2]];
    } else if (mode === 'side_gutter') {
      const idealGx = Math.max(x1, x2) + 22;
      const gx = pickClearX(idealGx, idealGx - 4, Math.min(bp.width - 14, idealGx + 90), y1, y2, excl);
      pts = [[x1, y1], [gx, y1], [gx, y2], [x2, y2]];
    } else if (sSide === 'right' || sSide === 'left') {
      if (Math.abs(y2 - y1) < 4.5 && !segHitsNodes(x1, y1, x2, y2, nodes, excl, 5)) {
        pts = [[x1, y1], [x2, y2]];
        usedHLanes.push([(y1 + y2) / 2, Math.min(x1, x2), Math.max(x1, x2)]);
      } else {
        const loX = Math.min(x1, x2) + 14;
        const hiX = Math.max(x1, x2) - 14;
        const midX = hiX <= loX ? (x1 + x2) / 2 : pickClearX((x1 + x2) / 2, loX, hiX, y1, y2, excl);
        pts = [[x1, y1], [midX, y1], [midX, y2], [x2, y2]];
      }
    } else if (Math.abs(x2 - x1) < 4.5 && !segHitsNodes(x1, y1, x2, y2, nodes, excl, 5)) {
      pts = [[x1, y1], [x2, y2]];
      usedVLanes.push([(x1 + x2) / 2, Math.min(y1, y2), Math.max(y1, y2)]);
    } else {
      const midY = pickClearY((y1 + y2) / 2, 1, x1, x2, excl);
      pts = [[x1, y1], [x1, midY], [x2, midY], [x2, y2]];
    }

    let d: string;
    if (pts.length <= 2) {
      d = `M ${pts[0][0].toFixed(1)} ${pts[0][1].toFixed(1)} L ${pts[1][0].toFixed(1)} ${pts[1][1].toFixed(1)}`;
    } else {
      const segs = [`M ${pts[0][0].toFixed(1)} ${pts[0][1].toFixed(1)}`];
      for (let i = 1; i < pts.length - 1; i++) {
        const [p0, p1, p2] = [pts[i - 1], pts[i], pts[i + 1]];
        const v1x = p1[0] - p0[0], v1y = p1[1] - p0[1];
        const v2x = p2[0] - p1[0], v2y = p2[1] - p1[1];
        const l1 = Math.max(0.01, Math.hypot(v1x, v1y));
        const l2 = Math.max(0.01, Math.hypot(v2x, v2y));
        const r = Math.min(8, l1 * 0.45, l2 * 0.45);
        segs.push(
          `L ${(p1[0] - (v1x / l1) * r).toFixed(1)} ${(p1[1] - (v1y / l1) * r).toFixed(1)} ` +
            `Q ${p1[0].toFixed(1)} ${p1[1].toFixed(1)} ${(p1[0] + (v2x / l2) * r).toFixed(1)} ${(p1[1] + (v2y / l2) * r).toFixed(1)}`,
        );
      }
      const last = pts[pts.length - 1];
      segs.push(`L ${last[0].toFixed(1)} ${last[1].toFixed(1)}`);
      d = segs.join(' ');
    }

    return { d, pts, lx: (x1 + x2) / 2, ly: (y1 + y2) / 2, dashed: Boolean(edge.dashed), label: (edge.label || '').trim() };
  });

  // Collision-free label pill placement
  const nodeRects: Array<[number, number, number, number]> = nodes.map((n) => [n.x - 4, n.y - 4, n.x + n.w + 4, n.y + n.h + 4]);
  const usedPills: Array<[number, number, number, number]> = [];
  for (const item of rawRouted) {
    if (!item.label) continue;
    const bw = Math.max(36, textWidthPx(item.label, lblFs) + 14);
    const bh = 21;
    const segs = [];
    for (let i = 0; i < item.pts.length - 1; i++) {
      const a = item.pts[i], b = item.pts[i + 1];
      segs.push({ a, b, len: Math.hypot(b[0] - a[0], b[1] - a[1]) });
    }
    segs.sort((x, y) => y.len - x.len);
    const { a, b } = segs[0];
    const isHoriz = Math.abs(a[1] - b[1]) < 2;
    const cands: Array<[number, number]> = [];
    for (const f of [0.5, 0.35, 0.65, 0.25, 0.75]) {
      const bx = a[0] + (b[0] - a[0]) * f;
      const by = a[1] + (b[1] - a[1]) * f;
      cands.push([bx, by]);
      if (isHoriz) cands.push([bx, by - 16], [bx, by + 16]);
      else cands.push([bx, by - 22], [bx, by + 22]);
    }
    let chosen: [number, number] = cands[0];
    for (const [cx, cy] of cands) {
      const cxC = Math.max(bw / 2 + 6, Math.min(bp.width - bw / 2 - 6, cx));
      const cyC = Math.max(bh / 2 + 6, Math.min(bp.height - bh / 2 - 6, cy));
      const rect: [number, number, number, number] = [cxC - bw / 2 - 2, cyC - bh / 2 - 2, cxC + bw / 2 + 2, cyC + bh / 2 + 2];
      if (nodeRects.some((nr) => rectOverlap(rect, nr))) continue;
      if (usedPills.some((pr) => rectOverlap(rect, pr))) continue;
      chosen = [cxC, cyC];
      usedPills.push(rect);
      break;
    }
    item.lx = chosen[0];
    item.ly = chosen[1];
  }

  return rawRouted;
}

const NodeGlyph: React.FC<{ kind: string; color: string; x: number; y: number; sz: number }> = ({ kind, color, x, y, sz }) => {
  const s = sz / 32;
  return (
    <g transform={`translate(${x},${y}) scale(${s})`} pointerEvents="none">
      {kind === 'conv_stack_3d' &&
        [
          { dx: 3, dy: 9, w: 7, h: 17, op: 0.22 },
          { dx: 11, dy: 7, w: 6, h: 19, op: 0.36 },
          { dx: 18, dy: 10, w: 5.5, h: 14, op: 0.52 },
          { dx: 24.5, dy: 12, w: 4.5, h: 11, op: 0.7 },
        ].map((sl, i) => (
          <g key={i}>
            <polygon points={`${sl.dx},${sl.dy} ${sl.dx + 3},${sl.dy - 3} ${sl.dx + sl.w + 3},${sl.dy - 3} ${sl.dx + sl.w},${sl.dy}`} fill={color} fillOpacity={sl.op * 0.7} stroke={color} strokeWidth={1.0} />
            <polygon points={`${sl.dx + sl.w},${sl.dy} ${sl.dx + sl.w + 3},${sl.dy - 3} ${sl.dx + sl.w + 3},${sl.dy + sl.h - 3} ${sl.dx + sl.w},${sl.dy + sl.h}`} fill={color} fillOpacity={sl.op * 0.9} stroke={color} strokeWidth={1.0} />
            <rect x={sl.dx} y={sl.dy} width={sl.w} height={sl.h} fill={color} fillOpacity={sl.op} stroke={color} strokeWidth={1.1} />
          </g>
        ))}
      {kind === 'conv_pyramid' &&
        [
          { dx: 2.5, dy: 6, w: 5.5, h: 21, op: 0.22 },
          { dx: 10.5, dy: 9.5, w: 5.2, h: 15.5, op: 0.42 },
          { dx: 18.2, dy: 13, w: 5, h: 10.5, op: 0.62 },
          { dx: 25, dy: 16, w: 4.5, h: 6.5, op: 0.82 },
        ].map((sl, i) => (
          <g key={i}>
            <polygon points={`${sl.dx},${sl.dy} ${sl.dx + 2.8},${sl.dy - 2.6} ${sl.dx + sl.w + 2.8},${sl.dy - 2.6} ${sl.dx + sl.w},${sl.dy}`} fill={color} fillOpacity={sl.op * 0.65} stroke={color} strokeWidth={0.95} />
            <rect x={sl.dx} y={sl.dy} width={sl.w} height={sl.h} fill={color} fillOpacity={sl.op} stroke={color} strokeWidth={1.1} />
          </g>
        ))}
      {kind === 'patch_grid' && (
        <>
          {[0, 1, 2].map((r) =>
            [0, 1, 2].map((c) => (
              <rect key={`${r}-${c}`} x={3 + c * 6.5} y={6 + r * 6.5} width={5.2} height={5.2} rx={0.9} fill={color} fillOpacity={0.2 + ((r + c) % 3) * 0.2} stroke={color} strokeWidth={0.9} />
            )),
          )}
          <line x1={23.5} y1={15.5} x2={27.5} y2={15.5} stroke={color} strokeWidth={1.3} />
          <rect x={27.5} y={7.5} width={3} height={16} rx={1} fill={color} fillOpacity={0.78} />
        </>
      )}
      {kind === 'cross_attn' && (
        <>
          <rect x={3} y={5} width={6} height={8} rx={1.5} fill={color} fillOpacity={0.3} stroke={color} strokeWidth={1.1} />
          <rect x={3} y={19} width={6} height={8} rx={1.5} fill={color} fillOpacity={0.62} stroke={color} strokeWidth={1.1} />
          <line x1={9.5} y1={9} x2={18.5} y2={22} stroke={color} strokeWidth={1.25} />
          <line x1={9.5} y1={23} x2={18.5} y2={10} stroke={color} strokeWidth={1.25} />
          <circle cx={14} cy={16} r={3.2} fill={color} fillOpacity={0.22} stroke={color} strokeWidth={1.2} />
          <rect x={20} y={8} width={8.5} height={16} rx={2} fill={color} fillOpacity={0.5} stroke={color} strokeWidth={1.2} />
        </>
      )}
      {kind === 'unet_trapezoid' && (
        <>
          <polygon points="3,6 11,11 11,21 3,26" fill={color} fillOpacity={0.28} stroke={color} strokeWidth={1.3} />
          <rect x={13.5} y={12} width={5} height={8} rx={1.2} fill={color} fillOpacity={0.78} stroke={color} strokeWidth={1.1} />
          <polygon points="29,6 21,11 21,21 29,26" fill={color} fillOpacity={0.44} stroke={color} strokeWidth={1.3} />
          <path d="M 7 6 Q 16 1 25 6" fill="none" stroke={color} strokeWidth={1.2} strokeDasharray="2,1.5" />
        </>
      )}
      {kind === 'moe_router' && (
        <>
          <polygon points="8,11 13,16 8,21 3,16" fill={color} fillOpacity={0.28} stroke={color} strokeWidth={1.3} />
          {[7, 16, 25].map((cy, idx) => (
            <g key={cy}>
              <line x1={13} y1={16} x2={20} y2={cy} stroke={color} strokeWidth={idx === 1 ? 1.8 : 1.0} strokeOpacity={idx === 1 ? 0.95 : 0.4} />
              <rect x={20} y={cy - 3.2} width={9} height={6.4} rx={1.5} fill={color} fillOpacity={idx === 1 ? 0.78 : 0.22} stroke={color} strokeWidth={1.1} />
            </g>
          ))}
        </>
      )}
      {kind === 'diffusion_steps' &&
        [
          { x: 3, op: 0.16, dash: '1.5,1.2' },
          { x: 12.5, op: 0.42, dash: '' },
          { x: 22, op: 0.82, dash: '' },
        ].map((st, i) => (
          <g key={i}>
            <rect x={st.x} y={9} width={7} height={14} rx={1.6} fill={color} fillOpacity={st.op} stroke={color} strokeWidth={1.15} strokeDasharray={st.dash || undefined} />
            {i < 2 && <line x1={st.x + 7.5} y1={16} x2={st.x + 9.5} y2={16} stroke={color} strokeWidth={1.2} />}
          </g>
        ))}
      {kind === 'tensor_cube' && (
        <>
          <polygon points="5,11 18,4 27,9 14,16" fill={color} fillOpacity={0.18} stroke={color} strokeWidth={1.6} />
          <polygon points="5,11 14,16 14,28 5,23" fill={color} fillOpacity={0.35} stroke={color} strokeWidth={1.6} />
          <polygon points="14,16 27,9 27,21 14,28" fill={color} fillOpacity={0.24} stroke={color} strokeWidth={1.6} />
        </>
      )}
      {kind === 'attn_grid' &&
        [0, 1, 2].map((r) =>
          [0, 1, 2].map((c) => (
            <rect key={`${r}-${c}`} x={5 + c * 7.5} y={5 + r * 7.5} width={6.5} height={6.5} rx={1.2} fill={color} fillOpacity={r === c ? 0.85 : 0.25} />
          )),
        )}
      {kind === 'encoder_stack' &&
        [0, 1, 2].map((i) => (
          <rect key={i} x={4} y={5 + i * 8.5} width={24} height={6} rx={2} fill={color} fillOpacity={0.22 + i * 0.2} stroke={color} strokeWidth={1.3} />
        ))}
      {kind === 'token_strip' &&
        [0, 1, 2, 3].map((i) => (
          <rect key={i} x={3.5 + i * 6.8} y={8} width={5.2} height={16} rx={1.5} fill={color} fillOpacity={0.22 + i * 0.18} stroke={color} strokeWidth={1.2} />
        ))}
      {kind === 'gate_router' && (
        <>
          <polygon points="16,4 28,16 16,28 4,16" fill={color} fillOpacity={0.18} stroke={color} strokeWidth={1.6} />
          <line x1={10} y1={16} x2={22} y2={16} stroke={color} strokeWidth={1.8} />
          <line x1={16} y1={10} x2={16} y2={22} stroke={color} strokeWidth={1.8} />
        </>
      )}
      {kind === 'merge_pool' && (
        <>
          {[8, 16, 24].map((cy) => (
            <g key={cy}>
              <circle cx={7} cy={cy} r={2.8} fill={color} fillOpacity={0.4} stroke={color} strokeWidth={1.2} />
              <line x1={10} y1={cy} x2={21} y2={16} stroke={color} strokeWidth={1.3} />
            </g>
          ))}
          <circle cx={24} cy={16} r={4.5} fill={color} fillOpacity={0.75} />
        </>
      )}
    </g>
  );
};

export const DiagramStudio: React.FC<Props> = ({
  lang,
  t,
  templates,
  themes,
  themeDefs,
  manuscriptContent,
  workspaceFigures,
  externalDiagram,
  externalRefinement,
  onSendSvgToPatcher,
  onOpenModelHub,
  onNotify,
}) => {
  const firstKey = Object.keys(templates || {})[0] || 'hierattn_cvpr';
  const [templateKey, setTemplateKey] = useState(firstKey);
  const [blueprint, setBlueprint] = useState<DiagramBlueprint | null>(templates?.[firstKey] || null);
  const [selected, setSelected] = useState<{ kind: 'node' | 'group'; id: string } | null>(null);
  const [dpi, setDpi] = useState<number>(600);
  const [concurrency, setConcurrency] = useState<number>(3);
  const [layoutMode, setLayoutMode] = useState<string>('auto');
  const [genAiIcons, setGenAiIcons] = useState<boolean>(false);
  const [generating, setGenerating] = useState(false);
  const [needApiMsg, setNeedApiMsg] = useState('');
  const [workers, setWorkers] = useState<Array<{ id: string; name: string; detail?: string; status: 'running' | 'done' | 'error'; error?: string }>>([]);
  const [auditNote, setAuditNote] = useState('');
  const [aiTileLoading, setAiTileLoading] = useState(false);

  const svgRef = useRef<SVGSVGElement>(null);
  const localImgRef = useRef<HTMLInputElement>(null);
  const dragRef = useRef<{
    kind: 'node' | 'group';
    id: string;
    mode: 'move' | 'resize';
    startX: number;
    startY: number;
    origX: number;
    origY: number;
    origW: number;
    origH: number;
  } | null>(null);

  useEffect(() => {
    if (!blueprint && templates?.[firstKey]) {
      setBlueprint(templates[firstKey]);
    }
  }, [templates]);

  useEffect(() => {
    if (!externalDiagram?.blueprint) return;
    setBlueprint(externalDiagram.blueprint);
    setSelected(null);
  }, [externalDiagram?.id]);

  useEffect(() => {
    if (!externalRefinement) return;
    setBlueprint((prev) => {
      if (!prev) return prev;
      let next = { ...prev };
      if (externalRefinement.venue_theme) next.venue_theme = externalRefinement.venue_theme;
      if (externalRefinement.custom_colors) {
        next.custom_colors = { ...(next.custom_colors || {}), ...externalRefinement.custom_colors };
      }
      if (externalRefinement.node_updates && externalRefinement.node_updates.length > 0) {
        next.nodes = next.nodes.map((n) => {
          const hit = externalRefinement.node_updates!.find((u) => {
            const m = (u.match || '').trim().toLowerCase();
            if (!m) return false;
            return n.id.toLowerCase() === m || n.label.toLowerCase().includes(m);
          });
          if (!hit) return n;
          return {
            ...n,
            ...(hit.label ? { label: hit.label } : {}),
            ...(hit.sublabel ? { sublabel: hit.sublabel } : {}),
            ...(hit.tone ? { tone: hit.tone } : {}),
            ...(hit.icon ? { icon: hit.icon, ai_image_b64: hit.ai_image_b64 || undefined } : {}),
            ...(hit.ai_image_b64 ? { ai_image_b64: hit.ai_image_b64 } : {}),
          };
        });
      }
      return next;
    });
  }, [externalRefinement?.id]);

  const routedEdges = useMemo(() => (blueprint ? computeRoutedEdges(blueprint) : []), [blueprint]);

  if (!blueprint) return null;

  const theme = resolveTheme(blueprint, themeDefs);
  const selNode = selected?.kind === 'node' ? blueprint.nodes.find((n) => n.id === selected.id) : undefined;
  const selGroup = selected?.kind === 'group' ? blueprint.groups.find((g) => g.id === selected.id) : undefined;

  const clientToSvg = (clientX: number, clientY: number) => {
    const svg = svgRef.current;
    if (!svg) return { x: 0, y: 0 };
    const rect = svg.getBoundingClientRect();
    return {
      x: ((clientX - rect.left) / rect.width) * blueprint.width,
      y: ((clientY - rect.top) / rect.height) * blueprint.height,
    };
  };

  const startDrag = (e: React.PointerEvent, kind: 'node' | 'group', id: string, mode: 'move' | 'resize') => {
    e.stopPropagation();
    (e.target as Element).setPointerCapture?.(e.pointerId);
    const item = kind === 'node' ? blueprint.nodes.find((n) => n.id === id) : blueprint.groups.find((g) => g.id === id);
    if (!item) return;
    setSelected({ kind, id });
    const pt = clientToSvg(e.clientX, e.clientY);
    dragRef.current = { kind, id, mode, startX: pt.x, startY: pt.y, origX: item.x, origY: item.y, origW: item.w, origH: item.h };
  };

  const onCanvasPointerMove = (e: React.PointerEvent) => {
    const d = dragRef.current;
    if (!d) return;
    const pt = clientToSvg(e.clientX, e.clientY);
    const dx = Math.round((pt.x - d.startX) / 4) * 4;
    const dy = Math.round((pt.y - d.startY) / 4) * 4;

    setBlueprint((prev) => {
      if (!prev) return prev;
      const updateList = <T extends { id: string; x: number; y: number; w: number; h: number }>(arr: T[], minW: number, minH: number): T[] =>
        arr.map((it) => {
          if (it.id !== d.id) return it;
          if (d.mode === 'move') {
            return { ...it, x: Math.max(8, Math.min(prev.width - it.w - 8, d.origX + dx)), y: Math.max(46, Math.min(prev.height - it.h - 8, d.origY + dy)) };
          }
          return { ...it, w: Math.max(minW, Math.min(prev.width - it.x - 8, d.origW + dx)), h: Math.max(minH, Math.min(prev.height - it.y - 8, d.origH + dy)) };
        });
      return d.kind === 'node' ? { ...prev, nodes: updateList(prev.nodes, 110, 56) } : { ...prev, groups: updateList(prev.groups, 160, 120) };
    });
  };

  const endDrag = () => { dragRef.current = null; };

  const updateNode = (id: string, patch: Partial<DiagramBlueprint['nodes'][0]>) =>
    setBlueprint((p) => (p ? { ...p, nodes: p.nodes.map((n) => (n.id === id ? { ...n, ...patch } : n)) } : p));

  const updateGroup = (id: string, patch: Partial<DiagramBlueprint['groups'][0]>) =>
    setBlueprint((p) => (p ? { ...p, groups: p.groups.map((g) => (g.id === id ? { ...g, ...patch } : g)) } : p));

  const addNewNode = () => {
    const id = `n_${Date.now().toString(36)}`;
    setBlueprint((p) => (p ? { ...p, nodes: [...p.nodes, { id, label: lang === 'zh' ? '新模块' : 'New Module', sublabel: 'R^(N×D)', x: 500, y: 210, w: 210, h: 86, tone: 'primary', icon: 'encoder_stack' }] } : p));
    setSelected({ kind: 'node', id });
  };

  const deleteSelected = () => {
    if (!selected) return;
    if (selected.kind === 'node') {
      setBlueprint((p) => (p ? { ...p, nodes: p.nodes.filter((n) => n.id !== selected.id), edges: p.edges.filter((e) => e.from !== selected.id && e.to !== selected.id) } : p));
    } else {
      setBlueprint((p) => (p ? { ...p, groups: p.groups.filter((g) => g.id !== selected.id) } : p));
    }
    setSelected(null);
  };

  const handleConcurrentAgents = async () => {
    setGenerating(true);
    setNeedApiMsg('');
    setWorkers([]);
    setAuditNote('');
    try {
      await streamDiagramAgents(
        {
          method_text: manuscriptContent,
          venue_theme: blueprint.venue_theme,
          layout_mode: layoutMode,
          custom_colors: blueprint.custom_colors,
          concurrency,
          generate_ai_icons: genAiIcons,
        },
        (evt) => {
          if (evt.type === 'need_api_key') {
            setNeedApiMsg(evt.message);
          } else if (evt.type === 'worker_start') {
            setWorkers((prev) => [...prev.filter((w) => w.id !== evt.id), { id: evt.id, name: evt.name, status: 'running' }]);
          } else if (evt.type === 'worker_done') {
            setWorkers((prev) => prev.map((w) => (w.id === evt.id ? { ...w, name: evt.name || w.name, detail: evt.detail, status: 'done' } : w)));
          } else if (evt.type === 'candidate') {
            setBlueprint(evt.blueprint);
            setSelected(null);
            if (evt.audit_note) setAuditNote(evt.audit_note);
          } else if (evt.type === 'worker_error') {
            setWorkers((prev) => prev.map((w) => (w.id === evt.id ? { ...w, status: 'error', error: evt.error } : w)));
          } else if (evt.type === 'done') {
            onNotify(lang === 'zh' ? '多智能体已协同绘成无重叠顶刊流程图，可直接 1:1 导出 .pptx' : 'Collaborative multi-agent PPTX diagram ready');
          }
        },
      );
    } catch (e: any) {
      onNotify(e.message);
    } finally {
      setGenerating(false);
    }
  };

  const handleExportSvg = async () => {
    const res = await api.diagramRender(blueprint);
    const saved = await saveTextFile(res.svg, 'image/svg+xml;charset=utf-8', 'paper_architecture.svg');
    if (saved.saved && saved.path) onNotify(lang === 'zh' ? `已导出 SVG 至：${saved.path}` : `Saved SVG: ${saved.path}`);
  };

  const lblFs = Math.max(10, blueprint.font_size - 3);

  return (
    <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: 'var(--bg-canvas)' }}>
      {/* TOP TOOLBAR: MULTI-AGENT CONCURRENCY + 1:1 PPTX / HIGH-DPI EXPORT */}
      <div style={{ padding: '10px 20px', background: 'var(--bg-paper)', borderBottom: '1px solid var(--border-hairline)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <select
            className="select"
            style={{ width: 205 }}
            value={templateKey}
            onChange={(e) => {
              const k = e.target.value;
              setTemplateKey(k);
              if (templates[k]) {
                setBlueprint(templates[k]);
                setSelected(null);
              }
            }}
          >
            <option value="hierattn_cvpr">HierAttn-Net (CVPR)</option>
            <option value="diffusion_neurips">DiT + Adapter (NeurIPS)</option>
            <option value="agent_icml">Agent 闭环 (ICML)</option>
          </select>

          <select className="select" style={{ width: 162, height: 34, padding: '0 8px' }} value={blueprint.venue_theme} onChange={(e) => setBlueprint({ ...blueprint, venue_theme: e.target.value })}>
            {(themes || ['CVPR Clean Slate', 'NeurIPS Editorial', 'Nature Scientific']).map((th) => (
              <option key={th} value={th}>
                {th}
              </option>
            ))}
          </select>

          <select
            className="select"
            style={{ width: 142, height: 34, padding: '0 8px' }}
            value={layoutMode}
            onChange={(e) => setLayoutMode(e.target.value)}
            title={lang === 'zh' ? '顶会构图骨架' : 'Layout archetype'}
          >
            <option value="auto">{lang === 'zh' ? '构图: 自动推荐' : 'Layout: Auto'}</option>
            <option value="pipeline">{lang === 'zh' ? '构图: 标准流水线' : 'Pipeline'}</option>
            <option value="dual_branch">{lang === 'zh' ? '构图: 双流多模态' : 'Dual-Branch'}</option>
            <option value="zoom_callout">{lang === 'zh' ? '构图: 核心模块放大' : 'Zoom Callout'}</option>
            <option value="sample_left">{lang === 'zh' ? '构图: 左侧输入样图' : 'Sample Left'}</option>
          </select>

          <div style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 7px', borderRadius: 7, border: '1px solid var(--border-hairline)', background: 'var(--bg-subtle)' }} title={lang === 'zh' ? '自定义主色 / 强调色（导出的 .pptx 1:1 同步）' : 'Custom Primary / Accent colors'}>
            <span style={{ fontSize: 11.5, color: 'var(--ink-muted)' }}>{lang === 'zh' ? '配色' : 'Hex'}</span>
            <input
              type="color"
              value={blueprint.custom_colors?.primary || theme.palette.primary[1]}
              onChange={(e) => setBlueprint({ ...blueprint, custom_colors: { ...(blueprint.custom_colors || {}), primary: e.target.value } })}
              style={{ width: 22, height: 22, padding: 0, border: '1px solid var(--border-hairline)', borderRadius: 4, cursor: 'pointer', background: 'none' }}
              title={lang === 'zh' ? '主色调 (Primary)' : 'Primary color'}
            />
            <input
              type="color"
              value={blueprint.custom_colors?.accent || theme.palette.accent[1]}
              onChange={(e) => setBlueprint({ ...blueprint, custom_colors: { ...(blueprint.custom_colors || {}), accent: e.target.value } })}
              style={{ width: 22, height: 22, padding: 0, border: '1px solid var(--border-hairline)', borderRadius: 4, cursor: 'pointer', background: 'none' }}
              title={lang === 'zh' ? '强调色 (Accent)' : 'Accent color'}
            />
            {blueprint.custom_colors && (
              <button
                className="btn btn-ghost btn-sm"
                style={{ padding: '0 4px', height: 22 }}
                title={lang === 'zh' ? '恢复主题默认配色' : 'Reset theme colors'}
                onClick={() => setBlueprint({ ...blueprint, custom_colors: undefined })}
              >
                <RotateCcw size={12} />
              </button>
            )}
          </div>

          <div className="segmented">
            <button className="seg-btn" style={{ padding: '0 8px' }} onClick={() => setBlueprint({ ...blueprint, font_size: Math.max(10, blueprint.font_size - 1) })}>
              <Minus size={13} />
            </button>
            <span style={{ fontSize: 12.5, fontFamily: 'var(--font-mono)', padding: '0 6px', fontWeight: 600 }}>{blueprint.font_size}px</span>
            <button className="seg-btn" style={{ padding: '0 8px' }} onClick={() => setBlueprint({ ...blueprint, font_size: Math.min(20, blueprint.font_size + 1) })}>
              <Plus size={13} />
            </button>
          </div>

          <button className="btn btn-sm" onClick={addNewNode}>
            <Plus size={13.5} /> {lang === 'zh' ? '新增模块' : 'Add Block'}
          </button>

          {/* Collaborative Multi-Agent PPT Synthesis Controls */}
          <select className="select" style={{ width: 112 }} value={concurrency} onChange={(e) => setConcurrency(Number(e.target.value))} title={lang === 'zh' ? '阶段绘制员最大并发数' : 'Stage worker concurrency'}>
            <option value={1}>并发 1 路</option>
            <option value={2}>并发 2 路</option>
            <option value={3}>并发 3 路</option>
            <option value={4}>并发 4 路</option>
          </select>

          <label style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12.5, color: 'var(--ink-secondary)', cursor: 'pointer' }}>
            <input type="checkbox" checked={genAiIcons} onChange={(e) => setGenAiIcons(e.target.checked)} />
            AI 图标
          </label>

          <button className="btn btn-primary btn-sm" onClick={handleConcurrentAgents} disabled={generating} title={lang === 'zh' ? '总规划架构师 → 并发分阶段模块绘制 → 幻觉连线审查 → 无碰撞通道布线与 1:1 PPT 合成' : 'Architect → Parallel Stage Agents → Edge Auditor → 1:1 PPTX'}>
            {generating ? <Loader2 size={13.5} className="spin" /> : <Wand2 size={13.5} />}
            {lang === 'zh' ? `多智能体协同绘 PPT (${concurrency}路)` : `Team Agents (${concurrency}×)`}
          </button>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap' }}>
          <select className="select mono" style={{ width: 108 }} value={dpi} onChange={(e) => setDpi(Number(e.target.value))}>
            <option value={600}>600 DPI</option>
            <option value={1200}>1200 DPI</option>
            <option value={300}>300 DPI</option>
          </select>
          <button className="btn btn-sm" onClick={async () => onSendSvgToPatcher((await api.diagramRender(blueprint)).svg)}>
            <Type size={13} /> {t.to_patcher}
          </button>
          <button className="btn btn-sm" onClick={handleExportSvg}>
            <Download size={13} /> SVG
          </button>
          <button className="btn btn-sm" onClick={() => downloadBlob('/api/diagrams/export-png', { blueprint, dpi }, `diagram_${dpi}dpi.png`)}>
            <Download size={13} /> {dpi} DPI
          </button>
          <button className="btn btn-sm" onClick={() => downloadBlob('/api/diagrams/export-pdf', { blueprint }, 'paper_architecture.pdf')}>
            <Download size={13} /> 矢量 PDF
          </button>
          <button className="btn btn-primary btn-sm" onClick={() => downloadBlob('/api/diagrams/export-pptx', { blueprint }, 'paper_architecture.pptx')}>
            <Presentation size={14} /> {lang === 'zh' ? '1:1 导出 .pptx' : '1:1 Export .pptx'}
          </button>
        </div>
      </div>

      {/* COLLABORATIVE MULTI-AGENT PIPELINE PROGRESS BAR */}
      {(needApiMsg || workers.length > 0) && (
        <div className="view-fade" style={{ padding: '9px 20px', background: 'var(--bg-paper)', borderBottom: '1px solid var(--border-hairline)', display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          {needApiMsg ? (
            <>
              <span style={{ fontSize: 13, color: 'var(--amber)' }}>{needApiMsg}</span>
              <button className="btn btn-primary btn-sm" onClick={onOpenModelHub}>
                <KeyRound size={13} /> {lang === 'zh' ? '配置 API Key' : 'Configure API'}
              </button>
            </>
          ) : (
            <>
              <span className="eyebrow" style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                <Sparkles size={13} color="var(--accent)" /> {lang === 'zh' ? '多智能体协同分工' : 'Agent Team'}
              </span>
              {workers.map((w) => (
                <span
                  key={w.id}
                  className={`badge ${w.status === 'done' ? 'badge-sage' : w.status === 'error' ? 'badge-vermilion' : 'badge-accent'}`}
                  title={w.error || w.detail || w.name}
                  style={{ gap: 5, padding: '4px 10px' }}
                >
                  {w.status === 'running' ? <Loader2 size={12} className="spin" /> : w.status === 'done' ? <CheckCircle2 size={12} /> : null}
                  {w.name}
                </span>
              ))}
              {auditNote && <span style={{ fontSize: 12, color: 'var(--ink-secondary)', marginLeft: 4 }}>· {auditNote}</span>}
            </>
          )}
        </div>
      )}

      {/* CONTEXTUAL QUICK-EDIT BAR */}
      <div style={{ padding: '8px 20px', background: 'var(--bg-subtle)', borderBottom: '1px solid var(--border-hairline)', display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', minHeight: 50 }}>
        {selNode ? (
          <>
            <span className="badge badge-accent">{lang === 'zh' ? '编辑模块' : 'Block'}</span>
            <input className="input" style={{ width: 220 }} value={selNode.label.replace(/\n/g, ' ')} onChange={(e) => updateNode(selNode.id, { label: e.target.value })} />
            <input className="input mono" style={{ width: 190 }} value={selNode.sublabel} onChange={(e) => updateNode(selNode.id, { sublabel: e.target.value })} />
            <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              {Object.entries(theme.palette).map(([toneKey, cols]: any) => (
                <button
                  key={toneKey}
                  onClick={() => updateNode(selNode.id, { tone: toneKey })}
                  style={{ width: 22, height: 22, borderRadius: 999, background: cols[0], border: selNode.tone === toneKey ? `2.5px solid ${cols[1]}` : `1.5px solid ${cols[1]}`, transform: selNode.tone === toneKey ? 'scale(1.15)' : 'none', cursor: 'pointer' }}
                />
              ))}
            </div>
            <select className="select" style={{ width: 148 }} value={selNode.icon || 'none'} onChange={(e) => updateNode(selNode.id, { icon: e.target.value, ai_image_b64: undefined })} title={lang === 'zh' ? '框内 2.5D 深度学习矢量示意图' : '2.5D DL Vector Schematic'}>
              {ICONS.map(([k, l]) => (
                <option key={k} value={k}>
                  {l}
                </option>
              ))}
            </select>
            {workspaceFigures && workspaceFigures.length > 0 && (
              <select
                className="select"
                style={{ width: 138 }}
                value=""
                onChange={async (e) => {
                  const rel = e.target.value;
                  if (!rel) return;
                  try {
                    const res = await api.workspaceFigureDataUrl(rel);
                    const b64 = (res.data_url || '').split(',')[1] || '';
                    if (b64) {
                      updateNode(selNode.id, { ai_image_b64: b64 });
                      onNotify(lang === 'zh' ? `已嵌入工作区论文真图 ${rel}（.pptx 同步包含）` : `Embedded ${rel}`);
                    }
                  } catch (err: any) {
                    onNotify(err.message);
                  }
                }}
                title={lang === 'zh' ? '直接嵌入当前 LaTeX 工作区里的真实论文图片' : 'Embed real workspace figure'}
              >
                <option value="">{lang === 'zh' ? '嵌入工作区真图…' : 'Workspace Fig…'}</option>
                {workspaceFigures.map((f) => (
                  <option key={f.rel} value={f.rel}>
                    {f.name}
                  </option>
                ))}
              </select>
            )}
            <input
              ref={localImgRef}
              type="file"
              accept="image/*"
              style={{ display: 'none' }}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (!f || !selNode) return;
                const reader = new FileReader();
                reader.onload = () => {
                  const b64 = String(reader.result || '').split(',')[1] || '';
                  if (b64) {
                    updateNode(selNode.id, { ai_image_b64: b64 });
                    onNotify(lang === 'zh' ? `已嵌入本地图片 ${f.name}（.pptx 同步包含）` : `Embedded ${f.name}`);
                  }
                };
                reader.readAsDataURL(f);
                e.target.value = '';
              }}
            />
            <button className="btn btn-sm" onClick={() => localImgRef.current?.click()} title={lang === 'zh' ? '上传本地 PNG/JPG/示意图嵌进方框' : 'Upload local image into box'}>
              <Upload size={13} /> {lang === 'zh' ? '本地图' : 'Image'}
            </button>
            <button
              className="btn btn-sm"
              disabled={aiTileLoading}
              onClick={async () => {
                setAiTileLoading(true);
                try {
                  const res = await api.diagramAiAsset(`${selNode.label} 3D isometric scientific vector icon`);
                  if (res.ok && res.b64) {
                    updateNode(selNode.id, { ai_image_b64: res.b64 });
                    onNotify(lang === 'zh' ? '已嵌入 AI 图标，导出 .pptx 自动包含' : 'Embedded AI icon');
                  } else {
                    onNotify(lang === 'zh' ? '请在 API 中心「角色分配」配置生图 Key（内置 2.5D 矢量图示离线可用）' : res.reason);
                  }
                } finally {
                  setAiTileLoading(false);
                }
              }}
            >
              {aiTileLoading ? <Loader2 size={13} className="spin" /> : <ImagePlus size={13} />} AI 贴图
            </button>
            <button className="btn btn-danger btn-sm" onClick={deleteSelected}>
              <Trash2 size={13} />
            </button>
          </>
        ) : selGroup ? (
          <>
            <span className="badge badge-neutral">{lang === 'zh' ? '编辑分组' : 'Stage'}</span>
            <input className="input" style={{ width: 320 }} value={selGroup.label} onChange={(e) => updateGroup(selGroup.id, { label: e.target.value })} />
            <button className="btn btn-danger btn-sm" onClick={deleteSelected}>
              <Trash2 size={13} />
            </button>
          </>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%' }}>
            <Move size={15} color="var(--accent)" />
            <span style={{ fontSize: 13, color: 'var(--ink-secondary)' }}>
              {lang === 'zh'
                ? '直接点击方框编辑文字/换色，拖动移动位置，拖动右下角圆点缩放；所有正交箭头自动避让置顶，导出的 .pptx 与画布 1:1 完全一致。'
                : 'Click any block to edit, drag to move, drag bottom-right dot to resize. Exported .pptx matches this canvas 1:1.'}
            </span>
            <input className="input" style={{ width: 290, marginLeft: 'auto' }} value={blueprint.title} onChange={(e) => setBlueprint({ ...blueprint, title: e.target.value })} />
          </div>
        )}
      </div>

      {/* INTERACTIVE CANVAS — STRICT Z-ORDER: GROUPS -> NODES -> ROUTED ARROWS ON TOP -> LABEL PILLS ON TOP */}
      <main className="canvas-area" style={{ padding: '18px 24px', alignItems: 'center' }}>
        <div className="card" style={{ width: '100%', maxWidth: 1340, padding: 18, background: '#fff', boxShadow: 'var(--shadow-paper)' }}>
          <svg
            ref={svgRef}
            viewBox={`0 0 ${blueprint.width} ${blueprint.height}`}
            style={{ width: '100%', height: 'auto', display: 'block', userSelect: 'none', touchAction: 'none' }}
            onPointerMove={onCanvasPointerMove}
            onPointerUp={endDrag}
            onPointerLeave={endDrag}
            onClick={() => setSelected(null)}
          >
            <defs>
              <marker id="live-arrow" viewBox="0 0 10 10" refX="8.2" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">
                <path d="M 0 1.2 L 9 5 L 0 8.8 z" fill={theme.arrow} />
              </marker>
            </defs>

            <rect x={0} y={0} width={blueprint.width} height={blueprint.height} fill={theme.bg} />

            {blueprint.title && (
              <text x={28} y={36} fontSize={blueprint.font_size + 3.5} fontWeight={600} fill={theme.ink}>
                {blueprint.title}
              </text>
            )}

            {/* LAYER 1: STAGE GROUPS */}
            {blueprint.groups.map((g) => {
              const isSel = selected?.kind === 'group' && selected.id === g.id;
              const { fs: gFs, lines: gLines } = fitGroupLabel(g.label, g.w, blueprint.font_size);
              return (
                <g key={g.id}>
                  <rect
                    x={g.x} y={g.y} width={g.w} height={g.h} rx={blueprint.corner_radius + 2}
                    fill={theme.group_bg} stroke={isSel ? '#1E3A5F' : theme.group_border}
                    strokeWidth={isSel ? 2.2 : 1.5} strokeDasharray="6,4" style={{ cursor: 'grab' }}
                    onPointerDown={(e) => startDrag(e, 'group', g.id, 'move')}
                    onClick={(e) => { e.stopPropagation(); setSelected({ kind: 'group', id: g.id }); }}
                  />
                  {gLines.map((gln, li) => (
                    <text key={`gl-${li}`} x={g.x + 12} y={g.y + 21 + li * (gFs * 1.24)} fontSize={gFs} fontWeight={600} fill={theme.muted} pointerEvents="none">
                      {gln}
                    </text>
                  ))}
                  {isSel && (
                    <circle cx={g.x + g.w} cy={g.y + g.h} r={6.5} fill="#1E3A5F" stroke="#fff" strokeWidth={2} style={{ cursor: 'nwse-resize' }} onPointerDown={(e) => startDrag(e, 'group', g.id, 'resize')} />
                  )}
                </g>
              );
            })}

            {/* LAYER 2: MODULE NODES */}
            {blueprint.nodes.map((n) => {
              const [fillC, borderC, textC] = theme.palette[n.tone] || theme.palette.primary;
              const isSel = selected?.kind === 'node' && selected.id === n.id;
              const hasIcon = Boolean(n.ai_image_b64 || (n.icon && n.icon !== 'none'));
              const { fs, subFs, lines, subLines, icoSz, availW } = fitNodeTypography(n.label, n.sublabel, n.w, n.h, blueprint.font_size, hasIcon);
              const textX = hasIcon ? n.x + 15 + icoSz + availW / 2 : n.x + n.w / 2;
              const lineH = fs * 1.28;
              const subH = subFs * 1.25;
              const totalH = lines.length * lineH + subLines.length * subH + (subLines.length ? 3 : 0);
              const startY = n.y + (n.h - totalH) / 2 + fs * 0.88;

              return (
                <g key={n.id}>
                  <rect
                    x={n.x} y={n.y} width={n.w} height={n.h} rx={blueprint.corner_radius}
                    fill={fillC} stroke={borderC} strokeWidth={isSel ? 2.6 : 1.7}
                    style={{ cursor: 'grab', filter: isSel ? 'drop-shadow(0 3px 8px rgba(30,58,95,0.22))' : 'drop-shadow(0 1px 2px rgba(20,24,33,0.05))' }}
                    onPointerDown={(e) => startDrag(e, 'node', n.id, 'move')}
                    onClick={(e) => { e.stopPropagation(); setSelected({ kind: 'node', id: n.id }); }}
                  />
                  {n.ai_image_b64 ? (
                    <image href={`data:image/png;base64,${n.ai_image_b64}`} x={n.x + 11} y={n.y + (n.h - icoSz) / 2} width={icoSz} height={icoSz} preserveAspectRatio="xMidYMid meet" pointerEvents="none" />
                  ) : hasIcon ? (
                    <NodeGlyph kind={n.icon} color={borderC} x={n.x + 11} y={n.y + (n.h - icoSz) / 2} sz={icoSz} />
                  ) : null}
                  {lines.map((ln, li) => (
                    <text key={`l-${li}`} x={textX} y={startY + li * lineH} textAnchor="middle" fontSize={fs} fontWeight={600} fill={textC} pointerEvents="none">
                      {ln}
                    </text>
                  ))}
                  {subLines.map((sln, si) => (
                    <text key={`s-${si}`} x={textX} y={startY + lines.length * lineH + 2 + si * subH} textAnchor="middle" fontSize={subFs} fill={theme.muted} style={{ fontFamily: 'var(--font-mono)' }} pointerEvents="none">
                      {sln}
                    </text>
                  ))}
                  {isSel && (
                    <circle cx={n.x + n.w} cy={n.y + n.h} r={6.5} fill={borderC} stroke="#fff" strokeWidth={2} style={{ cursor: 'nwse-resize' }} onPointerDown={(e) => startDrag(e, 'node', n.id, 'resize')} />
                  )}
                </g>
              );
            })}

            {/* LAYER 3: ROUTED ORTHOGONAL ARROWS STRICTLY ON TOP OF NODES (ZERO OCCLUSION!) */}
            {routedEdges.map((re, i) => (
              <path
                key={`e-${i}`}
                d={re.d}
                fill="none"
                stroke={theme.arrow}
                strokeWidth={1.9}
                strokeLinejoin="round"
                strokeLinecap="round"
                strokeDasharray={re.dashed ? '5,4' : undefined}
                markerEnd="url(#live-arrow)"
                pointerEvents="none"
              />
            ))}

            {/* LAYER 4: EDGE LABEL PILLS ON TOPMOST LAYER */}
            {routedEdges.map((re, i) => {
              if (!re.label) return null;
              const bw = Math.max(36, textWidthPx(re.label, lblFs) + 14);
              return (
                <g key={`el-${i}`} pointerEvents="none">
                  <rect x={re.lx - bw / 2} y={re.ly - 10.5} width={bw} height={21} rx={6} fill="#ffffff" stroke="#D5DCE4" strokeWidth={0.9} />
                  <text x={re.lx} y={re.ly + 3.5} textAnchor="middle" fontSize={lblFs} fontWeight={500} fill={theme.muted}>
                    {re.label}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
      </main>
    </div>
  );
};
