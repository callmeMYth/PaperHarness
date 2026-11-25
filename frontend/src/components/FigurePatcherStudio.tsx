import React, { useEffect, useRef, useState } from 'react';
import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  Download,
  FileUp,
  Move,
  Plus,
  ShieldCheck,
  Trash2,
  Type,
} from 'lucide-react';
import { api, saveDataUri, saveTextFile } from '../api';
import { I18nDict, Lang } from '../i18n';

export interface RasterBox {
  id: string;
  text: string;
  x: number;
  y: number;
  w: number;
  h: number;
  font_size: number;
  color: string;
  font_family: string;
  align?: 'left' | 'center' | 'right';
  erase_x?: number;
  erase_y?: number;
  erase_w?: number;
  erase_h?: number;
}

export interface IncomingRasterPayload {
  id: number;
  image_b64: string;
  width: number;
  height: number;
  boxes?: Partial<RasterBox>[];
}

interface SvgNodeEdit {
  id: string;
  index: number;
  text: string;
  font_size: string;
  fill: string;
  x: string;
  y: string;
  dx: number;
  dy: number;
}

interface Props {
  lang: Lang;
  t: I18nDict;
  incomingSvg: string;
  incomingRaster?: IncomingRasterPayload | null;
  onNotify: (msg: string) => void;
}

export const FigurePatcherStudio: React.FC<Props> = ({ lang, t, incomingSvg, incomingRaster, onNotify }) => {
  const fileRef = useRef<HTMLInputElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const svgHostRef = useRef<HTMLDivElement>(null);

  const [kind, setKind] = useState<'empty' | 'svg' | 'raster'>('empty');
  const [svgSource, setSvgSource] = useState('');
  const [svgNodes, setSvgNodes] = useState<SvgNodeEdit[]>([]);
  const [selectedSvgIdx, setSelectedSvgIdx] = useState<number | null>(null);

  const [origImageB64, setOrigImageB64] = useState('');
  const [displayImageB64, setDisplayImageB64] = useState('');
  const [imgSize, setImgSize] = useState({ w: 800, h: 500 });
  const [boxes, setBoxes] = useState<RasterBox[]>([]);
  const [selectedBoxId, setSelectedBoxId] = useState<string | null>(null);
  const [livePreviewText, setLivePreviewText] = useState(true);
  const [integrity, setIntegrity] = useState<any>(null);

  const [drawRect, setDrawRect] = useState<{ x: number; y: number; w: number; h: number } | null>(null);
  const rasterDragRef = useRef<
    | { mode: 'draw'; startX: number; startY: number }
    | { mode: 'move' | 'resize'; id: string; startX: number; startY: number; origX: number; origY: number; origW: number; origH: number }
    | null
  >(null);

  const svgDragRef = useRef<{ index: number; startClientX: number; startClientY: number; origDx: number; origDy: number; scaleX: number; scaleY: number } | null>(null);

  // Load SVG sent from DataTableStudio / DiagramStudio
  useEffect(() => {
    if (!incomingSvg) return;
    const file = new File([incomingSvg], 'figure.svg', { type: 'image/svg+xml' });
    api.patcherInspect(file).then((res) => {
      setKind('svg');
      setSvgSource(res.svg);
      setSvgNodes((res.nodes || []).map((n: any) => ({ ...n, dx: 0, dy: 0 })));
      setSelectedSvgIdx(null);
      setIntegrity(null);
    });
  }, [incomingSvg]);

  // Load raster image sent from Omni-Agent Multimodal Chat
  useEffect(() => {
    if (!incomingRaster?.image_b64) return;
    setKind('raster');
    setOrigImageB64(incomingRaster.image_b64);
    setDisplayImageB64(incomingRaster.image_b64);
    setImgSize({ w: incomingRaster.width || 800, h: incomingRaster.height || 500 });
    const mapped: RasterBox[] = (incomingRaster.boxes || []).map((b, i) => ({
      id: b.id || `box-${Date.now()}-${i}`,
      text: b.text || (lang === 'zh' ? '新标签' : 'New Label'),
      x: Math.round(b.x ?? 40),
      y: Math.round(b.y ?? 40),
      w: Math.max(24, Math.round(b.w ?? 140)),
      h: Math.max(18, Math.round(b.h ?? 32)),
      font_size: Math.round(b.font_size ?? 16),
      color: b.color || '#16191F',
      font_family: b.font_family || 'sans',
      align: b.align || 'center',
    }));
    setBoxes(mapped);
    setSelectedBoxId(mapped[0]?.id || null);
    setIntegrity(null);
  }, [incomingRaster?.id]);

  // Arrow-key 1px / 5px precision nudging for selected raster box or SVG node
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if (!['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)) return;
      const step = e.shiftKey ? 5 : 1;
      const dx = e.key === 'ArrowLeft' ? -step : e.key === 'ArrowRight' ? step : 0;
      const dy = e.key === 'ArrowUp' ? -step : e.key === 'ArrowDown' ? step : 0;

      if (kind === 'raster' && selectedBoxId) {
        e.preventDefault();
        setBoxes((prev) =>
          prev.map((b) =>
            b.id === selectedBoxId
              ? { ...b, x: Math.max(0, Math.min(imgSize.w - b.w, b.x + dx)), y: Math.max(0, Math.min(imgSize.h - b.h, b.y + dy)) }
              : b,
          ),
        );
      } else if (kind === 'svg' && selectedSvgIdx !== null) {
        e.preventDefault();
        setSvgNodes((prev) => prev.map((n) => (n.index === selectedSvgIdx ? { ...n, dx: Math.round((n.dx + dx) * 10) / 10, dy: Math.round((n.dy + dy) * 10) / 10 } : n)));
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [kind, selectedBoxId, selectedSvgIdx, imgSize]);

  // Live visual reflection of SVG node edits & direct drag handles on the rendered SVG DOM
  useEffect(() => {
    if (kind !== 'svg' || !svgHostRef.current) return;
    const svgEl = svgHostRef.current.querySelector('svg');
    if (!svgEl) return;
    const texts = Array.from(svgEl.querySelectorAll('text')).filter((el) => (el.textContent || '').trim().length > 0);
    texts.forEach((el, idx) => {
      const ed = svgNodes[idx];
      if (!ed) return;
      el.setAttribute('data-ph-idx', String(idx));
      el.style.cursor = 'grab';
      el.style.userSelect = 'none';
      if (ed.fill) el.setAttribute('fill', ed.fill);
      if (ed.font_size) el.setAttribute('font-size', ed.font_size);
      el.style.transform = ed.dx || ed.dy ? `translate(${ed.dx}px, ${ed.dy}px)` : '';
      el.style.outline = selectedSvgIdx === idx ? '1.5px dashed #1E3A5F' : '';
      el.style.outlineOffset = '2px';
    });
  }, [kind, svgSource, svgNodes, selectedSvgIdx]);

  const handleSvgPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    const target = (e.target as Element)?.closest('text[data-ph-idx]') as SVGTextElement | null;
    if (!target || !svgHostRef.current) return;
    const idx = Number(target.getAttribute('data-ph-idx'));
    const node = svgNodes[idx];
    if (!node) return;
    e.preventDefault();
    setSelectedSvgIdx(idx);
    const svgEl = svgHostRef.current.querySelector('svg') as SVGSVGElement | null;
    let scaleX = 1;
    let scaleY = 1;
    if (svgEl) {
      const rect = svgEl.getBoundingClientRect();
      const vb = svgEl.viewBox?.baseVal;
      if (vb && vb.width > 0 && rect.width > 0) {
        scaleX = vb.width / rect.width;
        scaleY = vb.height / rect.height;
      }
    }
    svgDragRef.current = { index: idx, startClientX: e.clientX, startClientY: e.clientY, origDx: node.dx, origDy: node.dy, scaleX, scaleY };
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
  };

  const handleSvgPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const d = svgDragRef.current;
    if (!d) return;
    const nextDx = Math.round((d.origDx + (e.clientX - d.startClientX) * d.scaleX) * 2) / 2;
    const nextDy = Math.round((d.origDy + (e.clientY - d.startClientY) * d.scaleY) * 2) / 2;
    setSvgNodes((prev) => prev.map((n) => (n.index === d.index ? { ...n, dx: nextDx, dy: nextDy } : n)));
  };

  const handleSvgPointerUp = () => {
    svgDragRef.current = null;
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const res = await api.patcherInspect(file);
      setIntegrity(null);
      if (res.kind === 'svg') {
        setKind('svg');
        setSvgSource(res.svg);
        setSvgNodes((res.nodes || []).map((n: any) => ({ ...n, dx: 0, dy: 0 })));
        setSelectedSvgIdx(null);
        onNotify(lang === 'zh' ? `已载入无损矢量 SVG（${res.nodes?.length || 0} 个文字节点，可直接拖动位置）` : `Loaded SVG (${res.nodes?.length || 0} nodes)`);
      } else {
        setKind('raster');
        setOrigImageB64(res.image_b64);
        setDisplayImageB64(res.image_b64);
        setImgSize({ w: res.width, h: res.height });
        const initBoxes: RasterBox[] = (res.boxes || []).map((b: any) => ({
          ...b,
          align: 'center',
          erase_x: b.x,
          erase_y: b.y,
          erase_w: b.w,
          erase_h: b.h,
        }));
        setBoxes(initBoxes);
        setSelectedBoxId(initBoxes[0]?.id || null);
        onNotify(
          initBoxes.length
            ? (lang === 'zh' ? `已识别 ${initBoxes.length} 个文字框，可直接拖动定位或缩放大小` : `Detected ${initBoxes.length} boxes — drag to position`)
            : (lang === 'zh' ? '请在右侧图片上拖拽框选文字区域，选中后可拖动微调位置' : 'Drag on the image to create a box, then drag/resize to position'),
        );
      }
    } catch (err: any) {
      onNotify(err.message);
    } finally {
      e.target.value = '';
    }
  };

  const applySvg = async () => {
    const res = await api.patcherPatchSvg(svgSource, svgNodes);
    setSvgSource(res.svg);
    const reinspected = await api.patcherInspect(new File([res.svg], 'patched.svg', { type: 'image/svg+xml' }));
    setSvgNodes((reinspected.nodes || []).map((n: any) => ({ ...n, dx: 0, dy: 0 })));
    setIntegrity(res.integrity);
    onNotify(lang === 'zh' ? `已无损更新 ${res.changed_nodes} 处矢量文字及坐标` : `Patched ${res.changed_nodes} SVG nodes`);
  };

  const applyRaster = async () => {
    if (!origImageB64 || boxes.length === 0) return;
    const res = await api.patcherPatchRaster(origImageB64, boxes);
    setDisplayImageB64(res.image_b64);
    setIntegrity(res.integrity);
    onNotify(lang === 'zh' ? `已精准替换 ${res.edited_boxes} 处文字并通过框外零改动校验` : `Patched ${res.edited_boxes} boxes`);
  };

  const clientToImg = (clientX: number, clientY: number) => {
    const img = imgRef.current;
    if (!img) return { x: 0, y: 0 };
    const r = img.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(imgSize.w, ((clientX - r.left) * imgSize.w) / r.width)),
      y: Math.max(0, Math.min(imgSize.h, ((clientY - r.top) * imgSize.h) / r.height)),
    };
  };

  const onRasterPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    const pt = clientToImg(e.clientX, e.clientY);
    rasterDragRef.current = { mode: 'draw', startX: pt.x, startY: pt.y };
    setDrawRect({ x: pt.x, y: pt.y, w: 0, h: 0 });
    setSelectedBoxId(null);
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
  };

  const startBoxDrag = (e: React.PointerEvent, b: RasterBox, mode: 'move' | 'resize') => {
    e.stopPropagation();
    const pt = clientToImg(e.clientX, e.clientY);
    setSelectedBoxId(b.id);
    rasterDragRef.current = { mode, id: b.id, startX: pt.x, startY: pt.y, origX: b.x, origY: b.y, origW: b.w, origH: b.h };
    (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
  };

  const onRasterPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const d = rasterDragRef.current;
    if (!d) return;
    const pt = clientToImg(e.clientX, e.clientY);
    if (d.mode === 'draw') {
      setDrawRect({ x: Math.min(d.startX, pt.x), y: Math.min(d.startY, pt.y), w: Math.abs(pt.x - d.startX), h: Math.abs(pt.y - d.startY) });
      return;
    }
    const dx = Math.round(pt.x - d.startX);
    const dy = Math.round(pt.y - d.startY);
    setBoxes((prev) =>
      prev.map((b) => {
        if (b.id !== d.id) return b;
        if (d.mode === 'move') {
          return { ...b, x: Math.max(0, Math.min(imgSize.w - b.w, d.origX + dx)), y: Math.max(0, Math.min(imgSize.h - b.h, d.origY + dy)) };
        }
        return {
          ...b,
          w: Math.max(18, Math.min(imgSize.w - b.x, d.origW + dx)),
          h: Math.max(14, Math.min(imgSize.h - b.y, d.origH + dy)),
        };
      }),
    );
  };

  const onRasterPointerUp = () => {
    const d = rasterDragRef.current;
    if (d?.mode === 'draw' && drawRect && drawRect.w >= 14 && drawRect.h >= 10) {
      const nb: RasterBox = {
        id: `box-${Date.now()}`,
        text: lang === 'zh' ? '新标签' : 'New Label',
        x: Math.round(drawRect.x),
        y: Math.round(drawRect.y),
        w: Math.round(drawRect.w),
        h: Math.round(drawRect.h),
        font_size: Math.max(12, Math.round(drawRect.h * 0.72)),
        color: '#16191F',
        font_family: 'sans',
        align: 'center',
      };
      setBoxes((prev) => [...prev, nb]);
      setSelectedBoxId(nb.id);
    }
    rasterDragRef.current = null;
    setDrawRect(null);
  };

  const updateBox = (id: string, patch: Partial<RasterBox>) =>
    setBoxes((prev) => prev.map((b) => (b.id === id ? { ...b, ...patch } : b)));

  const downloadPatched = async () => {
    if (kind === 'svg') {
      const saved = await saveTextFile(svgSource, 'image/svg+xml;charset=utf-8', 'figure_patched.svg');
      if (saved.saved && saved.path) onNotify(lang === 'zh' ? `已导出至：${saved.path}` : `Saved: ${saved.path}`);
    } else if (displayImageB64) {
      const saved = await saveDataUri(displayImageB64, 'image/png', 'figure_patched.png');
      if (saved.saved && saved.path) onNotify(lang === 'zh' ? `已导出至：${saved.path}` : `Saved: ${saved.path}`);
    }
  };

  return (
    <div className="studio-split-wide">
      <aside className="control-sidebar">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <span className="eyebrow">{t.patch_title}</span>
          <input ref={fileRef} type="file" accept=".svg,.pdf,.png,.jpg,.jpeg" style={{ display: 'none' }} onChange={handleUpload} />
          <button className="btn btn-primary" onClick={() => fileRef.current?.click()}>
            <FileUp size={14} /> {t.patch_upload}
          </button>
          <div style={{ fontSize: 12, color: 'var(--ink-secondary)', lineHeight: 1.55 }}>
            {lang === 'zh'
              ? '推荐优先导入矢量 PDF / SVG（自动识别全部文字节点并无损编辑）；PNG/JPG 适合纯色底标注替换，保证框外像素零改动。'
              : t.patch_hint}
          </div>
        </div>

        {kind === 'svg' && (
          <div className="view-fade" style={{ display: 'flex', flexDirection: 'column', gap: 9, borderTop: '1px solid var(--border-hairline)', paddingTop: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="eyebrow">SVG ({svgNodes.length})</span>
              <button className="btn btn-primary btn-sm" onClick={applySvg}>
                {lang === 'zh' ? '应用无损修改' : 'Apply Vector Patch'}
              </button>
            </div>
            <div style={{ fontSize: 11.5, color: 'var(--ink-muted)' }}>
              {lang === 'zh' ? '提示：可在右侧 SVG 画布直接拖拽文字移动位置，或用方向键 1px 微调。' : 'Drag any SVG label directly or nudge with arrow keys.'}
            </div>
            {svgNodes.map((n, idx) => {
              const active = selectedSvgIdx === idx;
              return (
                <div
                  key={n.id}
                  onClick={() => setSelectedSvgIdx(idx)}
                  className="card"
                  style={{
                    padding: '9px 10px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 6,
                    borderColor: active ? 'var(--accent)' : undefined,
                    background: active ? 'var(--accent-soft)' : undefined,
                    cursor: 'pointer',
                  }}
                >
                  <input className="input" value={n.text} onChange={(e) => setSvgNodes((prev) => prev.map((x, i) => (i === idx ? { ...x, text: e.target.value } : x)))} />
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 34px', gap: 6 }}>
                    <input className="input mono" style={{ fontSize: 11.5 }} value={n.font_size} placeholder={lang === 'zh' ? '字号' : 'Size'} onChange={(e) => setSvgNodes((prev) => prev.map((x, i) => (i === idx ? { ...x, font_size: e.target.value } : x)))} />
                    <div style={{ display: 'flex', gap: 3 }}>
                      <button className="btn btn-sm" style={{ padding: '0 6px', flex: 1 }} title="←" onClick={() => setSvgNodes((p) => p.map((x, i) => (i === idx ? { ...x, dx: x.dx - 2 } : x)))}><ArrowLeft size={12} /></button>
                      <button className="btn btn-sm" style={{ padding: '0 6px', flex: 1 }} title="↑" onClick={() => setSvgNodes((p) => p.map((x, i) => (i === idx ? { ...x, dy: x.dy - 2 } : x)))}><ArrowUp size={12} /></button>
                      <button className="btn btn-sm" style={{ padding: '0 6px', flex: 1 }} title="↓" onClick={() => setSvgNodes((p) => p.map((x, i) => (i === idx ? { ...x, dy: x.dy + 2 } : x)))}><ArrowDown size={12} /></button>
                      <button className="btn btn-sm" style={{ padding: '0 6px', flex: 1 }} title="→" onClick={() => setSvgNodes((p) => p.map((x, i) => (i === idx ? { ...x, dx: x.dx + 2 } : x)))}><ArrowRight size={12} /></button>
                    </div>
                    <input type="color" value={n.fill.startsWith('#') ? n.fill : '#16191F'} onChange={(e) => setSvgNodes((prev) => prev.map((x, i) => (i === idx ? { ...x, fill: e.target.value } : x)))} style={{ width: 32, height: 32, border: '1px solid var(--border-hairline)', borderRadius: 6 }} />
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11.5, color: 'var(--ink-secondary)' }}>
                      ΔX
                      <input className="input mono" type="number" step={1} value={n.dx} onChange={(e) => setSvgNodes((p) => p.map((x, i) => (i === idx ? { ...x, dx: Number(e.target.value) } : x)))} />
                    </label>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11.5, color: 'var(--ink-secondary)' }}>
                      ΔY
                      <input className="input mono" type="number" step={1} value={n.dy} onChange={(e) => setSvgNodes((p) => p.map((x, i) => (i === idx ? { ...x, dy: Number(e.target.value) } : x)))} />
                    </label>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {kind === 'raster' && (
          <div className="view-fade" style={{ display: 'flex', flexDirection: 'column', gap: 9, borderTop: '1px solid var(--border-hairline)', paddingTop: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="eyebrow">{lang === 'zh' ? '文字替换框' : 'Text Boxes'} ({boxes.length})</span>
              <button className="btn btn-primary btn-sm" onClick={applyRaster} disabled={boxes.length === 0}>
                {lang === 'zh' ? '替换并校验像素' : 'Apply & Verify'}
              </button>
            </div>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--ink-secondary)', cursor: 'pointer' }}>
              <input type="checkbox" checked={livePreviewText} onChange={(e) => setLivePreviewText(e.target.checked)} />
              {lang === 'zh' ? '在图片框内实时预览替换文字' : 'Live text preview inside boxes'}
            </label>
            {boxes.map((b) => {
              const active = selectedBoxId === b.id;
              return (
                <div
                  key={b.id}
                  onClick={() => setSelectedBoxId(b.id)}
                  className="card"
                  style={{
                    padding: '9px 10px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 6,
                    borderColor: active ? 'var(--accent)' : undefined,
                    background: active ? 'var(--accent-soft)' : undefined,
                    cursor: 'pointer',
                  }}
                >
                  <div style={{ display: 'flex', gap: 5 }}>
                    <input className="input" value={b.text} onChange={(e) => updateBox(b.id, { text: e.target.value })} />
                    <button className="btn btn-ghost btn-sm" onClick={(e) => { e.stopPropagation(); setBoxes((prev) => prev.filter((x) => x.id !== b.id)); }}>
                      <Trash2 size={13} />
                    </button>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 66px 34px', gap: 6 }}>
                    <select className="select" value={b.font_family} onChange={(e) => updateBox(b.id, { font_family: e.target.value })}>
                      <option value="sans">Arial / Sans</option>
                      <option value="serif">Times / Serif</option>
                      <option value="cjk">微软雅黑 / 宋体</option>
                      <option value="mono">Consolas</option>
                    </select>
                    <input className="input mono" type="number" value={b.font_size} onChange={(e) => updateBox(b.id, { font_size: Number(e.target.value) })} />
                    <input type="color" value={b.color} onChange={(e) => updateBox(b.id, { color: e.target.value })} style={{ width: 32, height: 32, border: '1px solid var(--border-hairline)', borderRadius: 6 }} />
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 5 }}>
                    {(['x', 'y', 'w', 'h'] as const).map((k) => (
                      <label key={k} style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 10.5, color: 'var(--ink-muted)' }}>
                        {k.toUpperCase()}
                        <input
                          className="input mono"
                          type="number"
                          style={{ padding: '4px 6px', fontSize: 11.5 }}
                          value={Math.round(b[k])}
                          onChange={(e) => updateBox(b.id, { [k]: Math.max(0, Number(e.target.value)) })}
                        />
                      </label>
                    ))}
                  </div>
                  <div style={{ display: 'flex', gap: 4 }}>
                    {(['left', 'center', 'right'] as const).map((al) => (
                      <button
                        key={al}
                        className={`btn btn-sm ${(b.align || 'center') === al ? 'btn-primary' : ''}`}
                        style={{ flex: 1, height: 26, fontSize: 11.5 }}
                        onClick={() => updateBox(b.id, { align: al })}
                      >
                        {al === 'left' ? (lang === 'zh' ? '居左' : 'L') : al === 'center' ? (lang === 'zh' ? '居中' : 'C') : (lang === 'zh' ? '居右' : 'R')}
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </aside>

      <main className="canvas-area">
        <div className="card" style={{ padding: '18px 22px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexWrap: 'wrap', gap: 10 }}>
            <div>
              <div style={{ fontFamily: 'var(--font-serif)', fontSize: 19, fontWeight: 600 }}>{t.patch_title}</div>
              {kind !== 'empty' && (
                <div style={{ fontSize: 12, color: 'var(--ink-muted)', marginTop: 2, display: 'flex', alignItems: 'center', gap: 5 }}>
                  <Move size={12.5} />
                  {kind === 'raster'
                    ? (lang === 'zh' ? '空白处拖拽新建框 · 拖动框内部精确定位 · 拖右下角调整尺寸 · 方向键 1px 微调' : 'Drag blank area to draw · Drag box to move · Drag corner handle to resize · Arrow keys nudge 1px')
                    : (lang === 'zh' ? '直接点击并拖动图中任意矢量文字调整位置 · 方向键 1px 微调 · 点击左侧应用无损修改' : 'Click & drag any vector label directly to reposition · Arrow keys nudge 1px')}
                </div>
              )}
            </div>
            {kind !== 'empty' && (
              <button className="btn btn-primary btn-sm" onClick={downloadPatched}>
                <Download size={13.5} /> {t.patch_download}
              </button>
            )}
          </div>

          {integrity && (
            <div className="card view-fade" style={{ background: 'var(--sage-soft)', borderColor: 'var(--sage-border)', padding: '10px 14px', marginBottom: 14, display: 'flex', alignItems: 'center', gap: 10 }}>
              <ShieldCheck size={18} color="var(--sage)" />
              <div style={{ fontSize: 12.5 }}>
                <strong style={{ color: 'var(--sage)' }}>{lang === 'zh' ? '学术诚信像素校验通过' : 'Integrity Verified'}</strong> · {integrity.note}
              </div>
            </div>
          )}

          {kind === 'empty' && (
            <div style={{ border: '1.5px dashed var(--border-strong)', borderRadius: 10, padding: '64px 24px', textAlign: 'center', color: 'var(--ink-muted)' }}>
              <Type size={30} style={{ opacity: 0.45, marginBottom: 10 }} />
              <div style={{ fontFamily: 'var(--font-serif)', fontSize: 17, color: 'var(--ink-primary)', marginBottom: 6 }}>{t.patch_empty}</div>
              <div style={{ fontSize: 12.5, maxWidth: 460, margin: '0 auto 14px' }}>{t.patch_empty_sub}</div>
              <button className="btn btn-primary" onClick={() => fileRef.current?.click()}>
                <Plus size={14} /> {t.patch_upload}
              </button>
            </div>
          )}

          {kind === 'svg' && (
            <div
              ref={svgHostRef}
              onPointerDown={handleSvgPointerDown}
              onPointerMove={handleSvgPointerMove}
              onPointerUp={handleSvgPointerUp}
              onPointerLeave={handleSvgPointerUp}
              style={{ background: '#fff', border: '1px solid var(--border-hairline)', borderRadius: 9, padding: 18, userSelect: 'none' }}
            >
              <div className="svg-responsive" dangerouslySetInnerHTML={{ __html: svgSource }} />
            </div>
          )}

          {kind === 'raster' && displayImageB64 && (
            <div
              style={{ position: 'relative', display: 'inline-block', border: '1px solid var(--border-hairline)', borderRadius: 8, overflow: 'hidden', cursor: 'crosshair', userSelect: 'none', background: '#fff' }}
              onPointerDown={onRasterPointerDown}
              onPointerMove={onRasterPointerMove}
              onPointerUp={onRasterPointerUp}
            >
              <img ref={imgRef} src={`data:image/png;base64,${displayImageB64}`} alt="Figure" draggable={false} style={{ display: 'block', maxWidth: '100%', height: 'auto' }} />
              {boxes.map((b) => {
                const active = selectedBoxId === b.id;
                const justify = b.align === 'left' ? 'flex-start' : b.align === 'right' ? 'flex-end' : 'center';
                return (
                  <div
                    key={b.id}
                    onPointerDown={(e) => startBoxDrag(e, b, 'move')}
                    style={{
                      position: 'absolute',
                      left: `${(b.x / imgSize.w) * 100}%`,
                      top: `${(b.y / imgSize.h) * 100}%`,
                      width: `${(b.w / imgSize.w) * 100}%`,
                      height: `${(b.h / imgSize.h) * 100}%`,
                      border: active ? '2px solid var(--accent)' : '1.5px solid rgba(30, 58, 95, 0.72)',
                      background: livePreviewText ? 'rgba(255, 255, 255, 0.9)' : 'rgba(30, 58, 95, 0.14)',
                      cursor: 'move',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: justify,
                      padding: '0 3px',
                      boxShadow: active ? '0 0 0 2px rgba(30,58,95,0.22)' : 'none',
                      overflow: 'visible',
                    }}
                  >
                    {livePreviewText && (
                      <span
                        style={{
                          color: b.color,
                          fontSize: `${Math.max(10, Math.min(28, b.font_size * 0.72))}px`,
                          fontFamily: b.font_family === 'serif' ? 'Georgia, serif' : b.font_family === 'mono' ? 'Consolas, monospace' : 'Arial, sans-serif',
                          lineHeight: 1.05,
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          pointerEvents: 'none',
                        }}
                      >
                        {b.text}
                      </span>
                    )}
                    {/* Bottom-right corner resize handle */}
                    <div
                      onPointerDown={(e) => startBoxDrag(e, b, 'resize')}
                      title={lang === 'zh' ? '拖拽调整文本框大小' : 'Drag to resize'}
                      style={{
                        position: 'absolute',
                        right: -5,
                        bottom: -5,
                        width: 11,
                        height: 11,
                        borderRadius: '50%',
                        background: active ? 'var(--vermilion)' : 'var(--accent)',
                        border: '2px solid #fff',
                        cursor: 'nwse-resize',
                      }}
                    />
                  </div>
                );
              })}
              {drawRect && (
                <div style={{ position: 'absolute', left: `${(drawRect.x / imgSize.w) * 100}%`, top: `${(drawRect.y / imgSize.h) * 100}%`, width: `${(drawRect.w / imgSize.w) * 100}%`, height: `${(drawRect.h / imgSize.h) * 100}%`, border: '1.5px dashed var(--vermilion)', background: 'rgba(185, 56, 21, 0.12)', pointerEvents: 'none' }} />
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
};
