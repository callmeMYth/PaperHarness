import React, { useEffect, useRef, useState } from 'react';
import {
  ArrowLeftRight,
  ArrowUp,
  ArrowUpRight,
  CheckCircle2,
  Copy,
  FileUp,
  ImagePlus,
  KeyRound,
  Loader2,
  PanelLeft,
  Presentation,
  Sparkles,
  Square,
  SquarePen,
  X,
} from 'lucide-react';
import { downloadBlob, streamOmniChat } from '../api';
import { Lang } from '../i18n';
import { DiagramBlueprint, StudioId } from '../types';

export interface ToolRunItem {
  tool: string;
  label?: string;
  summary?: string;
  done: boolean;
  error?: boolean;
  preview_svg?: string;
  preview_png_b64?: string;
  code_snippet?: string;
  blueprint?: DiagramBlueprint;
  target_studio?: StudioId;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  images?: string[];
  tools?: ToolRunItem[];
  needApiKey?: string;
  meta?: string;
}

export interface AgentTodoItem {
  id: string;
  label: string;
  status: 'running' | 'done' | 'error';
  studio?: StudioId;
}

export interface SessionArtifact {
  id: string;
  kind: 'diagram' | 'chart' | 'table' | 'manuscript' | 'patcher' | 'citation';
  title: string;
  studio: StudioId;
  createdAt: string;
  blueprint?: DiagramBlueprint;
  preview_png_b64?: string;
  code_snippet?: string;
}

interface Props {
  lang: Lang;
  sessionId: string;
  sessionTitle: string;
  messages: ChatMessage[];
  isStreaming: boolean;
  runningCount: number;
  sidebarOpen: boolean;
  workspaceOpen: boolean;
  workspaceContext: {
    studio: StudioId;
    title: string;
    venue: string;
    manuscript: string;
    bibtex: string;
    latex_workspace?: { root_dir: string; active_file: string; tex_files: string[]; figures: string[] } | null;
  };
  externalAttachImage?: { id: number; dataUrl: string } | null;
  onMessagesChange: (sessionId: string, updater: (prev: ChatMessage[]) => ChatMessage[]) => void;
  onStreamingChange: (sessionId: string, running: boolean, ctrl?: AbortController) => void;
  onAbortSession: (sessionId: string) => void;
  onToggleSidebar: () => void;
  onToggleWorkspace: () => void;
  onNewChat: () => void;
  onImportDocFile: (file: File) => void;
  onPickImportDoc?: () => void;
  onOpenModelHub: () => void;
  onUiAction: (evt: any, sessionId: string) => void;
  onJumpStudio: (studio: StudioId) => void;
  onTodoUpdate: (sessionId: string, updater: (prev: AgentTodoItem[]) => AgentTodoItem[]) => void;
  onArtifactAdd: (sessionId: string, art: SessionArtifact) => void;
  onNotify: (msg: string) => void;
}

const TOOL_LABELS: Record<string, string> = {
  draw_diagram: '顶刊流程图引擎',
  refine_diagram: '流程图风格与图示微调',
  draw_chart: '智能数据绘图 (600 DPI)',
  build_table: '顶刊三线表',
  edit_manuscript: '论文润色与双步翻译引擎',
  optimize_formulas: '公式排版与符号一致',
  patch_figure_text: '安全改图文字',
  verify_citations: '引用防幻觉核验',
  web_search: '联网学术检索',
  lookup_term: '多模态术语联网查证',
  switch_studio: '切换工作台',
};

function renderRichText(raw: string): React.ReactNode {
  const cleaned = raw.replace(/\n{3,}/g, '\n\n').trim();
  const tokens = cleaned.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return tokens.map((tok, idx) => {
    if (tok.startsWith('**') && tok.endsWith('**') && tok.length > 4) {
      return <strong key={idx}>{tok.slice(2, -2)}</strong>;
    }
    if (tok.startsWith('`') && tok.endsWith('`') && tok.length > 2) {
      return (
        <code key={idx} style={{ fontFamily: 'var(--font-mono)', fontSize: '0.9em', background: 'rgba(30,58,95,0.08)', padding: '1px 5px', borderRadius: 4 }}>
          {tok.slice(1, -1)}
        </code>
      );
    }
    return <React.Fragment key={idx}>{tok}</React.Fragment>;
  });
}

function readImageAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(new Error('图片读取失败'));
    reader.readAsDataURL(file);
  });
}

export const ConversationPane: React.FC<Props> = ({
  lang,
  sessionId,
  sessionTitle,
  messages,
  isStreaming,
  runningCount,
  sidebarOpen,
  workspaceOpen,
  workspaceContext,
  externalAttachImage,
  onMessagesChange,
  onStreamingChange,
  onAbortSession,
  onToggleSidebar,
  onToggleWorkspace,
  onNewChat,
  onImportDocFile,
  onPickImportDoc,
  onOpenModelHub,
  onUiAction,
  onJumpStudio,
  onTodoUpdate,
  onArtifactAdd,
  onNotify,
}) => {
  const [input, setInput] = useState('');
  const [pendingImages, setPendingImages] = useState<string[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [showQuickBar, setShowQuickBar] = useState(true);

  const draftsRef = useRef<Record<string, string>>({});
  const prevSidRef = useRef<string>(sessionId);
  const imgInputRef = useRef<HTMLInputElement>(null);
  const docInputRef = useRef<HTMLInputElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (prevSidRef.current !== sessionId) {
      draftsRef.current[prevSidRef.current] = input;
      setInput(draftsRef.current[sessionId] || '');
      prevSidRef.current = sessionId;
    }
  }, [sessionId]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length, isStreaming, sessionId]);

  useEffect(() => {
    if (!externalAttachImage?.dataUrl) return;
    setPendingImages((prev) => [...prev, externalAttachImage.dataUrl].slice(0, 4));
  }, [externalAttachImage?.id]);

  const attachImages = async (files: FileList | File[]) => {
    const imgs = Array.from(files).filter((f) => f.type.startsWith('image/'));
    if (!imgs.length) return;
    try {
      const urls = await Promise.all(imgs.slice(0, 4).map(readImageAsDataUrl));
      setPendingImages((prev) => [...prev, ...urls].slice(0, 4));
    } catch (e: any) {
      onNotify(e.message);
    }
  };

  const handlePaste = async (e: React.ClipboardEvent) => {
    const items = Array.from(e.clipboardData?.items || []);
    const imgFiles = items.filter((it) => it.type.startsWith('image/')).map((it) => it.getAsFile()).filter(Boolean) as File[];
    if (imgFiles.length) {
      e.preventDefault();
      await attachImages(imgFiles);
    }
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const allFiles = Array.from(e.dataTransfer.files || []);
    const imgs = allFiles.filter((f) => f.type.startsWith('image/'));
    const docs = allFiles.filter((f) => /\.(docx|tex|pdf|md|txt)$/i.test(f.name));
    if (imgs.length) await attachImages(imgs);
    if (docs.length) onImportDocFile(docs[0]);
  };

  const sendMessage = async (overrideText?: string) => {
    const text = (overrideText ?? input).trim();
    const imgs = [...pendingImages];
    if ((!text && imgs.length === 0) || isStreaming) return;

    // Bind every callback strictly to targetSid so switching sessions or launching parallel chats never crosstalks!
    const targetSid = sessionId;
    const ctrl = new AbortController();

    const userMsg: ChatMessage = { id: `u-${Date.now()}`, role: 'user', content: text, images: imgs.length ? imgs : undefined };
    const asstId = `a-${Date.now() + 1}`;
    const asstPlaceholder: ChatMessage = { id: asstId, role: 'assistant', content: '', tools: [] };

    const historyPayload = [...messages, userMsg].map((m) => ({
      role: m.role,
      content: m.content,
      ...(m.images?.length ? { images: m.images } : {}),
    }));

    onMessagesChange(targetSid, (prev) => [...prev, userMsg, asstPlaceholder]);
    draftsRef.current[targetSid] = '';
    setInput('');
    setPendingImages([]);
    onStreamingChange(targetSid, true, ctrl);

    const patchAsst = (updater: (m: ChatMessage) => ChatMessage) =>
      onMessagesChange(targetSid, (prev) => prev.map((m) => (m.id === asstId ? updater(m) : m)));

    try {
      await streamOmniChat(
        { messages: historyPayload, context: workspaceContext },
        (evt) => {
          if (evt.type === 'need_api_key') {
            patchAsst((m) => ({ ...m, needApiKey: evt.message }));
          } else if (evt.type === 'token') {
            patchAsst((m) => ({ ...m, content: m.content + (evt.text || '') }));
          } else if (evt.type === 'tool_start') {
            const todoId = `${asstId}-${evt.tool}`;
            onTodoUpdate(targetSid, (prev) => {
              const exists = prev.find((x) => x.id === todoId);
              if (exists) return prev.map((x) => (x.id === todoId ? { ...x, label: evt.label || x.label, status: 'running' } : x));
              return [...prev, { id: todoId, label: evt.label || TOOL_LABELS[evt.tool] || evt.tool, status: 'running' }];
            });
            patchAsst((m) => {
              const list = [...(m.tools || [])];
              const runningIdx = list.findIndex((x) => x.tool === evt.tool && !x.done);
              if (runningIdx >= 0) {
                list[runningIdx] = { ...list[runningIdx], label: evt.label };
                return { ...m, tools: list };
              }
              return { ...m, tools: [...list, { tool: evt.tool, label: evt.label, done: false }] };
            });
          } else if (evt.type === 'tool_result') {
            const todoId = `${asstId}-${evt.tool}`;
            onTodoUpdate(targetSid, (prev) =>
              prev.map((x) =>
                x.id === todoId ? { ...x, label: evt.summary || x.label, status: evt.error ? 'error' : 'done', studio: evt.target_studio } : x,
              ),
            );
            if (!evt.error && evt.target_studio) {
              const nowStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
              const kindMap: Record<string, SessionArtifact['kind']> = {
                draw_diagram: 'diagram',
                draw_chart: 'chart',
                build_table: 'table',
                edit_manuscript: 'manuscript',
                patch_figure_text: 'patcher',
                verify_citations: 'citation',
              };
              if (kindMap[evt.tool]) {
                onArtifactAdd(targetSid, {
                  id: `art-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
                  kind: kindMap[evt.tool],
                  title: evt.blueprint?.title || TOOL_LABELS[evt.tool] || evt.tool,
                  studio: evt.target_studio,
                  createdAt: nowStr,
                  blueprint: evt.blueprint,
                  preview_png_b64: evt.preview_png_b64,
                  code_snippet: evt.code_snippet,
                });
              }
            }
            patchAsst((m) => {
              const list = [...(m.tools || [])];
              const idx = list.map((x) => x.tool).lastIndexOf(evt.tool);
              const item: ToolRunItem = {
                tool: evt.tool,
                label: idx >= 0 ? list[idx].label : evt.tool,
                summary: evt.summary,
                done: true,
                error: evt.error,
                preview_svg: evt.preview_svg,
                preview_png_b64: evt.preview_png_b64,
                code_snippet: evt.code_snippet,
                blueprint: evt.blueprint,
                target_studio: evt.target_studio,
              };
              if (idx >= 0) list[idx] = item;
              else list.push(item);
              return { ...m, tools: list };
            });
          } else if (evt.type === 'ui_action') {
            onUiAction(evt, targetSid);
          } else if (evt.type === 'error') {
            patchAsst((m) => ({ ...m, content: m.content + (m.content ? '\n\n' : '') + `⚠ ${evt.message}` }));
          } else if (evt.type === 'done') {
            patchAsst((m) => ({ ...m, meta: `${evt.provider} · ${evt.model}` }));
          }
        },
        ctrl.signal,
      );
    } catch (e: any) {
      if (e?.name === 'AbortError') {
        patchAsst((m) => ({
          ...m,
          content: m.content + (m.content ? '\n\n' : '') + (lang === 'zh' ? '（已手动停止当前对话生成）' : '(Stopped by user)'),
        }));
      } else {
        patchAsst((m) => ({ ...m, content: m.content || `⚠ ${e.message}` }));
      }
    } finally {
      onStreamingChange(targetSid, false);
    }
  };

  const quickPrompts =
    pendingImages.length > 0
      ? lang === 'zh'
        ? [
            '把这张图载入「安全改图文字」并帮我定位可编辑文字',
            '读取这张表图数据，画 600 DPI CVPR 柱状图并生成三线表',
            '按这张草图，用多智能体协同画一张可导出 PPT 的流程图',
          ]
        : [
            'Load this image into Figure Patcher to edit text labels',
            'Extract table data from this image and plot a 600 DPI chart',
            'Turn this sketch into a multi-agent editable PPTX flowchart',
          ]
      : lang === 'zh'
        ? [
            '用多智能体协同画一张 CVPR 顶刊流程图并导出 PPT',
            '帮我用对比实验数据画 600 DPI 柱状图与三线表',
            '通读当前论文润色、防过度声称并生成差异修改卡片',
            '整理当前论文公式排版位置并联网核验引用真实性',
          ]
        : [
            'Use collaborative agents to draw a CVPR PPTX flowchart',
            'Plot a 600 DPI benchmark chart and LaTeX three-line table',
            'Polish the active manuscript and propose Accept/Reject diffs',
            'Optimize equation placement and verify citations via Crossref',
          ];

  const isEmpty = messages.length === 0;

  const composerCard = (
    <div className={`composer-card ${dragOver ? 'drag-over' : ''}`}>
      {pendingImages.length > 0 && (
        <div className="omni-thumb-row" style={{ marginBottom: 8 }}>
          {pendingImages.map((src, idx) => (
            <div key={idx} className="omni-thumb">
              <img src={src} alt={`upload-${idx}`} />
              <button className="omni-thumb-rm" onClick={() => setPendingImages((prev) => prev.filter((_, i) => i !== idx))}>
                <X size={11} />
              </button>
            </div>
          ))}
        </div>
      )}

      <textarea
        className="composer-input"
        rows={isEmpty ? 3 : 2}
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onPaste={handlePaste}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
          }
        }}
        placeholder={
          lang === 'zh'
            ? '输入消息、拖入论文/图片，或 Ctrl+V 粘贴截图…（Agent 会自动打开对应工具）'
            : 'Ask anything, drop a paper/image, or paste a screenshot…'
        }
      />

      <div className="composer-actions">
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <input
            ref={imgInputRef}
            type="file"
            accept="image/*"
            multiple
            style={{ display: 'none' }}
            onChange={(e) => {
              if (e.target.files?.length) attachImages(e.target.files);
              e.target.value = '';
            }}
          />
          <input
            ref={docInputRef}
            type="file"
            accept=".docx,.tex,.pdf,.md,.txt"
            style={{ display: 'none' }}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onImportDocFile(f);
              e.target.value = '';
            }}
          />
          <button
            className="circle-tool-btn"
            title={lang === 'zh' ? '发送图片（也支持拖入或 Ctrl+V 粘贴截图）' : 'Attach image (Ctrl+V supported)'}
            onClick={() => imgInputRef.current?.click()}
          >
            <ImagePlus size={15.5} />
          </button>
          <button
            className="circle-tool-btn"
            title={lang === 'zh' ? '导入 Word / LaTeX / PDF 论文' : 'Import Word / LaTeX / PDF'}
            onClick={() => (onPickImportDoc ? onPickImportDoc() : docInputRef.current?.click())}
          >
            <FileUp size={15.5} />
          </button>
          <button
            className={`circle-tool-btn ${showQuickBar && isEmpty ? 'active' : ''}`}
            title={lang === 'zh' ? '显示/隐藏快捷学术指令' : 'Toggle quick prompts'}
            onClick={() => setShowQuickBar((v) => !v)}
          >
            <Sparkles size={15.5} />
          </button>
        </div>

        {isStreaming ? (
          <button
            className="send-circle-btn"
            style={{ background: 'var(--vermilion)' }}
            onClick={() => onAbortSession(sessionId)}
            title={lang === 'zh' ? '停止当前对话（不影响其它后台并发对话）' : 'Stop this chat (other chats keep running)'}
          >
            <Square size={13} fill="currentColor" />
          </button>
        ) : (
          <button
            className="send-circle-btn"
            disabled={!input.trim() && pendingImages.length === 0}
            onClick={() => sendMessage()}
            title={lang === 'zh' ? '发送 (Enter)' : 'Send (Enter)'}
          >
            <ArrowUp size={16} strokeWidth={2.4} />
          </button>
        )}
      </div>
    </div>
  );

  return (
    <section
      className={`conv-pane ${workspaceOpen ? 'split' : 'wide'} ${dragOver ? 'drag-over' : ''}`}
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
    >
      {/* Mrite-style Minimal Conversation Header */}
      <header className="pane-header">
        <button className="icon-flat-btn" onClick={onToggleSidebar} title={sidebarOpen ? '收起历史栏' : '展开历史栏'}>
          <PanelLeft size={16} />
        </button>
        <div className="pane-title" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7 }}>
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{sessionTitle}</span>
          {runningCount > 0 && (
            <span className="badge badge-accent" style={{ fontSize: 10.5, padding: '1px 7px', flexShrink: 0, gap: 4 }}>
              <Loader2 size={10.5} className="spin" />
              {lang === 'zh' ? `${runningCount} 路并发中` : `${runningCount} active`}
            </span>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <button className="icon-flat-btn" onClick={onNewChat} title={lang === 'zh' ? '新建并发对话（可与当前对话同时运行）' : 'New Concurrent Chat'}>
            <SquarePen size={15.5} />
          </button>
          <button
            className={`icon-flat-btn ${workspaceOpen ? 'active' : ''}`}
            onClick={onToggleWorkspace}
            title={workspaceOpen ? '收起右侧工作台' : '展开右侧工作台'}
          >
            <ArrowLeftRight size={15.5} />
          </button>
        </div>
      </header>

      {isEmpty ? (
        /* Mrite-inspired Centered Editorial Hero + Floating Rounded Composer */
        <div className="conv-hero view-fade">
          <div className="hero-watermark" aria-hidden="true">
            PaperHarness
          </div>
          <div className="conv-hero-inner">
            <h1 className="hero-greeting">
              {lang === 'zh' ? '今天想要和 PaperHarness 一起做什么？' : 'What would you like to work on today?'}
            </h1>
            {composerCard}
            {showQuickBar && (
              <div className="hero-chips">
                {quickPrompts.map((p) => (
                  <button key={p} className="hero-chip" onClick={() => sendMessage(p)}>
                    <Sparkles size={13} color="var(--accent)" style={{ flexShrink: 0 }} />
                    <span>{p}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      ) : (
        <>
          <div className="conv-stream">
            {messages.map((m) => (
              <div key={m.id} style={{ display: 'flex', flexDirection: 'column', gap: 7, alignItems: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
                {m.images && m.images.length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, justifyContent: 'flex-end', maxWidth: '90%' }}>
                    {m.images.map((src, idx) => (
                      <img
                        key={idx}
                        src={src}
                        alt="attached"
                        style={{ maxWidth: 168, maxHeight: 124, borderRadius: 10, border: '1px solid var(--border-strong)', objectFit: 'cover' }}
                      />
                    ))}
                  </div>
                )}

                {m.needApiKey && (
                  <div className="card view-fade" style={{ width: '100%', padding: '12px 14px', background: 'var(--amber-soft)', borderColor: 'var(--amber)' }}>
                    <div style={{ fontSize: 13, lineHeight: 1.55, marginBottom: 9 }}>{m.needApiKey}</div>
                    <button className="btn btn-primary btn-sm" onClick={onOpenModelHub}>
                      <KeyRound size={13.5} /> {lang === 'zh' ? '立即配置 API Key' : 'Configure API Key'}
                    </button>
                  </div>
                )}

                {(m.content.trim() || (m.role === 'assistant' && isStreaming && !m.needApiKey && !(m.tools && m.tools.length))) && (
                  <div className={`omni-bubble ${m.role}`}>
                    {m.content.trim() ? (
                      renderRichText(m.content)
                    ) : (
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--ink-muted)' }}>
                        <Loader2 size={13.5} className="spin" /> {lang === 'zh' ? '正在规划并按需调用工作台工具…' : 'Planning tools…'}
                      </span>
                    )}
                  </div>
                )}

                {m.tools &&
                  m.tools.map((tr, i) => (
                    <div key={`${tr.tool}-${i}`} className="card view-fade" style={{ width: '100%', padding: '11px 13px', display: 'flex', flexDirection: 'column', gap: 8 }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12.8, fontWeight: 600, color: tr.error ? 'var(--vermilion)' : 'var(--accent)' }}>
                          {tr.done ? <CheckCircle2 size={14} color={tr.error ? 'var(--vermilion)' : 'var(--sage)'} /> : <Loader2 size={14} className="spin" />}
                          {TOOL_LABELS[tr.tool] || tr.tool}
                        </span>
                        {tr.target_studio && tr.done && (
                          <button className="btn btn-ghost btn-sm" style={{ height: 24, padding: '0 7px', fontSize: 11.5 }} onClick={() => onJumpStudio(tr.target_studio!)}>
                            {lang === 'zh' ? '右侧展开' : 'Open'} <ArrowUpRight size={12.5} />
                          </button>
                        )}
                      </div>

                      <div style={{ fontSize: 12.4, color: 'var(--ink-secondary)', lineHeight: 1.5 }}>{tr.summary || tr.label}</div>

                      {tr.preview_svg && (
                        <div style={{ background: '#fff', border: '1px solid var(--border-hairline)', borderRadius: 8, padding: 8 }}>
                          <div className="svg-responsive" dangerouslySetInnerHTML={{ __html: tr.preview_svg }} />
                          {tr.blueprint && (
                            <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
                              <button className="btn btn-sm" style={{ flex: 1 }} onClick={() => onJumpStudio('diagrams')}>
                                {lang === 'zh' ? '在右侧拖动精调' : 'Edit on Right'}
                              </button>
                              <button
                                className="btn btn-primary btn-sm"
                                style={{ flex: 1 }}
                                onClick={() => downloadBlob('/api/diagrams/export-pptx', { blueprint: tr.blueprint }, 'paper_architecture.pptx')}
                              >
                                <Presentation size={13} /> {lang === 'zh' ? '1:1 导出 .pptx' : 'Export .pptx'}
                              </button>
                            </div>
                          )}
                        </div>
                      )}

                      {tr.preview_png_b64 && (
                        <div style={{ background: '#fff', border: '1px solid var(--border-hairline)', borderRadius: 8, padding: 6 }}>
                          <img src={`data:image/png;base64,${tr.preview_png_b64}`} alt="Chart preview" style={{ width: '100%', height: 'auto', borderRadius: 5, display: 'block' }} />
                        </div>
                      )}

                      {tr.code_snippet && (
                        <div>
                          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 4 }}>
                            <button
                              className="btn btn-sm"
                              style={{ height: 24, fontSize: 11.5 }}
                              onClick={() => {
                                navigator.clipboard.writeText(tr.code_snippet || '');
                                onNotify(lang === 'zh' ? '已复制 LaTeX 三线表源码' : 'Copied LaTeX');
                              }}
                            >
                              <Copy size={12} /> {lang === 'zh' ? '复制 LaTeX' : 'Copy LaTeX'}
                            </button>
                          </div>
                          <div className="code-block" style={{ maxHeight: 140, fontSize: 11 }}>{tr.code_snippet}</div>
                        </div>
                      )}
                    </div>
                  ))}

                {m.meta && <div style={{ fontSize: 11, color: 'var(--ink-muted)', paddingLeft: 4 }}>{m.meta}</div>}
              </div>
            ))}
            <div ref={endRef} />
          </div>

          <div className="conv-dock">{composerCard}</div>
        </>
      )}
    </section>
  );
};
