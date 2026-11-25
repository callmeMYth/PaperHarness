import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowDown,
  ArrowUp,
  BookOpen,
  Check,
  CheckCheck,
  CheckCircle2,
  Eye,
  FileCode2,
  FileUp,
  Globe,
  Hash,
  Loader2,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Search,
  Sigma,
  Sparkles,
  Wand2,
  X,
} from 'lucide-react';
import { api } from '../api';
import { I18nDict, Lang } from '../i18n';
import { EditCard, FormulaBlock, FormulaRecommendation, OutlineItem } from '../types';
import { MathTex, TypesetParagraph } from './MathTex';

export interface ExternalManuscriptAction {
  id: number;
  center_view?: 'source' | 'preview' | 'formula';
  edits?: EditCard[];
  stream_text?: string;
}

interface Props {
  lang: Lang;
  t: I18nDict;
  title: string;
  content: string;
  originalContent: string;
  venue: string;
  externalAction?: ExternalManuscriptAction | null;
  hasWorkspace?: boolean;
  onPatchWorkspaceFigure?: (ref: string) => void;
  onContentChange: (c: string) => void;
  onVenueChange: (v: string) => void;
  onImportLoaded: (doc: { title: string; content: string; source_type: string; preamble?: string }) => void;
  onNotify: (msg: string) => void;
}

type CenterView = 'source' | 'preview' | 'formula';
type LeftTab = 'outline' | 'glossary' | 'corpus';

export const ManuscriptStudio: React.FC<Props> = ({
  lang,
  t,
  title,
  content,
  originalContent,
  venue,
  externalAction,
  hasWorkspace,
  onPatchWorkspaceFigure,
  onContentChange,
  onVenueChange,
  onImportLoaded,
  onNotify,
}) => {
  const [centerView, setCenterView] = useState<CenterView>('source');
  const [leftTab, setLeftTab] = useState<LeftTab>('outline');
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [agentOpen, setAgentOpen] = useState(false);

  const [outline, setOutline] = useState<OutlineItem[]>([]);
  const [glossary, setGlossary] = useState<any>(null);
  const [corpusQuery, setCorpusQuery] = useState('token pruning high-resolution vision language');
  const [corpusRes, setCorpusRes] = useState<any>(null);

  const [arxivId, setArxivId] = useState('');
  const [importing, setImporting] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const [formulaBlocks, setFormulaBlocks] = useState<FormulaBlock[]>([]);
  const [formulaRecs, setFormulaRecs] = useState<FormulaRecommendation[]>([]);
  const [symbolConflicts, setSymbolConflicts] = useState<any[]>([]);
  const [editingEqId, setEditingEqId] = useState<string | null>(null);

  const [streamText, setStreamText] = useState('');
  const [editCards, setEditCards] = useState<EditCard[]>([]);

  const docStats = useMemo(() => {
    const words = content.trim() ? content.trim().split(/\s+/).length : 0;
    const paras = content.trim() ? content.trim().split(/\n\s*\n/).filter(Boolean).length : 0;
    return { words, paras };
  }, [content]);

  useEffect(() => {
    if (!externalAction) return;
    if (externalAction.center_view) setCenterView(externalAction.center_view);
    if (externalAction.edits) {
      setEditCards(externalAction.edits);
      if (externalAction.edits.length > 0) setAgentOpen(true);
    }
    if (externalAction.stream_text) {
      setStreamText(externalAction.stream_text);
      setAgentOpen(true);
    }
  }, [externalAction?.id]);

  // Lightweight structure outline only (zero premature diagnosis!)
  const initialLoadedRef = useRef(false);
  useEffect(() => {
    if (!content.trim()) return;
    const run = () => api.outline(content).then((o) => { setOutline(o.outline || []); initialLoadedRef.current = true; }).catch(() => {});
    if (!initialLoadedRef.current) { run(); return; }
    const timer = setTimeout(run, 300);
    return () => clearTimeout(timer);
  }, [content]);

  useEffect(() => {
    if (leftTab === 'glossary' && content.trim()) api.glossary(content).then(setGlossary).catch(() => {});
    if (leftTab === 'corpus' && !corpusRes) api.corpus(corpusQuery, undefined, 5).then(setCorpusRes).catch(() => {});
  }, [leftTab, content]);

  useEffect(() => {
    if (centerView === 'formula' || centerView === 'preview') {
      api
        .formulaAnalyze(content)
        .then((res) => {
          setFormulaBlocks(res.blocks || []);
          setFormulaRecs(res.recommendations || []);
          setSymbolConflicts(res.symbol_conflicts || []);
        })
        .catch(() => {});
    }
  }, [centerView, content]);

  const handleFileImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    try {
      const doc = await api.importFile(file);
      onImportLoaded(doc);
      onNotify(lang === 'zh' ? `已导入 ${doc.filename}` : `Imported ${doc.filename}`);
    } catch (err: any) {
      onNotify(err.message);
    } finally {
      setImporting(false);
      e.target.value = '';
    }
  };

  const handleArxivImport = async () => {
    if (!arxivId.trim()) return;
    setImporting(true);
    try {
      const doc = await api.importArxiv(arxivId.trim());
      onImportLoaded(doc);
      setArxivId('');
      onNotify(lang === 'zh' ? `已拉取 arXiv 论文：${doc.title.slice(0, 42)}` : `Imported arXiv: ${doc.title.slice(0, 42)}`);
    } catch (err: any) {
      onNotify(err.message);
    } finally {
      setImporting(false);
    }
  };

  const handleCleanTypography = async () => {
    try {
      const res = await api.typography(content, 'auto', false);
      if (res.changed) {
        onContentChange(res.cleaned);
        onNotify(lang === 'zh' ? `标点与空格已规范化：${res.changes[0]}` : `Cleaned: ${res.changes[0]}`);
      } else {
        onNotify(lang === 'zh' ? '当前标点与空格已符合学术规范' : 'Typography is already clean');
      }
    } catch (err: any) {
      onNotify(err.message);
    }
  };

  const applyEditCard = (card: EditCard) => {
    if (card.status === 'accepted') return;
    if (!content.includes(card.original)) {
      onNotify(lang === 'zh' ? '原句已被手动改动，无法定位替换区间' : 'Original sentence was already modified');
      return;
    }
    onContentChange(content.replace(card.original, card.revised));
    setEditCards((prev) => prev.map((c) => (c.id === card.id ? { ...c, status: 'accepted' } : c)));
    api.recordFeedback({ original: card.original, revised: card.revised, tag: card.tag, reason: card.reason, decision: 'accepted', venue, mode: 'chat' });
    onNotify(lang === 'zh' ? `已采纳 [${card.tag}] 修改` : `Applied [${card.tag}] edit`);
  };

  const rejectEditCard = (card: EditCard) => {
    setEditCards((prev) => prev.map((c) => (c.id === card.id ? { ...c, status: 'rejected' } : c)));
    api.recordFeedback({ original: card.original, revised: card.revised, tag: card.tag, reason: card.reason, decision: 'rejected', venue, mode: 'chat' });
  };

  const acceptAllEdits = () => {
    let next = content;
    let applied = 0;
    const updated = editCards.map((c) => {
      if (c.status === 'pending' && next.includes(c.original)) {
        next = next.replace(c.original, c.revised);
        applied += 1;
        api.recordFeedback({ original: c.original, revised: c.revised, tag: c.tag, reason: c.reason, decision: 'accepted', venue, mode: 'chat' });
        return { ...c, status: 'accepted' as const };
      }
      return c;
    });
    if (applied > 0) {
      onContentChange(next);
      setEditCards(updated);
      onNotify(lang === 'zh' ? `已批量采纳 ${applied} 处修改，可直接导出 Word 修订版` : `Accepted ${applied} edits`);
    }
  };

  const moveBlock = (index: number, delta: number) => {
    const target = index + delta;
    if (target < 0 || target >= formulaBlocks.length) return;
    const copy = [...formulaBlocks];
    const [item] = copy.splice(index, 1);
    copy.splice(target, 0, item);
    setFormulaBlocks(copy);
  };

  const insertRecommendedEquation = (rec: FormulaRecommendation) => {
    const newEq: FormulaBlock = {
      id: `eq-rec-${Date.now()}`,
      kind: 'equation',
      display: rec.recommended_mode === 'display',
      number: formulaBlocks.filter((b) => b.kind === 'equation').length + 1,
      label: rec.suggested_label,
      latex: rec.suggested_latex,
    };
    const copy = [...formulaBlocks];
    copy.splice(rec.after_block_index + 1, 0, newEq);
    setFormulaBlocks(copy);
    setFormulaRecs((prev) => prev.filter((r) => r.id !== rec.id));
    onNotify(lang === 'zh' ? '已插入推荐公式，可自由上下调整位置后点「应用排版并同步引用」' : 'Inserted recommended equation');
  };

  const commitFormulaLayout = async () => {
    const res = await api.formulaRebuild(formulaBlocks, true);
    onContentChange(res.content);
    onNotify(lang === 'zh' ? `已同步 ${res.equation_count} 个公式及 ${res.synced_references} 处上下文引用编号` : `Synced ${res.equation_count} equations`);
  };

  const acceptedCount = editCards.filter((c) => c.status === 'accepted').length;
  const changedFromOriginal = content !== originalContent;

  return (
    <div className="studio-body">
      {drawerOpen && (
        <aside className="left-drawer view-fade">
          <div style={{ padding: '10px 10px 8px', borderBottom: '1px solid var(--border-hairline)' }}>
            <div className="segmented" style={{ width: '100%' }}>
              {(
                [
                  ['outline', t.tab_outline],
                  ['glossary', t.tab_glossary],
                  ['corpus', t.tab_corpus],
                ] as const
              ).map(([k, lbl]) => (
                <button
                  key={k}
                  className={`seg-btn ${leftTab === k ? 'active' : ''}`}
                  style={{ flex: 1, justifyContent: 'center', padding: '0 4px', fontSize: 12 }}
                  onClick={() => setLeftTab(k)}
                >
                  {lbl}
                </button>
              ))}
            </div>
          </div>

          <div className="panel-scroll" style={{ padding: 11 }}>
            {leftTab === 'outline' && (
              <div className="view-fade" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                  <span className="eyebrow">{t.import_title}</span>
                  <input ref={fileRef} type="file" accept=".docx,.tex,.md,.txt,.pdf" style={{ display: 'none' }} onChange={handleFileImport} />
                  <button className="btn" style={{ width: '100%' }} onClick={() => fileRef.current?.click()} disabled={importing}>
                    {importing ? <Loader2 size={14} className="spin" /> : <FileUp size={14} />}
                    {t.open_file}
                  </button>
                  <div style={{ display: 'flex', gap: 5 }}>
                    <input
                      className="input mono"
                      style={{ fontSize: 12, padding: '6px 8px' }}
                      value={arxivId}
                      onChange={(e) => setArxivId(e.target.value)}
                      placeholder={t.arxiv_ph}
                      onKeyDown={(e) => e.key === 'Enter' && handleArxivImport()}
                    />
                    <button className="btn btn-sm" style={{ height: 36 }} onClick={handleArxivImport} disabled={importing}>
                      <Globe size={14} />
                    </button>
                  </div>
                </div>

                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <span className="eyebrow">{t.doc_outline}</span>
                    <span style={{ fontSize: 11.5, color: 'var(--ink-muted)' }}>
                      {outline.length} {t.nodes}
                    </span>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                    {outline.map((item, i) => (
                      <button
                        key={i}
                        className="outline-item"
                        style={{ paddingLeft: 8 + (item.level - 1) * 12 }}
                        onClick={() => setCenterView(item.kind === 'equation' ? 'formula' : 'preview')}
                      >
                        {item.kind === 'equation' ? <Sigma size={13} color="var(--violet)" /> : <Hash size={13} color="var(--accent)" />}
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.title}</span>
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <label className="field-label">{t.target_venue}</label>
                  <select className="select" value={venue} onChange={(e) => onVenueChange(e.target.value)}>
                    <option>CVPR / ICCV</option>
                    <option>NeurIPS / ICML</option>
                    <option>ACL / EMNLP</option>
                    <option>IEEE TPAMI</option>
                    <option>Nature / Science</option>
                    <option>中文核心期刊 / 学位论文</option>
                  </select>
                </div>
              </div>
            )}

            {leftTab === 'glossary' && (
              <div className="view-fade" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                <span className="eyebrow">
                  {t.locked_acr} ({glossary?.acronyms?.length || 0})
                </span>
                {(glossary?.acronyms || []).map((a: any) => (
                  <div key={a.acr} className="card" style={{ padding: '8px 10px' }}>
                    <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}>{a.acr}</div>
                    <div style={{ fontSize: 12, color: 'var(--ink-secondary)' }}>{a.full}</div>
                  </div>
                ))}
                <span className="eyebrow" style={{ marginTop: 4 }}>
                  {t.matched_terms} ({glossary?.terms?.length || 0})
                </span>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                  {(glossary?.terms || []).slice(0, 18).map((tm: any) => (
                    <span key={tm.en} className="badge badge-neutral">
                      {tm.en} · {tm.zh}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {leftTab === 'corpus' && (
              <div className="view-fade" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <span className="eyebrow">{t.corpus_search}</span>
                <div style={{ display: 'flex', gap: 5 }}>
                  <input
                    className="input"
                    value={corpusQuery}
                    onChange={(e) => setCorpusQuery(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && api.corpus(corpusQuery, undefined, 5).then(setCorpusRes)}
                    placeholder={t.corpus_ph}
                  />
                  <button className="btn btn-sm" style={{ height: 36 }} onClick={() => api.corpus(corpusQuery, undefined, 5).then(setCorpusRes)}>
                    <Search size={14} />
                  </button>
                </div>
                {corpusRes && (
                  <div style={{ fontSize: 11.5, color: 'var(--ink-muted)' }}>
                    {corpusRes.corpus_size?.toLocaleString()} 句 · {corpusRes.active_packs || 1} 个语料包
                  </div>
                )}
                {(corpusRes?.results || []).map((r: any, idx: number) => (
                  <div key={idx} className="card" style={{ padding: '10px 11px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 4, marginBottom: 4 }}>
                      <span className="badge badge-accent">
                        {r.venue} {r.year}
                      </span>
                      <span style={{ fontSize: 11, color: 'var(--ink-muted)' }}>{r.pack_name || r.section}</span>
                    </div>
                    <div style={{ fontFamily: 'var(--font-serif)', fontSize: 13.5, lineHeight: 1.55 }}>“{r.text}”</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </aside>
      )}

      {/* CENTER STAGE */}
      <section className="center-stage">
        <div className="stage-toolbar">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <button className="btn btn-ghost btn-sm" style={{ padding: '0 6px' }} onClick={() => setDrawerOpen((v) => !v)}>
              {drawerOpen ? <PanelLeftClose size={16} /> : <PanelLeftOpen size={16} />}
            </button>
            <div className="segmented">
              {(
                [
                  ['source', t.view_source, FileCode2],
                  ['preview', t.view_preview, Eye],
                  ['formula', t.view_formula, Sigma],
                ] as const
              ).map(([k, lbl, Icon]) => (
                <button key={k} className={`seg-btn ${centerView === k ? 'active' : ''}`} onClick={() => setCenterView(k)}>
                  <Icon size={13.5} /> {lbl}
                </button>
              ))}
            </div>
          </div>

          <div className="audit-hud">
            <span className="badge badge-neutral">
              {docStats.paras} {lang === 'zh' ? '段' : 'paras'} · {docStats.words} {lang === 'zh' ? '词' : 'words'}
            </span>
            <button className="btn btn-sm" onClick={handleCleanTypography}>
              <Wand2 size={13} /> {t.clean_typo}
            </button>
            <button className={`btn btn-sm ${agentOpen ? 'btn-primary' : ''}`} onClick={() => setAgentOpen((v) => !v)}>
              <Sparkles size={13} /> {lang === 'zh' ? `润色卡片${editCards.length ? ` (${editCards.length})` : ''}` : `Edits${editCards.length ? ` (${editCards.length})` : ''}`}
            </button>
          </div>
        </div>

        <div className="paper-scroll">
          <div key={centerView} className="paper-sheet view-fade">
            {centerView === 'source' && (
              <>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginBottom: 14 }}>
                  <div style={{ fontFamily: 'var(--font-serif)', fontSize: 23, fontWeight: 600, lineHeight: 1.3 }}>{title}</div>
                  {changedFromOriginal && <span className="badge badge-sage">{t.track_active}</span>}
                </div>
                <textarea className="manuscript-editor" value={content} onChange={(e) => onContentChange(e.target.value)} spellCheck={false} rows={32} />
              </>
            )}

            {centerView === 'preview' && (
              <div className="typeset-prose">
                <div style={{ textAlign: 'center', marginBottom: 24 }}>
                  <div style={{ fontSize: 12, fontFamily: 'var(--font-sans)', textTransform: 'uppercase', letterSpacing: '0.09em', color: 'var(--ink-muted)', marginBottom: 6 }}>
                    {venue} · {t.view_preview}
                  </div>
                  <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: 25, fontWeight: 600, margin: 0, lineHeight: 1.3 }}>{title}</h1>
                </div>
                {formulaBlocks.map((blk) => {
                  if (blk.kind === 'heading') {
                    const cleanHead = (blk.text || '').replace(/^\\(?:sub)*section\*?\{([^}]+)\}/, '$1').replace(/^#{1,4}\s+/, '');
                    return <h2 key={blk.id}>{cleanHead}</h2>;
                  }
                  if (blk.kind === 'equation') {
                    return (
                      <div key={blk.id} className="equation-box">
                        <div style={{ flex: 1, textAlign: 'center' }}>
                          <MathTex tex={blk.latex || ''} display={true} />
                        </div>
                        <span className="equation-num">({blk.number})</span>
                      </div>
                    );
                  }
                  return <TypesetParagraph key={blk.id} text={blk.text || ''} hasWorkspace={hasWorkspace} onPatchWorkspaceFigure={onPatchWorkspaceFigure} />;
                })}
              </div>
            )}

            {centerView === 'formula' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
                  <div>
                    <h2 style={{ margin: 0, fontFamily: 'var(--font-serif)', fontSize: 21 }}>{t.formula_title}</h2>
                    <div style={{ fontSize: 13, color: 'var(--ink-secondary)', marginTop: 2 }}>{t.formula_sub}</div>
                  </div>
                  <button className="btn btn-primary" onClick={commitFormulaLayout}>
                    <CheckCircle2 size={14} /> {t.sync_refs}
                  </button>
                </div>

                {symbolConflicts.length > 0 && (
                  <div className="card" style={{ background: 'var(--amber-soft)', borderColor: 'var(--amber-border)', padding: '10px 14px' }}>
                    <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--amber)', marginBottom: 4 }}>
                      {t.symbol_audit} ({symbolConflicts.length})
                    </div>
                    {symbolConflicts.map((sc, i) => (
                      <div key={i} style={{ fontSize: 13 }}>
                        • <code>{sc.variants.join(' vs ')}</code> — {sc.suggestion}
                      </div>
                    ))}
                  </div>
                )}

                {(() => {
                  let eqSeq = 0;
                  return formulaBlocks.map((blk, idx) => {
                    const recAfter = formulaRecs.find((r) => r.after_block_index === idx);
                    const curEqNum = blk.kind === 'equation' ? ++eqSeq : 0;
                    return (
                      <React.Fragment key={blk.id}>
                        {blk.kind === 'equation' ? (
                          <div className="formula-card">
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8, marginBottom: 10 }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                                <span className="badge badge-accent">
                                  Eq. ({curEqNum}) · {blk.display ? t.to_display : t.to_inline}
                                </span>
                                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink-muted)' }}>
                                  \label&#123;{blk.label}&#125;
                                </span>
                              </div>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 5, flexWrap: 'wrap' }}>
                                <button className="btn btn-sm" onClick={() => moveBlock(idx, -1)}>
                                  <ArrowUp size={13} /> {t.move_up}
                                </button>
                                <button className="btn btn-sm" onClick={() => moveBlock(idx, 1)}>
                                  <ArrowDown size={13} /> {t.move_down}
                                </button>
                                <button
                                  className="btn btn-sm"
                                  onClick={() => setFormulaBlocks((prev) => prev.map((b) => (b.id === blk.id ? { ...b, display: !b.display } : b)))}
                                >
                                  {blk.display ? t.to_inline : t.to_display}
                                </button>
                                <button className="btn btn-sm" onClick={() => setEditingEqId(editingEqId === blk.id ? null : blk.id)}>
                                  {editingEqId === blk.id ? t.done : t.edit_tex}
                                </button>
                              </div>
                            </div>

                            <div style={{ textAlign: 'center', padding: '10px 8px', background: 'var(--bg-subtle)', borderRadius: 7, overflowX: 'auto' }}>
                              <MathTex tex={blk.latex || ''} display={true} />
                            </div>

                            {editingEqId === blk.id && (
                              <textarea
                                className="textarea mono"
                                rows={3}
                                style={{ marginTop: 8 }}
                                value={blk.latex || ''}
                                onChange={(e) => setFormulaBlocks((prev) => prev.map((x) => (x.id === blk.id ? { ...x, latex: e.target.value } : x)))}
                              />
                            )}
                          </div>
                        ) : blk.kind === 'heading' ? (
                          <div style={{ fontFamily: 'var(--font-serif)', fontSize: 18, fontWeight: 600, color: 'var(--accent)', marginTop: 8 }}>
                            {(blk.text || '').replace(/^\\(?:sub)*section\*?\{([^}]+)\}/, '$1').replace(/^#+\s+/, '')}
                          </div>
                        ) : (
                          <div style={{ padding: '10px 14px', borderRadius: 8, border: '1px solid var(--border-hairline)', background: 'var(--bg-subtle)', fontFamily: 'var(--font-serif)', fontSize: 15, lineHeight: 1.7, color: 'var(--ink-secondary)' }}>
                            <TypesetParagraph text={blk.text || ''} />
                          </div>
                        )}

                        {recAfter && (
                          <div className="formula-anchor">
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                                <Sparkles size={14} color="var(--accent)" />
                                <strong style={{ fontSize: 13, color: 'var(--accent)' }}>{t.rec_anchor}</strong>
                              </div>
                              <button className="btn btn-primary btn-sm" onClick={() => insertRecommendedEquation(recAfter)}>
                                <Plus size={13} /> {t.insert_here}
                              </button>
                            </div>
                            <div style={{ fontSize: 12.5, color: 'var(--ink-secondary)' }}>{recAfter.rationale}</div>
                            <div style={{ background: 'var(--bg-paper)', padding: '6px 10px', borderRadius: 6, border: '1px solid var(--accent-border)', textAlign: 'center', overflowX: 'auto' }}>
                              <MathTex tex={recAfter.suggested_latex} display={false} />
                            </div>
                          </div>
                        )}
                      </React.Fragment>
                    );
                  });
                })()}
              </div>
            )}
          </div>
        </div>
      </section>

      {/* RIGHT DIFF ACCEPT/REJECT CARDS PANEL (fed directly by the primary left ConversationPane) */}
      {agentOpen && <aside className="right-panel">
        <div className="panel-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
            <Sparkles size={16} color="var(--accent)" />
            <span style={{ fontWeight: 600, fontSize: 14 }}>{lang === 'zh' ? '逐句修改与译文卡片' : 'Proposed Edits'}</span>
          </div>
          <button className="icon-flat-btn" onClick={() => setAgentOpen(false)} title={lang === 'zh' ? '收起' : 'Close'}>
            <X size={14} />
          </button>
        </div>

        <div className="panel-scroll">
          {!streamText && editCards.length === 0 && (
            <div style={{ textAlign: 'center', padding: '42px 18px', color: 'var(--ink-muted)' }}>
              <BookOpen size={28} style={{ opacity: 0.45, marginBottom: 10 }} />
              <div style={{ fontFamily: 'var(--font-serif)', fontSize: 17, color: 'var(--ink-primary)', marginBottom: 6 }}>{lang === 'zh' ? '在左侧对话框直接提需求' : 'Chat on the left to review edits'}</div>
              <div style={{ fontSize: 13, lineHeight: 1.7 }}>
                {lang === 'zh'
                  ? '直接对左侧智能体说「按 CVPR 风格润色引言」「翻译成地道中文（保留专有名词）」或「按审稿人视角批注」，生成的逐句接受/拒绝 Diff 卡片会自动显示在这里。'
                  : 'Ask the left Conversation Agent to polish, translate, or review this paper. Interactive Accept/Reject diff cards will appear here.'}
              </div>
            </div>
          )}

          {editCards.length > 0 && (
            <div style={{ marginBottom: 14 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                <span className="eyebrow">
                  {t.proposed_edits} ({acceptedCount}/{editCards.length})
                </span>
                <button className="btn btn-sage btn-sm" onClick={acceptAllEdits}>
                  <CheckCheck size={13.5} /> {t.accept_all}
                </button>
              </div>
              {editCards.map((card) => (
                <div key={card.id} className={`edit-card ${card.status}`}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                    <span className="badge badge-accent">{card.tag}</span>
                    <div style={{ display: 'flex', gap: 5 }}>
                      {card.status === 'pending' ? (
                        <>
                          <button className="btn btn-sage btn-sm" onClick={() => applyEditCard(card)}>
                            <Check size={12.5} /> {t.accept}
                          </button>
                          <button className="btn btn-ghost btn-sm" onClick={() => rejectEditCard(card)}>
                            <X size={12.5} />
                          </button>
                        </>
                      ) : (
                        <span className={`badge ${card.status === 'accepted' ? 'badge-sage' : 'badge-neutral'}`}>
                          {card.status === 'accepted' ? t.applied : t.dismissed}
                        </span>
                      )}
                    </div>
                  </div>
                  <span className="diff-del">{card.original}</span>
                  <span className="diff-ins">{card.revised}</span>
                  <div style={{ fontSize: 12, color: 'var(--ink-secondary)', marginTop: 6 }}>{card.reason}</div>
                </div>
              ))}
            </div>
          )}

          {streamText && (
            <div className="card view-fade" style={{ padding: '12px 14px', fontSize: 13, lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
              {streamText.replace(/```json_edits[\s\S]*?```/g, '').trim()}
            </div>
          )}
        </div>
      </aside>}
    </div>
  );
};
