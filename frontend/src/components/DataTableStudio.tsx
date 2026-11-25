import React, { useEffect, useState } from 'react';
import {
  BarChart3,
  ChevronDown,
  ChevronUp,
  Code2,
  Copy,
  Download,
  FileSpreadsheet,
  Loader2,
  Minus,
  Play,
  Plus,
  Sparkles,
  Table2,
  Type,
} from 'lucide-react';
import { api, downloadBlob, saveDataUri, saveTextFile } from '../api';
import { I18nDict, Lang } from '../i18n';

export interface ExternalChartPayload {
  id: number;
  sub_mode: 'figure' | 'table';
  csv_text: string;
  chart_type?: string;
  title?: string;
  ylabel?: string;
  venue?: string;
  caption?: string;
  label?: string;
  lower_is_better?: string[];
}

interface Props {
  lang: Lang;
  t: I18nDict;
  sampleDatasets: Record<string, any>;
  palettes: Record<string, string[]>;
  venuePresets: Record<string, any>;
  externalChart?: ExternalChartPayload | null;
  onSendSvgToPatcher: (svg: string) => void;
  onNotify: (msg: string) => void;
}

export const DataTableStudio: React.FC<Props> = ({
  lang,
  t,
  sampleDatasets,
  palettes,
  venuePresets,
  externalChart,
  onSendSvgToPatcher,
  onNotify,
}) => {
  const [subMode, setSubMode] = useState<'figure' | 'table'>('figure');
  const [datasetKey, setDatasetKey] = useState('benchmark_bars');
  const [csvText, setCsvText] = useState(sampleDatasets?.benchmark_bars?.csv || '');
  const [analysis, setAnalysis] = useState<any>(null);

  const [chartType, setChartType] = useState('grouped_bar');
  const [venue, setVenue] = useState('CVPR / ICCV');
  const [spacingMode, setSpacingMode] = useState<'airy' | 'standard' | 'compact'>('airy');
  const [colWidth, setColWidth] = useState<'single' | 'double'>('double');
  const [fontFamily, setFontFamily] = useState('DejaVu Serif');
  const [fontSize, setFontSize] = useState(11.0);
  const [lineWidth, setLineWidth] = useState(2.0);
  const [paletteName, setPaletteName] = useState('oxford_academic');
  const [legendPos, setLegendPos] = useState('top');
  const [showGrid, setShowGrid] = useState(true);
  const [showValues, setShowValues] = useState(true);
  const [dpi, setDpi] = useState(600);
  const [chartTitle, setChartTitle] = useState('High-Resolution VLM Benchmark Comparison');
  const [ylabel, setYlabel] = useState('Score (%)');
  const [moreOpen, setMoreOpen] = useState(false);

  const [rendering, setRendering] = useState(false);
  const [svgOut, setSvgOut] = useState('');
  const [pngB64, setPngB64] = useState('');
  const [pdfB64, setPdfB64] = useState('');
  const [pythonCode, setPythonCode] = useState('');
  const [showCode, setShowCode] = useState(false);

  const [tableCaption, setTableCaption] = useState('Quantitative comparison across high-resolution VLM benchmarks. Best results are in bold and second-best are underlined.');
  const [tableLabel, setTableLabel] = useState('tab:main_results');
  const [lowerCols, setLowerCols] = useState<string[]>(['GFLOPs']);
  const [decimals, setDecimals] = useState<string>('1');
  const [tableRes, setTableRes] = useState<any>(null);

  const loadSample = (key: string) => {
    setDatasetKey(key);
    const ds = sampleDatasets[key];
    if (!ds) return;
    setCsvText(ds.csv);
    setChartType(ds.recommended_chart || 'grouped_bar');
    setLowerCols(ds.lower_is_better || []);
    setChartTitle(ds.name || '');
    setPythonCode('');
  };

  useEffect(() => {
    if (!externalChart) return;
    setSubMode(externalChart.sub_mode);
    if (externalChart.csv_text) setCsvText(externalChart.csv_text);
    if (externalChart.chart_type) setChartType(externalChart.chart_type);
    if (externalChart.title) setChartTitle(externalChart.title);
    if (externalChart.ylabel) setYlabel(externalChart.ylabel);
    if (externalChart.venue && venuePresets?.[externalChart.venue]) applyVenuePreset(externalChart.venue);
    if (externalChart.caption) setTableCaption(externalChart.caption);
    if (externalChart.label) setTableLabel(externalChart.label);
    if (externalChart.lower_is_better) setLowerCols(externalChart.lower_is_better);
    setPythonCode('');
  }, [externalChart?.id]);

  useEffect(() => {
    const timer = setTimeout(() => {
      if (!csvText.trim()) return;
      api.chartAnalyze(csvText).then(setAnalysis).catch(() => {});
      api
        .tableGenerate({
          csv_text: csvText,
          caption: tableCaption,
          label: tableLabel,
          lower_is_better: lowerCols,
          decimals: decimals === '' ? null : Number(decimals),
          highlight_best: true,
        })
        .then(setTableRes)
        .catch(() => {});
    }, 200);
    return () => clearTimeout(timer);
  }, [csvText, tableCaption, tableLabel, lowerCols, decimals]);

  const renderChart = async (useCustomCode = false) => {
    if (!csvText.trim()) return;
    setRendering(true);
    try {
      const res = await api.chartRender({
        csv_text: csvText,
        chart_type: chartType,
        title: chartTitle,
        ylabel,
        venue,
        width_in: colWidth === 'single' ? 4.4 : 7.6,
        height_in: colWidth === 'single' ? 3.2 : 4.4,
        font_family: fontFamily,
        font_size: fontSize,
        line_width: lineWidth,
        palette_name: paletteName,
        legend_pos: legendPos,
        show_grid: showGrid,
        show_values: showValues,
        spacing_mode: spacingMode,
        dpi,
        custom_code: useCustomCode ? pythonCode : undefined,
      });
      setSvgOut(res.svg);
      setPngB64(res.png_b64);
      setPdfB64(res.pdf_b64);
      setPythonCode(res.code);
    } catch (e: any) {
      onNotify(e.message);
    } finally {
      setRendering(false);
    }
  };

  useEffect(() => {
    if (subMode !== 'figure') return;
    const timer = setTimeout(() => renderChart(false), 180);
    return () => clearTimeout(timer);
  }, [csvText, chartType, venue, spacingMode, colWidth, fontFamily, fontSize, lineWidth, paletteName, legendPos, showGrid, showValues, dpi, chartTitle, ylabel, subMode]);

  const applyVenuePreset = (v: string) => {
    setVenue(v);
    const p = venuePresets[v];
    if (p) {
      setFontFamily(p.font_family);
      setFontSize(p.font_size);
      setLineWidth(p.line_width);
      setPaletteName(p.palette);
      setShowGrid(p.grid);
    }
  };

  const downloadUri = async (b64: string, mime: string, fname: string) => {
    const res = await saveDataUri(b64, mime, fname);
    if (res.saved && res.path) onNotify(lang === 'zh' ? `已导出至：${res.path}` : `Saved to: ${res.path}`);
  };

  const downloadSvg = async () => {
    const res = await saveTextFile(svgOut, 'image/svg+xml;charset=utf-8', `figure_${chartType}.svg`);
    if (res.saved && res.path) onNotify(lang === 'zh' ? `已导出 SVG 至：${res.path}` : `Saved SVG: ${res.path}`);
  };

  return (
    <div className="studio-split">
      {/* STREAMLINED LEFT DATA PANEL (ONLY DATA + LABELS + FOLDABLE ADVANCED) */}
      <aside className="control-sidebar">
        <div className="segmented" style={{ width: '100%' }}>
          <button className={`seg-btn ${subMode === 'figure' ? 'active' : ''}`} style={{ flex: 1, justifyContent: 'center' }} onClick={() => setSubMode('figure')}>
            <BarChart3 size={14} /> {t.sub_figure}
          </button>
          <button className={`seg-btn ${subMode === 'table' ? 'active' : ''}`} style={{ flex: 1, justifyContent: 'center' }} onClick={() => setSubMode('table')}>
            <Table2 size={14} /> {t.sub_table}
          </button>
        </div>

        <div>
          <label className="field-label">{t.sample_ds}</label>
          <select className="select" value={datasetKey} onChange={(e) => loadSample(e.target.value)}>
            {Object.entries(sampleDatasets || {}).map(([k, v]: any) => (
              <option key={k} value={k}>
                {v.name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="field-label">{t.csv_label}</label>
          <textarea className="textarea mono" rows={8} value={csvText} onChange={(e) => setCsvText(e.target.value)} />
        </div>

        {subMode === 'figure' ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div>
              <label className="field-label">{t.fig_title}</label>
              <input className="input" style={{ marginBottom: 7 }} value={chartTitle} onChange={(e) => setChartTitle(e.target.value)} />
              <input className="input" value={ylabel} onChange={(e) => setYlabel(e.target.value)} placeholder="Y 轴标签" />
            </div>

            <button className="btn btn-ghost btn-sm" style={{ justifyContent: 'space-between', padding: '0 4px' }} onClick={() => setMoreOpen((v) => !v)}>
              <span className="eyebrow">{lang === 'zh' ? '更多精细排版选项' : 'More Style Options'}</span>
              {moreOpen ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
            </button>

            {moreOpen && (
              <div className="view-fade" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                  <div>
                    <label className="field-label">{t.col_width}</label>
                    <select className="select" value={colWidth} onChange={(e) => setColWidth(e.target.value as any)}>
                      <option value="double">{t.double_col}</option>
                      <option value="single">{t.single_col}</option>
                    </select>
                  </div>
                  <div>
                    <label className="field-label">{t.font_family}</label>
                    <select className="select" value={fontFamily} onChange={(e) => setFontFamily(e.target.value)}>
                      <option value="DejaVu Serif">Times / Serif</option>
                      <option value="DejaVu Sans">Helvetica / Sans</option>
                      <option value="SimSun">宋体 (中文)</option>
                      <option value="Microsoft YaHei">微软雅黑</option>
                    </select>
                  </div>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                  <div>
                    <label className="field-label">{t.legend_pos}</label>
                    <select className="select" value={legendPos} onChange={(e) => setLegendPos(e.target.value)}>
                      <option value="top">{lang === 'zh' ? '顶部横排' : 'Top'}</option>
                      <option value="best">{lang === 'zh' ? '图内自动' : 'Best'}</option>
                      <option value="right">{lang === 'zh' ? '右侧外部' : 'Right'}</option>
                      <option value="none">{lang === 'zh' ? '隐藏' : 'None'}</option>
                    </select>
                  </div>
                  <div>
                    <label className="field-label">{t.line_width} ({lineWidth.toFixed(1)})</label>
                    <input type="range" min={1.2} max={3.2} step={0.2} value={lineWidth} onChange={(e) => setLineWidth(Number(e.target.value))} style={{ width: '100%', marginTop: 8, accentColor: 'var(--accent)' }} />
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 14, fontSize: 13 }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                    <input type="checkbox" checked={showGrid} onChange={(e) => setShowGrid(e.target.checked)} /> {t.gridlines}
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                    <input type="checkbox" checked={showValues} onChange={(e) => setShowValues(e.target.checked)} /> {t.data_labels}
                  </label>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="view-fade" style={{ display: 'flex', flexDirection: 'column', gap: 11 }}>
            <div>
              <label className="field-label">{lang === 'zh' ? '表题 Caption' : 'Caption'}</label>
              <textarea className="textarea" rows={3} value={tableCaption} onChange={(e) => setTableCaption(e.target.value)} />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 90px', gap: 8 }}>
              <div>
                <label className="field-label">LaTeX Label</label>
                <input className="input mono" value={tableLabel} onChange={(e) => setTableLabel(e.target.value)} />
              </div>
              <div>
                <label className="field-label">{lang === 'zh' ? '小数位' : 'Dec'}</label>
                <select className="select" value={decimals} onChange={(e) => setDecimals(e.target.value)}>
                  <option value="">Auto</option>
                  <option value="1">1</option>
                  <option value="2">2</option>
                  <option value="3">3</option>
                </select>
              </div>
            </div>
            <div>
              <label className="field-label">{lang === 'zh' ? '越小越优列 (↓)' : 'Lower-is-Better (↓)'}</label>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {(analysis?.num_cols || []).map((col: string) => {
                  const isLow = lowerCols.includes(col);
                  return (
                    <button
                      key={col}
                      className={`btn btn-sm ${isLow ? 'btn-primary' : ''}`}
                      onClick={() => setLowerCols((prev) => (prev.includes(col) ? prev.filter((c) => c !== col) : [...prev, col]))}
                    >
                      {col} {isLow ? '↓' : '↑'}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        )}
      </aside>

      <main key={subMode} className="canvas-area view-fade">
        {subMode === 'figure' ? (
          <>
            {/* 1-CLICK EFFORTLESS STYLE & HIGH-DPI RIBBON */}
            <div className="card" style={{ padding: '12px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <select className="select" style={{ width: 146 }} value={venue} onChange={(e) => applyVenuePreset(e.target.value)}>
                  {Object.keys(venuePresets || {}).map((v) => (
                    <option key={v} value={v}>
                      {v}
                    </option>
                  ))}
                </select>

                {/* Spacing One-Click Switch */}
                <div className="segmented" title={lang === 'zh' ? '文字与图形疏密间距' : 'Spacing'}>
                  {(
                    [
                      ['airy', lang === 'zh' ? '宽松' : 'Airy'],
                      ['standard', lang === 'zh' ? '标准' : 'Std'],
                      ['compact', lang === 'zh' ? '紧凑' : 'Tight'],
                    ] as const
                  ).map(([k, lbl]) => (
                    <button key={k} className={`seg-btn ${spacingMode === k ? 'active' : ''}`} onClick={() => setSpacingMode(k)}>
                      {lbl}
                    </button>
                  ))}
                </div>

                {/* Font Size Stepper */}
                <div className="segmented" title={t.font_size}>
                  <button className="seg-btn" style={{ padding: '0 8px' }} onClick={() => setFontSize((f) => Math.max(8, f - 0.5))}>
                    <Minus size={13} />
                  </button>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12.5, padding: '0 6px', fontWeight: 600 }}>{fontSize.toFixed(1)}pt</span>
                  <button className="seg-btn" style={{ padding: '0 8px' }} onClick={() => setFontSize((f) => Math.min(16, f + 0.5))}>
                    <Plus size={13} />
                  </button>
                </div>

                {/* Compact Palette Swatch Chips */}
                <div style={{ display: 'flex', gap: 5, alignItems: 'center' }}>
                  {Object.entries(palettes || {}).map(([name, cols]) => (
                    <button
                      key={name}
                      title={name}
                      onClick={() => setPaletteName(name)}
                      style={{
                        display: 'flex',
                        gap: 2,
                        padding: '5px 6px',
                        borderRadius: 7,
                        border: paletteName === name ? '2px solid var(--accent)' : '1px solid var(--border-hairline)',
                        background: 'var(--bg-paper)',
                        cursor: 'pointer',
                      }}
                    >
                      {cols.slice(0, 3).map((c) => (
                        <span key={c} style={{ width: 9, height: 9, borderRadius: 2, background: c }} />
                      ))}
                    </button>
                  ))}
                </div>
              </div>

              {/* Ultra-HD DPI + Export Strip */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap' }}>
                <select className="select mono" style={{ width: 112 }} value={dpi} onChange={(e) => setDpi(Number(e.target.value))}>
                  <option value={600}>600 DPI</option>
                  <option value={1200}>1200 DPI</option>
                  <option value={300}>300 DPI</option>
                </select>
                <button className="btn btn-sm" onClick={() => setShowCode((v) => !v)}>
                  <Code2 size={13.5} /> {showCode ? t.hide_py : 'Python'}
                </button>
                <button className="btn btn-sm" disabled={!svgOut} onClick={() => onSendSvgToPatcher(svgOut)}>
                  <Type size={13.5} /> {t.to_patcher}
                </button>
                <button className="btn btn-sm" disabled={!svgOut} onClick={downloadSvg}>
                  <Download size={13.5} /> SVG
                </button>
                <button className="btn btn-sm" disabled={!pngB64} onClick={() => downloadUri(pngB64, 'image/png', `figure_${chartType}_${dpi}dpi.png`)}>
                  <Download size={13.5} /> {dpi} DPI PNG
                </button>
                <button className="btn btn-primary btn-sm" disabled={!pdfB64} onClick={() => downloadUri(pdfB64, 'application/pdf', `figure_${chartType}.pdf`)}>
                  <Download size={13.5} /> 矢量 PDF
                </button>
              </div>
            </div>

            {/* Smart Chart Type Recommendation Strip */}
            {analysis?.recommendations && (
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                <span className="eyebrow" style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                  <Sparkles size={13.5} color="var(--accent)" /> {lang === 'zh' ? '推荐图型' : 'Charts'}
                </span>
                {analysis.recommendations.map((rec: any) => (
                  <button
                    key={rec.chart_type}
                    onClick={() => setChartType(rec.chart_type)}
                    className={`btn btn-sm ${chartType === rec.chart_type ? 'btn-primary' : ''}`}
                    title={rec.reason}
                  >
                    {rec.title} · {Math.round(rec.confidence * 100)}%
                  </button>
                ))}
              </div>
            )}

            {/* Spacious Live Vector Figure Preview */}
            <div className="card" style={{ padding: '20px 22px', background: '#fff', minHeight: 360, display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
              {rendering && (
                <div style={{ position: 'absolute', top: 14, right: 16, display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--ink-muted)' }}>
                  <Loader2 size={14} className="spin" /> {dpi} DPI…
                </div>
              )}
              {svgOut ? (
                <div className="svg-responsive" style={{ maxWidth: colWidth === 'single' ? 540 : 940, margin: '0 auto' }} dangerouslySetInnerHTML={{ __html: svgOut }} />
              ) : (
                <div style={{ color: 'var(--ink-muted)' }}>…</div>
              )}
            </div>

            {showCode && (
              <div className="card view-fade">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <span className="eyebrow">Python Matplotlib</span>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button className="btn btn-sm" onClick={() => { navigator.clipboard.writeText(pythonCode); onNotify(lang === 'zh' ? '已复制绘图代码' : 'Copied'); }}>
                      <Copy size={13} /> {lang === 'zh' ? '复制' : 'Copy'}
                    </button>
                    <button className="btn btn-primary btn-sm" onClick={() => renderChart(true)}>
                      <Play size={13} /> {t.rerun_code}
                    </button>
                  </div>
                </div>
                <textarea className="textarea mono" rows={15} value={pythonCode} onChange={(e) => setPythonCode(e.target.value)} />
              </div>
            )}
          </>
        ) : (
          <>
            <div className="card" style={{ padding: '20px 24px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
                <div>
                  <div style={{ fontFamily: 'var(--font-serif)', fontSize: 20, fontWeight: 600 }}>{t.table_preview}</div>
                  <div style={{ fontSize: 13, color: 'var(--ink-muted)' }}>{t.table_sub}</div>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button
                    className="btn btn-sm"
                    onClick={() => {
                      if (tableRes?.latex) {
                        navigator.clipboard.writeText(tableRes.latex);
                        onNotify(lang === 'zh' ? '已复制 LaTeX booktabs 三线表' : 'Copied LaTeX');
                      }
                    }}
                  >
                    <Copy size={13.5} /> {t.copy_latex}
                  </button>
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={() =>
                      downloadBlob(
                        '/api/tables/export-docx',
                        { csv_text: csvText, caption: tableCaption, label: tableLabel, lower_is_better: lowerCols, decimals: decimals === '' ? null : Number(decimals) },
                        'academic_table.docx',
                      )
                    }
                  >
                    <FileSpreadsheet size={13.5} /> {t.export_word_tbl}
                  </button>
                </div>
              </div>

              <div style={{ fontFamily: 'var(--font-serif)', fontSize: 14.5, marginBottom: 10, color: 'var(--ink-secondary)' }}>
                <strong>Table 1.</strong> {tableCaption}
              </div>

              {tableRes && (
                <div className="table-scroll">
                  <table className="academic-table">
                    <thead>
                      <tr>
                        {tableRes.headers.map((h: any, i: number) => (
                          <th key={i}>
                            {h.label} {h.direction === 'up' ? '↑' : h.direction === 'down' ? '↓' : ''}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {tableRes.rows.map((r: any[], ri: number) => (
                        <tr key={ri} className={r[0]?.is_ours ? 'ours-row' : ''}>
                          {r.map((cell: any, ci: number) => (
                            <td key={ci} style={{ fontWeight: cell.rank === 'best' || (ci === 0 && cell.is_ours) ? 700 : 400, textDecoration: cell.rank === 'second' ? 'underline' : 'none' }}>
                              {cell.text}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {tableRes?.latex && (
              <div className="card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <span className="eyebrow">LaTeX booktabs</span>
                  <button className="btn btn-sm" onClick={() => { navigator.clipboard.writeText(tableRes.latex); onNotify(lang === 'zh' ? '已复制 LaTeX 源码' : 'Copied'); }}>
                    <Copy size={13} /> {lang === 'zh' ? '复制' : 'Copy'}
                  </button>
                </div>
                <div className="code-block">{tableRes.latex}</div>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
};
