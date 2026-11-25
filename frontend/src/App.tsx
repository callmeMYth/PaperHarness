import React, { useEffect, useRef, useState } from 'react';
import {
  Archive,
  BarChart3,
  BookMarked,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  FileCode2,
  FileText,
  FileUp,
  FolderInput,
  FolderOpen,
  Home,
  ImagePlus,
  Loader2,
  Maximize2,
  Minus,
  Moon,
  Network,
  PanelRight,
  Presentation,
  Save,
  Settings,
  SquarePen,
  Sun,
  Trash2,
  Type,
  X,
} from 'lucide-react';
import { api, downloadBlob } from './api';
import { CitationStudio } from './components/CitationStudio';
import {
  AgentTodoItem,
  ChatMessage,
  ConversationPane,
  SessionArtifact,
} from './components/ConversationPane';
import { DataTableStudio, ExternalChartPayload } from './components/DataTableStudio';
import { DiagramRefinementPayload, DiagramStudio } from './components/DiagramStudio';
import { FigurePatcherStudio, IncomingRasterPayload } from './components/FigurePatcherStudio';
import { ExternalManuscriptAction, ManuscriptStudio } from './components/ManuscriptStudio';
import { ModelHubModal, TabKey } from './components/ModelHubModal';
import { Lang, T } from './i18n';
import { DiagramBlueprint, SettingsPayload, StudioId } from './types';

declare global {
  interface Window {
    pywebview?: {
      api?: {
        is_desktop?: () => Promise<boolean>;
        get_default_dirs?: () => Promise<{ app_dir: string; exports_dir: string; last_dir: string }>;
        save_file_b64?: (filename: string, data_b64: string) => Promise<{ ok: boolean; cancelled?: boolean; path?: string; filename?: string }>;
        pick_workspace_folder?: () => Promise<{ ok: boolean; cancelled?: boolean; path?: string; name?: string }>;
        pick_import_file?: () => Promise<{ ok: boolean; cancelled?: boolean; path?: string; filename?: string; b64?: string }>;
        open_file_location?: (path: string) => Promise<{ ok: boolean }>;
        minimize?: () => Promise<void>;
        toggle_maximize?: () => Promise<boolean>;
        close?: () => Promise<void>;
      };
    };
  }
}

interface ChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
  updatedAt: number;
}

interface TexWorkspaceState {
  root_dir: string;
  project_name: string;
  main_tex: string;
  active_file: string;
  tex_files: Array<{ rel: string; name: string; size_kb: number; is_entry: boolean }>;
  bib_files: Array<{ rel: string; name: string; size_kb: number }>;
  figures: Array<{ rel: string; name: string; ext: string; size_kb: number }>;
  data_files: Array<{ rel: string; name: string; size_kb: number }>;
}

/** Recursively collect files from a dropped FileSystemDirectoryEntry (browser/WebView2 folder drop). */
async function collectEntryFiles(entry: any, prefix = ''): Promise<Array<{ file: File; rel: string }>> {
  if (entry.isFile) {
    const file: File = await new Promise((resolve, reject) => entry.file(resolve, reject));
    return [{ file, rel: prefix ? `${prefix}/${entry.name}` : entry.name }];
  }
  if (entry.isDirectory) {
    const reader = entry.createReader();
    const allChildren: any[] = [];
    while (true) {
      const batch: any[] = await new Promise((resolve, reject) => reader.readEntries(resolve, reject));
      if (!batch.length) break;
      allChildren.push(...batch);
    }
    const out: Array<{ file: File; rel: string }> = [];
    const nextPref = prefix ? `${prefix}/${entry.name}` : entry.name;
    for (const ch of allChildren) {
      out.push(...(await collectEntryFiles(ch, nextPref)));
    }
    return out;
  }
  return [];
}

const SESSIONS_KEY = 'ph_sessions_v1';

function loadInitialSessions(): ChatSession[] {
  try {
    const raw = localStorage.getItem(SESSIONS_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length > 0) return parsed;
    }
  } catch {
    // ignore storage parse failure
  }
  return [{ id: `s-${Date.now()}`, title: '新对话', messages: [], updatedAt: Date.now() }];
}

export default function App() {
  const [sessions, setSessions] = useState<ChatSession[]>(loadInitialSessions);
  const [activeSessionId, setActiveSessionId] = useState<string>(() => loadInitialSessions()[0].id);
  const activeSessionIdRef = useRef<string>(activeSessionId);
  activeSessionIdRef.current = activeSessionId;

  // Per-session concurrent streaming state & AbortControllers (multiple chats can run simultaneously!)
  const [streamingMap, setStreamingMap] = useState<Record<string, boolean>>({});
  const abortMapRef = useRef<Record<string, AbortController>>({});

  // Dynamic right-side tool studio: `null` means calm Mrite-style idle stage; Agent auto-opens the exact studio on tool call!
  const [activeTool, setActiveTool] = useState<StudioId | null>(null);
  const [autoOpened, setAutoOpened] = useState(false);

  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [workspaceOpen, setWorkspaceOpen] = useState(true);
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [inspectorTab, setInspectorTab] = useState<'todos' | 'artifacts'>('todos');
  const [treeOpen, setTreeOpen] = useState(true);

  const [todosBySession, setTodosBySession] = useState<Record<string, AgentTodoItem[]>>({});
  const [artifactsBySession, setArtifactsBySession] = useState<Record<string, SessionArtifact[]>>({});

  const [theme, setTheme] = useState<'paper' | 'ink'>('paper');
  const [lang, setLang] = useState<Lang>(() => (localStorage.getItem('ph_lang') as Lang) || 'zh');
  const [uiZoom, setUiZoom] = useState<number>(() => Number(localStorage.getItem('ph_zoom') || '100'));
  const [modelHubOpen, setModelHubOpen] = useState(false);
  const [hubInitialTab, setHubInitialTab] = useState<TabKey>('domestic');
  const openModelHub = (tab: TabKey = 'domestic') => {
    setHubInitialTab(tab);
    setModelHubOpen(true);
  };
  const [toast, setToast] = useState<{ msg: string; revealPath?: string } | null>(null);
  const [exportsDir, setExportsDir] = useState('');
  const [lastImportPath, setLastImportPath] = useState('');
  const [lastExportPath, setLastExportPath] = useState('');
  const [texWorkspace, setTexWorkspace] = useState<TexWorkspaceState | null>(null);
  const [folderDragOver, setFolderDragOver] = useState(false);
  const [externalAttachImg, setExternalAttachImg] = useState<{ id: number; dataUrl: string } | null>(null);
  const nativeDropHandledRef = useRef(0);
  const wsZipInputRef = useRef<HTMLInputElement>(null);

  const [settings, setSettings] = useState<SettingsPayload | null>(null);
  const [sample, setSample] = useState<any>(null);

  const [title, setTitle] = useState('PaperHarness');
  const [content, setContent] = useState('');
  const [originalContent, setOriginalContent] = useState('');
  const [preamble, setPreamble] = useState('');
  const [venue, setVenue] = useState('CVPR / ICCV');
  const [bibtex, setBibtex] = useState('');

  const [patcherSvg, setPatcherSvg] = useState('');
  const [incomingRaster, setIncomingRaster] = useState<IncomingRasterPayload | null>(null);
  const [externalDiagram, setExternalDiagram] = useState<{ id: number; blueprint: DiagramBlueprint } | null>(null);
  const [diagramRefinement, setDiagramRefinement] = useState<DiagramRefinementPayload | null>(null);
  const [externalChart, setExternalChart] = useState<ExternalChartPayload | null>(null);
  const [externalManuscript, setExternalManuscript] = useState<ExternalManuscriptAction | null>(null);

  const quickImportRef = useRef<HTMLInputElement>(null);
  const t = T[lang];

  const activeSession = sessions.find((s) => s.id === activeSessionId) || sessions[0];
  const todos = todosBySession[activeSession.id] || [];
  const artifacts = artifactsBySession[activeSession.id] || [];
  const runningCount = Object.values(streamingMap).filter(Boolean).length;

  const studioMeta: Array<{ id: StudioId; label: string; tag: string; icon: React.FC<any> }> = [
    { id: 'manuscript', label: t.st_manuscript, tag: lang === 'zh' ? '论文' : 'Doc', icon: FileText },
    { id: 'diagrams', label: t.st_diagrams, tag: 'PPT', icon: Network },
    { id: 'charts', label: t.st_charts, tag: lang === 'zh' ? '绘图' : 'Plot', icon: BarChart3 },
    { id: 'patcher', label: t.st_patcher, tag: lang === 'zh' ? '改图' : 'Edit', icon: Type },
    { id: 'citations', label: t.st_citations, tag: 'Bib', icon: BookMarked },
  ];

  const notify = (msg: string, revealPath?: string) => {
    const next = { msg, revealPath };
    setToast(next);
    setTimeout(() => setToast((cur) => (cur?.msg === msg ? null : cur)), revealPath ? 6000 : 3400);
  };

  const refreshSettings = async () => {
    const s = await api.getSettings();
    setSettings(s);
  };

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  useEffect(() => {
    localStorage.setItem('ph_lang', lang);
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
  }, [lang]);

  useEffect(() => {
    localStorage.setItem('ph_zoom', String(uiZoom));
    document.documentElement.style.fontSize = `${(14 * uiZoom) / 100}px`;
  }, [uiZoom]);

  // Persist lightweight text-only session history (strip bulky base64 images before saving to localStorage)
  useEffect(() => {
    try {
      const compact = sessions.slice(0, 18).map((s) => ({
        ...s,
        messages: s.messages.map((m) => ({
          ...m,
          images: undefined,
          tools: m.tools?.map((tr) => ({ ...tr, preview_png_b64: undefined })),
        })),
      }));
      localStorage.setItem(SESSIONS_KEY, JSON.stringify(compact));
    } catch {
      // ignore quota error
    }
  }, [sessions]);

  useEffect(() => {
    Promise.all([api.getSettings(), api.sample(), api.health()])
      .then(([s, smp, h]) => {
        setSettings(s);
        setSample(smp);
        if (h?.exports_dir) setExportsDir(h.exports_dir);
        if (smp?.paper) {
          setTitle(smp.paper.title);
          setContent(smp.paper.content);
          setOriginalContent(smp.paper.content);
          setVenue(smp.paper.venue || 'CVPR / ICCV');
          setBibtex(smp.paper.bibtex || '');
        }
      })
      .catch((err) => notify(err.message));

    const onFileIo = (e: Event) => {
      const d = (e as CustomEvent<{ kind: 'export' | 'import'; filename: string; path: string }>).detail;
      if (!d?.path) return;
      if (d.kind === 'export') {
        setLastExportPath(d.path);
        notify(`已导出 ${d.filename} → ${d.path}`, d.path);
      } else {
        setLastImportPath(d.path);
      }
    };
    const onNativeFolderDrop = (e: Event) => {
      const folderPath = String((e as CustomEvent<string>).detail || '').trim();
      if (!folderPath) return;
      nativeDropHandledRef.current = Date.now();
      setFolderDragOver(false);
      api
        .workspaceOpenFolder(folderPath)
        .then(applyLoadedWorkspace)
        .catch((err) => notify(err.message));
    };
    window.addEventListener('ph:file-io', onFileIo);
    window.addEventListener('ph:native-folder-drop', onNativeFolderDrop);
    return () => {
      window.removeEventListener('ph:file-io', onFileIo);
      window.removeEventListener('ph:native-folder-drop', onNativeFolderDrop);
    };
  }, []);

  const applyLoadedWorkspace = (ws: any) => {
    setTexWorkspace({
      root_dir: ws.root_dir,
      project_name: ws.project_name,
      main_tex: ws.main_tex,
      active_file: ws.active_file || ws.main_tex,
      tex_files: ws.tex_files || [],
      bib_files: ws.bib_files || [],
      figures: ws.figures || [],
      data_files: ws.data_files || [],
    });
    if (ws.title) setTitle(ws.title);
    if (ws.content !== undefined) {
      setContent(ws.content);
      setOriginalContent(ws.content);
    }
    setPreamble(ws.preamble || '');
    if (ws.bibtex) setBibtex(ws.bibtex);
    setLastImportPath(ws.root_dir);
    setActiveTool('manuscript');
    setAutoOpened(false);
    setWorkspaceOpen(true);
    setInspectorOpen(true);
    setSidebarOpen(false);
    notify(
      lang === 'zh'
        ? `已挂载 LaTeX 工作区：${ws.project_name}（${ws.tex_files?.length || 0} 个 .tex · ${ws.figures?.length || 0} 张图片 · ${ws.bib_files?.length || 0} 个 .bib）`
        : `Mounted LaTeX workspace: ${ws.project_name}`,
      ws.root_dir,
    );
  };

  const triggerOpenLatexFolder = async () => {
    const pyApi = window.pywebview?.api;
    if (pyApi?.pick_workspace_folder) {
      try {
        const res = await pyApi.pick_workspace_folder();
        if (res?.cancelled || !res?.ok || !res.path) return;
        const ws = await api.workspaceOpenFolder(res.path);
        applyLoadedWorkspace(ws);
        return;
      } catch (e: any) {
        notify(e.message);
        return;
      }
    }
    wsZipInputRef.current?.click();
  };

  const handleGlobalDrop = async (e: React.DragEvent) => {
    setFolderDragOver(false);
    // If native pywebview full-path handler already mounted the dropped folder within the last 800ms, skip duplicate web upload
    if (Date.now() - nativeDropHandledRef.current < 800) return;
    const items = Array.from(e.dataTransfer?.items || []);
    const dirEntry = items.map((it) => (it as any).webkitGetAsEntry?.()).find((en) => en && en.isDirectory);
    if (dirEntry) {
      e.preventDefault();
      e.stopPropagation();
      try {
        notify(lang === 'zh' ? `正在扫描并读取文件夹「${dirEntry.name}」全部 .tex / 图片 / .bib…` : `Loading folder ${dirEntry.name}…`);
        const collected = await collectEntryFiles(dirEntry);
        if (!collected.length) return;
        const ws = await api.workspaceImportFiles(dirEntry.name, collected);
        applyLoadedWorkspace(ws);
      } catch (err: any) {
        notify(err.message);
      }
      return;
    }
    const zipFile = Array.from(e.dataTransfer?.files || []).find((f) => f.name.toLowerCase().endsWith('.zip'));
    if (zipFile) {
      e.preventDefault();
      e.stopPropagation();
      try {
        const ws = await api.workspaceImportZip(zipFile);
        applyLoadedWorkspace(ws);
      } catch (err: any) {
        notify(err.message);
      }
    }
  };

  const handleOpenWorkspaceTex = async (rel: string) => {
    try {
      const res = await api.workspaceReadFile(rel);
      setContent(res.content);
      setOriginalContent(res.content);
      setPreamble(res.preamble || '');
      setTexWorkspace((prev) => (prev ? { ...prev, active_file: rel } : prev));
      setActiveTool('manuscript');
      setWorkspaceOpen(true);
      notify(lang === 'zh' ? `已打开工作区文件：${rel}` : `Opened ${rel}`);
    } catch (e: any) {
      notify(e.message);
    }
  };

  const handleSaveBackToWorkspace = async () => {
    if (!texWorkspace?.active_file) return;
    try {
      const res = await api.workspaceSaveFile(texWorkspace.active_file, content, preamble);
      setOriginalContent(content);
      setLastExportPath(res.full_path);
      notify(lang === 'zh' ? `已保存回原工作区（已自动备份 .bak）：${res.full_path}` : `Saved to ${res.full_path}`, res.full_path);
    } catch (e: any) {
      notify(e.message);
    }
  };

  const handleOpenWorkspaceFigureInPatcher = async (rel: string) => {
    try {
      const insp = await api.workspaceFigurePatcher(rel);
      if (insp.kind === 'svg') {
        setPatcherSvg(insp.svg);
      } else {
        setIncomingRaster({ id: Date.now(), image_b64: insp.image_b64, width: insp.width, height: insp.height, boxes: insp.boxes || [] });
      }
      openToolStudio('patcher', false);
      notify(
        lang === 'zh'
          ? `已载入工作区图片 ${rel}${insp.boxes?.length ? `（自动识别 ${insp.boxes.length} 个可拖动文字框）` : ''}`
          : `Loaded ${rel} into Figure Patcher`,
      );
    } catch (e: any) {
      notify(e.message);
    }
  };

  const handleSendWorkspaceFigureToChat = async (rel: string) => {
    try {
      const res = await api.workspaceFigureDataUrl(rel);
      setExternalAttachImg({ id: Date.now(), dataUrl: res.data_url });
      notify(lang === 'zh' ? `已将工作区图片 ${rel} 附带到左侧对话框` : `Attached ${rel} to chat`);
    } catch (e: any) {
      notify(e.message);
    }
  };

  const openToolStudio = (st: StudioId, byAgent = false) => {
    setActiveTool(st);
    setAutoOpened(byAgent);
    setWorkspaceOpen(true);
    // Give wide studios generous horizontal room automatically (user can still re-open inspector anytime)
    setInspectorOpen(false);
    if (st === 'diagrams' || st === 'manuscript') setSidebarOpen(false);
  };

  const handleNewChat = () => {
    const ns: ChatSession = { id: `s-${Date.now()}`, title: lang === 'zh' ? '新对话' : 'New Chat', messages: [], updatedAt: Date.now() };
    setSessions((prev) => [ns, ...prev]);
    setActiveSessionId(ns.id);
  };

  const handleUpdateSessionMessages = (sessionId: string, updater: (prev: ChatMessage[]) => ChatMessage[]) => {
    setSessions((prev) =>
      prev.map((s) => {
        if (s.id !== sessionId) return s;
        const nextMsgs = updater(s.messages);
        const firstUser = nextMsgs.find((m) => m.role === 'user' && m.content.trim());
        const nextTitle =
          s.title === '新对话' || s.title === 'New Chat'
            ? firstUser
              ? firstUser.content.trim().slice(0, 20)
              : s.title
            : s.title;
        return { ...s, title: nextTitle, messages: nextMsgs, updatedAt: Date.now() };
      }),
    );
  };

  const handleStreamingChange = (sessionId: string, running: boolean, ctrl?: AbortController) => {
    if (running && ctrl) {
      abortMapRef.current[sessionId] = ctrl;
    } else if (!running) {
      delete abortMapRef.current[sessionId];
    }
    setStreamingMap((prev) => {
      if (running) return { ...prev, [sessionId]: true };
      const next = { ...prev };
      delete next[sessionId];
      return next;
    });
  };

  const handleAbortSession = (sessionId: string) => {
    abortMapRef.current[sessionId]?.abort();
    delete abortMapRef.current[sessionId];
  };

  const handleSessionTodoUpdate = (sessionId: string, updater: (prev: AgentTodoItem[]) => AgentTodoItem[]) => {
    setTodosBySession((prev) => ({ ...prev, [sessionId]: updater(prev[sessionId] || []) }));
  };

  const handleSessionArtifactAdd = (sessionId: string, art: SessionArtifact) => {
    setArtifactsBySession((prev) => ({ ...prev, [sessionId]: [art, ...(prev[sessionId] || [])] }));
  };

  const handleImportFile = async (file: File, fullPath?: string) => {
    try {
      const doc = await api.importFile(file);
      setTitle(doc.title);
      setContent(doc.content);
      setOriginalContent(doc.content);
      setPreamble(doc.preamble || '');
      const loc = fullPath || file.name;
      setLastImportPath(loc);
      openToolStudio('manuscript', false);
      notify(lang === 'zh' ? `已导入论文：${loc}` : `Imported: ${loc}`, fullPath);
    } catch (e: any) {
      notify(e.message);
    }
  };

  const triggerNativeOrWebImport = async () => {
    const pyApi = window.pywebview?.api;
    if (pyApi?.pick_import_file) {
      try {
        const res = await pyApi.pick_import_file();
        if (res?.cancelled || !res?.ok || !res.b64 || !res.filename) return;
        const bin = atob(res.b64);
        const arr = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
        const f = new File([arr], res.filename);
        await handleImportFile(f, res.path);
        return;
      } catch (e: any) {
        notify(e.message);
        return;
      }
    }
    quickImportRef.current?.click();
  };

  const handleOmniUiAction = (evt: any, sourceSessionId: string) => {
    const uid = Date.now() + Math.random();
    const isForeground = sourceSessionId === activeSessionIdRef.current;
    const focusStudio = (st: StudioId, bgNote?: string) => {
      if (isForeground) {
        openToolStudio(st, true);
      } else {
        notify(bgNote || (lang === 'zh' ? '后台并发对话已完成任务，可在左侧历史切换查看' : 'Background chat finished its task'));
      }
    };
    if (evt.action === 'load_diagram' && evt.blueprint) {
      setExternalDiagram({ id: uid, blueprint: evt.blueprint });
      focusStudio('diagrams', lang === 'zh' ? '后台对话已绘成顶刊流程图，点击左侧对话或「PPT」标签查看' : 'Background chat finished diagram');
      if (isForeground) notify(lang === 'zh' ? 'Agent 已绘成顶刊流程图并自动打开画布' : 'Agent opened Diagram Studio');
    } else if (evt.action === 'refine_diagram') {
      setDiagramRefinement({
        id: uid,
        venue_theme: evt.venue_theme,
        custom_colors: evt.custom_colors,
        node_updates: evt.node_updates,
      });
      focusStudio('diagrams');
      if (isForeground) notify(lang === 'zh' ? '已按你的要求微调流程图风格与框内图示' : 'Refined diagram styling & nodes');
    } else if (evt.action === 'load_chart' || evt.action === 'load_table') {
      setExternalChart({
        id: uid,
        sub_mode: evt.sub_mode || (evt.action === 'load_table' ? 'table' : 'figure'),
        csv_text: evt.csv_text || '',
        chart_type: evt.chart_type,
        title: evt.title,
        ylabel: evt.ylabel,
        venue: evt.venue,
        caption: evt.caption,
        label: evt.label,
        lower_is_better: evt.lower_is_better,
      });
      focusStudio('charts', lang === 'zh' ? '后台对话已生成图表/三线表，可在「绘图」工作台查看' : 'Background chat finished chart/table');
    } else if (evt.action === 'update_manuscript' && typeof evt.content === 'string') {
      setContent(evt.content);
      focusStudio('manuscript');
    } else if (evt.action === 'push_edits') {
      setExternalManuscript({ id: uid, edits: evt.edits, stream_text: evt.stream_text });
      focusStudio('manuscript', lang === 'zh' ? '后台对话已生成逐句润色/翻译卡片，可在「论文」工作台审校' : 'Background chat pushed manuscript edits');
    } else if (evt.action === 'open_formula_studio') {
      setExternalManuscript({ id: uid, center_view: 'formula' });
      focusStudio('manuscript');
    } else if (evt.action === 'load_patcher_svg' && evt.svg) {
      setPatcherSvg(evt.svg);
      focusStudio('patcher');
    } else if (evt.action === 'load_patcher_raster' && evt.image_b64) {
      setIncomingRaster({ id: uid, image_b64: evt.image_b64, width: evt.width, height: evt.height, boxes: evt.boxes });
      focusStudio('patcher');
    } else if (evt.action === 'load_citations') {
      if (evt.bibtex) setBibtex(evt.bibtex);
      focusStudio('citations', lang === 'zh' ? '后台对话已完成引用核验，可在「Bib」查看结果' : 'Background chat finished citation audit');
    } else if (evt.action === 'switch_studio' && evt.studio && evt.studio !== 'corpus') {
      if (isForeground) openToolStudio(evt.studio, true);
    }
  };

  const activeRoute = settings?.routing?.writing;
  const activeProv = settings?.providers?.find((p) => p.id === activeRoute?.provider_id);
  const isProviderReady = Boolean(
    activeProv && (activeProv.has_key || activeProv.region === 'local') && (activeRoute?.model || activeProv.default_model),
  );

  const handleExportWord = async () => {
    try {
      const tracked = content !== originalContent;
      const res = await downloadBlob(
        '/api/manuscript/export-docx',
        {
          title,
          revised_text: content,
          original_text: originalContent,
          track_changes: tracked,
          author: settings?.preferences?.author_name || 'PaperHarness',
        },
        'manuscript.docx',
      );
      if (res.saved && !res.path) {
        notify(tracked ? (lang === 'zh' ? '已导出 Word 修订版 .docx' : 'Exported Track Changes .docx') : (lang === 'zh' ? '已导出 .docx' : 'Exported .docx'));
      }
    } catch (e: any) {
      notify(e.message);
    }
  };

  const handleExportLatex = async () => {
    try {
      const res = await downloadBlob('/api/manuscript/export-latex', { title, content, preamble }, 'manuscript.tex');
      if (res.saved && !res.path) notify(lang === 'zh' ? '已导出 LaTeX .tex 源码' : 'Exported .tex');
    } catch (e: any) {
      notify(e.message);
    }
  };

  const activeStudioInfo = studioMeta.find((s) => s.id === activeTool);

  return (
    <div
      className="desktop-root"
      onDragOver={(e) => {
        const hasDirOrZip = Array.from(e.dataTransfer?.items || []).some(
          (it) => it.kind === 'file' && ((it as any).webkitGetAsEntry?.()?.isDirectory || it.type === 'application/zip' || it.type === 'application/x-zip-compressed'),
        );
        if (hasDirOrZip) {
          e.preventDefault();
          setFolderDragOver(true);
        }
      }}
      onDragLeave={(e) => {
        if (e.currentTarget === e.target) setFolderDragOver(false);
      }}
      onDrop={handleGlobalDrop}
    >
      <input
        ref={wsZipInputRef}
        type="file"
        accept=".zip"
        style={{ display: 'none' }}
        onChange={async (e) => {
          const f = e.target.files?.[0];
          if (f) {
            try {
              applyLoadedWorkspace(await api.workspaceImportZip(f));
            } catch (err: any) {
              notify(err.message);
            }
          }
          e.target.value = '';
        }}
      />
      {folderDragOver && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 300,
            background: 'rgba(30, 58, 95, 0.14)',
            backdropFilter: 'blur(3px)',
            border: '3px dashed var(--accent)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            pointerEvents: 'none',
          }}
        >
          <div className="card" style={{ padding: '22px 32px', textAlign: 'center', boxShadow: 'var(--shadow-md)' }}>
            <FolderInput size={34} color="var(--accent)" style={{ marginBottom: 8 }} />
            <div style={{ fontFamily: 'var(--font-serif)', fontSize: 19, fontWeight: 600 }}>
              {lang === 'zh' ? '松开鼠标，直接导入整个 LaTeX 论文工作区' : 'Drop to Mount Full LaTeX Workspace'}
            </div>
            <div style={{ fontSize: 12.5, color: 'var(--ink-muted)', marginTop: 4 }}>
              {lang === 'zh' ? '自动读取所有 .tex 章节、figures/ 论文图片（含 PDF/SVG/PNG）与 .bib 文献库' : 'Auto-indexes all .tex sections, figures, and .bib references'}
            </div>
          </div>
        </div>
      )}
      {/* NATIVE FRAMELESS DESKTOP TITLEBAR (Mrite-style clean top bar, draggable in pywebview) */}
      <header className="desktop-titlebar pywebview-drag-region">
        <div className="titlebar-brand">
          <span className="brand-wordmark">PaperHarness</span>
          <span className="titlebar-sep">/</span>
          <span className="titlebar-doc" title={title}>
            {title}
          </span>
        </div>

        <div className="titlebar-right no-drag">
          <button className="titlebar-pill" onClick={() => openModelHub('domestic')}>
            <span className={`dot-inline ${isProviderReady ? 'online' : 'offline'}`} />
            <span>
              {isProviderReady
                ? `${activeProv?.name.split(' ')[0]} · ${activeRoute?.model || activeProv?.default_model}`
                : t.cfg_api}
            </span>
          </button>

          <button className="titlebar-chip" onClick={() => setLang((l) => (l === 'zh' ? 'en' : 'zh'))} title={t.switch_lang_title}>
            {lang === 'zh' ? 'EN' : '中文'}
          </button>

          {texWorkspace && (
            <>
              <button
                className="titlebar-chip"
                onClick={handleSaveBackToWorkspace}
                title={`写回原文件：${texWorkspace.root_dir}\\${texWorkspace.active_file}`}
                style={{ borderColor: 'var(--sage-border)', color: 'var(--sage)', background: 'var(--sage-soft)' }}
              >
                <Save size={13} /> {lang === 'zh' ? `保存 ${texWorkspace.active_file}` : 'Save TeX'}
              </button>
              <button
                className="titlebar-chip"
                onClick={async () => {
                  try {
                    const fname = `${(texWorkspace.project_name || 'paper').replace(/[^\w\u4e00-\u9fa5.-]/g, '_')}_submission.zip`;
                    const res = await downloadBlob('/api/workspace/export-submission-zip', {}, fname);
                    if (res.saved && !res.path) notify(lang === 'zh' ? `已打包干净投稿压缩包：${fname}` : `Exported ${fname}`);
                  } catch (e: any) {
                    notify(e.message);
                  }
                }}
                title={lang === 'zh' ? '一键清理 .aux/.log/.bak/编译PDF，打包干净的 Overleaf / arXiv 投稿包 (.zip)' : 'Export clean submission.zip (strips .aux/.log/.bak/compiled PDF)'}
              >
                <Archive size={13} /> {lang === 'zh' ? '打包投稿 .zip' : 'Submit .zip'}
              </button>
            </>
          )}

          <button
            className="titlebar-chip"
            onClick={() => api.revealPath(lastExportPath || exportsDir)}
            title={lastExportPath ? `最近导出：${lastExportPath}` : `默认导出目录：${exportsDir}`}
          >
            <FolderOpen size={13} /> {lang === 'zh' ? '导出位置' : 'Exports'}
          </button>

          <button className="titlebar-chip" onClick={handleExportLatex} title={t.export_tex}>
            <FileCode2 size={13} /> .tex
          </button>

          <button className="titlebar-chip accent" onClick={handleExportWord} title={t.export_docx}>
            <FileText size={13} /> {content !== originalContent ? (lang === 'zh' ? '修订 .docx' : 'Tracked') : '.docx'}
          </button>

          <div className="win-controls">
            <button className="win-btn" title="最小化" onClick={() => window.pywebview?.api?.minimize?.()}>
              <Minus size={13.5} />
            </button>
            <button className="win-btn" title="最大化 / 还原" onClick={() => window.pywebview?.api?.toggle_maximize?.()}>
              <Maximize2 size={12} />
            </button>
            <button className="win-btn close" title="关闭" onClick={() => window.pywebview?.api?.close?.()}>
              <X size={14} />
            </button>
          </div>
        </div>
      </header>

      {/* MAIN 4-COLUMN MRITE-INSPIRED DESKTOP BODY */}
      <div className="desktop-body">
        {/* 1. FAR-LEFT SLIM ICON RAIL */}
        <nav className="icon-rail" aria-label="Workspace Navigation">
          <button
            className={`rail-icon-btn ${activeTool === null ? 'active' : ''}`}
            title={lang === 'zh' ? '对话主页' : 'Conversation Home'}
            onClick={() => {
              setActiveTool(null);
              setWorkspaceOpen(true);
              setSidebarOpen(true);
              setInspectorOpen(true);
            }}
          >
            <Home size={18} strokeWidth={1.85} />
          </button>

          {studioMeta.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              className={`rail-icon-btn ${activeTool === id ? 'active' : ''}`}
              title={label}
              onClick={() => openToolStudio(id, false)}
            >
              <Icon size={17.5} strokeWidth={1.8} />
            </button>
          ))}

          <div className="rail-spacer" />

          <button
            className="rail-icon-btn"
            title={lang === 'zh' ? '多模态术语库与联网搜索设置' : 'Glossary & Web Search'}
            onClick={() => openModelHub('glossary_search')}
          >
            <BookOpen size={17} />
          </button>

          <button
            className="rail-text-chip"
            title={lang === 'zh' ? `字号缩放 ${uiZoom}%` : `Scale ${uiZoom}%`}
            onClick={() => setUiZoom((z) => (z >= 120 ? 100 : z + 10))}
          >
            {uiZoom === 100 ? 'A+' : `${uiZoom}%`}
          </button>

          <button
            className="rail-icon-btn"
            title={theme === 'paper' ? t.switch_theme_dark : t.switch_theme_light}
            onClick={() => setTheme((cur) => (cur === 'paper' ? 'ink' : 'paper'))}
          >
            {theme === 'paper' ? <Moon size={16.5} /> : <Sun size={16.5} />}
          </button>

          <button className="rail-icon-btn" title={t.hub_title} onClick={() => openModelHub('domestic')} style={{ position: 'relative' }}>
            <Settings size={17} />
            <span className={`status-dot ${isProviderReady ? 'online' : 'offline'}`} />
          </button>
        </nav>

        {/* 2. LEFT PROJECTS & CONVERSATION HISTORY SIDEBAR (Mrite style) */}
        {sidebarOpen && (
          <aside className="history-sidebar">
            <div className="history-head">
              <span className="history-brand">PaperHarness</span>
              <input
                ref={quickImportRef}
                type="file"
                accept=".docx,.tex,.pdf,.md,.txt"
                style={{ display: 'none' }}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) handleImportFile(f);
                  e.target.value = '';
                }}
              />
              <div style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                <button className="icon-flat-btn" title={lang === 'zh' ? '打开整个 LaTeX 文件夹（或拖入窗口）' : 'Open LaTeX Folder'} onClick={triggerOpenLatexFolder}>
                  <FolderInput size={15} />
                </button>
                <button className="icon-flat-btn" title={lang === 'zh' ? '导入单个文档 (.docx/.tex/.pdf)' : 'Import single file'} onClick={triggerNativeOrWebImport}>
                  <FileUp size={15} />
                </button>
              </div>
            </div>

            <button className="new-chat-row" onClick={handleNewChat}>
              <SquarePen size={14.5} />
              <span>{lang === 'zh' ? '新对话' : 'New Chat'}</span>
            </button>

            <div className="history-scroll">
              <div className="history-group-title">{lang === 'zh' ? '置顶项目' : 'Pinned'}</div>
              <button className={`history-item ${activeTool === 'manuscript' ? 'active' : ''}`} onClick={() => openToolStudio('manuscript', false)}>
                <span className="history-item-text">{title}</span>
                <span className="mini-tag">{lang === 'zh' ? '论文' : 'Doc'}</span>
              </button>

              <div className="history-group-title" style={{ marginTop: 14 }}>
                {lang === 'zh' ? '科研工作台' : 'Tools'}
              </div>
              {studioMeta.map((st) => (
                <button key={st.id} className={`history-item ${activeTool === st.id ? 'active' : ''}`} onClick={() => openToolStudio(st.id, false)}>
                  <span className="history-item-text">{st.label}</span>
                  <span className="mini-tag">{st.tag}</span>
                </button>
              ))}
              <button className="history-item" onClick={() => openModelHub('glossary_search')}>
                <span className="history-item-text">{lang === 'zh' ? '术语库与联网搜索' : 'Glossary & Search'}</span>
                <span className="mini-tag">{lang === 'zh' ? '查词' : 'Web'}</span>
              </button>

              <div className="history-group-title" style={{ marginTop: 14, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span>{lang === 'zh' ? '对话历史' : 'History'}</span>
                {runningCount > 0 && (
                  <span style={{ fontSize: 10.5, color: 'var(--accent)', fontWeight: 600 }}>
                    {lang === 'zh' ? `${runningCount} 并发中` : `${runningCount} running`}
                  </span>
                )}
              </div>
              {sessions.map((s) => (
                <div
                  key={s.id}
                  className={`history-item ${s.id === activeSession.id ? 'active' : ''}`}
                  onClick={() => setActiveSessionId(s.id)}
                >
                  {streamingMap[s.id] && <Loader2 size={12.5} className="spin" color="var(--accent)" style={{ flexShrink: 0 }} />}
                  <span className="history-item-text">{s.title}</span>
                  {sessions.length > 1 && (
                    <button
                      className="history-del"
                      title="删除"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleAbortSession(s.id);
                        const rest = sessions.filter((x) => x.id !== s.id);
                        setSessions(rest);
                        if (activeSessionId === s.id && rest[0]) setActiveSessionId(rest[0].id);
                      }}
                    >
                      <Trash2 size={12} />
                    </button>
                  )}
                </div>
              ))}
            </div>
          </aside>
        )}

        {/* 3. PRIMARY CONVERSATION PANE (Always center-stage! Supports true multi-chat concurrency) */}
        <ConversationPane
          lang={lang}
          sessionId={activeSession.id}
          sessionTitle={activeSession.title}
          messages={activeSession.messages}
          isStreaming={Boolean(streamingMap[activeSession.id])}
          runningCount={runningCount}
          sidebarOpen={sidebarOpen}
          workspaceOpen={workspaceOpen}
          workspaceContext={{
            studio: activeTool || 'manuscript',
            title,
            venue,
            manuscript: content,
            bibtex,
            latex_workspace: texWorkspace
              ? {
                  root_dir: texWorkspace.root_dir,
                  active_file: texWorkspace.active_file,
                  tex_files: texWorkspace.tex_files.map((f) => f.rel),
                  figures: texWorkspace.figures.map((f) => f.rel),
                }
              : null,
          }}
          externalAttachImage={externalAttachImg}
          onMessagesChange={handleUpdateSessionMessages}
          onStreamingChange={handleStreamingChange}
          onAbortSession={handleAbortSession}
          onToggleSidebar={() => setSidebarOpen((v) => !v)}
          onToggleWorkspace={() => setWorkspaceOpen((v) => !v)}
          onNewChat={handleNewChat}
          onImportDocFile={handleImportFile}
          onPickImportDoc={triggerNativeOrWebImport}
          onOpenModelHub={() => openModelHub('domestic')}
          onUiAction={handleOmniUiAction}
          onJumpStudio={(st) => openToolStudio(st, false)}
          onTodoUpdate={handleSessionTodoUpdate}
          onArtifactAdd={handleSessionArtifactAdd}
          onNotify={notify}
        />

        {/* 4. DYNAMIC AUTO-OPEN TOOL WORKSPACE STAGE */}
        {workspaceOpen && (
          <main className="dynamic-workspace">
            {activeTool === null ? (
              /* Calm Mrite-style Idle Canvas — Agent auto-opens the exact right studio when you chat! */
              <div className="idle-stage view-fade">
                <div className="hero-watermark" aria-hidden="true">
                  PaperHarness
                </div>
                <div className="idle-stage-inner">
                  <div className="idle-caption">
                    {lang === 'zh'
                      ? '在左侧直接对话，Agent 会自动决定并打开对应工具页面；也可从下方快速进入'
                      : 'Chat on the left — the Agent automatically opens the right tool here, or pick one below'}
                  </div>
                  <div className="idle-pills">
                    <button className="idle-pill" onClick={triggerOpenLatexFolder}>
                      <FolderInput size={16} color="var(--accent)" />
                      <span>{lang === 'zh' ? '打开 / 拖入整个 LaTeX 论文文件夹（含图片与 Bib）' : 'Open / Drop Full LaTeX Folder'}</span>
                    </button>
                    <button className="idle-pill" onClick={triggerNativeOrWebImport}>
                      <FileUp size={16} color="var(--accent)" />
                      <span>{lang === 'zh' ? '导入单个文档 (.docx / .tex / .pdf)' : 'Import Single Manuscript'}</span>
                    </button>
                    <button className="idle-pill" onClick={() => openToolStudio('diagrams', false)}>
                      <Network size={16} color="var(--accent)" />
                      <span>{lang === 'zh' ? '顶刊流程图 · 多智能体绘 PPT' : 'Architecture Diagram · PPTX'}</span>
                    </button>
                    <button className="idle-pill" onClick={() => openToolStudio('charts', false)}>
                      <BarChart3 size={16} color="var(--accent)" />
                      <span>{lang === 'zh' ? '智能数据绘图与三线表 (600 DPI)' : 'Smart Data Figures & Tables'}</span>
                    </button>
                    <button className="idle-pill" onClick={() => openToolStudio('patcher', false)}>
                      <Type size={16} color="var(--accent)" />
                      <span>{lang === 'zh' ? '安全改图文字（拖拽定位校验）' : 'Safe Text-Only Figure Patcher'}</span>
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              /* Auto-Opened Full Interactive Tool Studio */
              <div className="active-studio-wrap">
                <div className="studio-strip">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0, overflow: 'hidden' }}>
                    <span className="studio-badge">
                      {autoOpened ? (lang === 'zh' ? 'Agent 自动打开 · ' : 'Auto · ') : ''}
                      {activeStudioInfo?.label}
                    </span>
                    <div className="studio-mini-tabs">
                      {studioMeta.map((st) => (
                        <button
                          key={st.id}
                          className={`mini-tab ${activeTool === st.id ? 'active' : ''}`}
                          onClick={() => {
                            setActiveTool(st.id);
                            setAutoOpened(false);
                          }}
                        >
                          {st.tag}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 5, flexShrink: 0 }}>
                    <button
                      className={`icon-flat-btn ${inspectorOpen ? 'active' : ''}`}
                      onClick={() => setInspectorOpen((v) => !v)}
                      title={lang === 'zh' ? '显示/隐藏产物与待办栏' : 'Toggle Artifacts & Todos'}
                    >
                      <PanelRight size={15.5} />
                    </button>
                    <button
                      className="icon-flat-btn"
                      onClick={() => {
                        setActiveTool(null);
                        setInspectorOpen(true);
                      }}
                      title={lang === 'zh' ? '收起工作台返回简洁画布' : 'Return to clean canvas'}
                    >
                      <X size={15.5} />
                    </button>
                  </div>
                </div>

                <div key={activeTool} className="studio-enter">
                  {activeTool === 'manuscript' && (
                    <ManuscriptStudio
                      lang={lang}
                      t={t}
                      title={title}
                      content={content}
                      originalContent={originalContent}
                      venue={venue}
                      externalAction={externalManuscript}
                      hasWorkspace={Boolean(texWorkspace)}
                      onPatchWorkspaceFigure={handleOpenWorkspaceFigureInPatcher}
                      onContentChange={setContent}
                      onVenueChange={setVenue}
                      onImportLoaded={(doc) => {
                        setTitle(doc.title);
                        setContent(doc.content);
                        setOriginalContent(doc.content);
                        setPreamble(doc.preamble || '');
                      }}
                      onNotify={notify}
                    />
                  )}

                  {activeTool === 'charts' && sample && (
                    <DataTableStudio
                      lang={lang}
                      t={t}
                      sampleDatasets={sample.datasets}
                      palettes={sample.chart_palettes}
                      venuePresets={sample.venue_presets}
                      externalChart={externalChart}
                      onSendSvgToPatcher={(svg) => {
                        setPatcherSvg(svg);
                        openToolStudio('patcher', false);
                      }}
                      onNotify={notify}
                    />
                  )}

                  {activeTool === 'diagrams' && sample && (
                    <DiagramStudio
                      lang={lang}
                      t={t}
                      templates={sample.diagram_templates}
                      themes={sample.diagram_themes}
                      themeDefs={sample.diagram_theme_defs}
                      manuscriptContent={content}
                      workspaceFigures={texWorkspace?.figures || []}
                      externalDiagram={externalDiagram}
                      externalRefinement={diagramRefinement}
                      onSendSvgToPatcher={(svg) => {
                        setPatcherSvg(svg);
                        openToolStudio('patcher', false);
                      }}
                      onOpenModelHub={() => openModelHub('domestic')}
                      onNotify={notify}
                    />
                  )}

                  {activeTool === 'patcher' && (
                    <FigurePatcherStudio
                      lang={lang}
                      t={t}
                      incomingSvg={patcherSvg}
                      incomingRaster={incomingRaster}
                      onNotify={notify}
                    />
                  )}

                  {activeTool === 'citations' && (
                    <CitationStudio lang={lang} t={t} manuscript={content} bibtex={bibtex} onBibtexChange={setBibtex} onNotify={notify} />
                  )}
                </div>
              </div>
            )}
          </main>
        )}

        {/* 5. FAR-RIGHT INSPECTOR: 产物 / 待办 + 工作区文件树 (Mrite exact right panel!) */}
        {inspectorOpen && (
          <aside className="inspector-rail">
            <div className="inspector-top">
              <div className="inspector-head">
                <div className="segmented" style={{ marginLeft: 'auto' }}>
                  <button className={`seg-btn ${inspectorTab === 'artifacts' ? 'active' : ''}`} style={{ height: 26, fontSize: 12 }} onClick={() => setInspectorTab('artifacts')}>
                    {lang === 'zh' ? `产物${artifacts.length ? ` (${artifacts.length})` : ''}` : `Artifacts`}
                  </button>
                  <button className={`seg-btn ${inspectorTab === 'todos' ? 'active' : ''}`} style={{ height: 26, fontSize: 12 }} onClick={() => setInspectorTab('todos')}>
                    {lang === 'zh' ? `待办${todos.length ? ` (${todos.length})` : ''}` : `Tasks`}
                  </button>
                </div>
              </div>

              <div className="inspector-body">
                {inspectorTab === 'todos' ? (
                  todos.length === 0 ? (
                    <div className="inspector-empty">
                      <div style={{ fontWeight: 600, color: 'var(--ink-secondary)', marginBottom: 4 }}>
                        {lang === 'zh' ? '本对话暂无待办' : 'No active tasks'}
                      </div>
                      <div>{lang === 'zh' ? 'Agent 开始规划后会显示在这里' : 'Agent steps will appear here'}</div>
                    </div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                      {todos.map((td) => (
                        <div
                          key={td.id}
                          className="card"
                          style={{ padding: '8px 10px', fontSize: 12, display: 'flex', alignItems: 'flex-start', gap: 7, cursor: td.studio ? 'pointer' : 'default' }}
                          onClick={() => td.studio && openToolStudio(td.studio, false)}
                        >
                          {td.status === 'running' ? (
                            <Loader2 size={13.5} className="spin" color="var(--accent)" style={{ flexShrink: 0, marginTop: 2 }} />
                          ) : (
                            <CheckCircle2 size={13.5} color={td.status === 'error' ? 'var(--vermilion)' : 'var(--sage)'} style={{ flexShrink: 0, marginTop: 2 }} />
                          )}
                          <span style={{ lineHeight: 1.45 }}>{td.label}</span>
                        </div>
                      ))}
                    </div>
                  )
                ) : artifacts.length === 0 ? (
                  <div className="inspector-empty">
                    <div style={{ fontWeight: 600, color: 'var(--ink-secondary)', marginBottom: 4 }}>
                      {lang === 'zh' ? '本对话暂无产物' : 'No artifacts yet'}
                    </div>
                    <div>{lang === 'zh' ? '流程图、高 DPI 图表与三线表将自动归档于此' : 'Generated PPTX, charts & tables appear here'}</div>
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {artifacts.map((art) => (
                      <div key={art.id} className="card" style={{ padding: '9px 10px', display: 'flex', flexDirection: 'column', gap: 6 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 6 }}>
                          <strong style={{ fontSize: 12.2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{art.title}</strong>
                          <span style={{ fontSize: 10.5, color: 'var(--ink-muted)' }}>{art.createdAt}</span>
                        </div>
                        <div style={{ display: 'flex', gap: 5 }}>
                          <button className="btn btn-sm" style={{ flex: 1, height: 26, fontSize: 11.5 }} onClick={() => openToolStudio(art.studio, false)}>
                            {lang === 'zh' ? '打开查看' : 'Open'}
                          </button>
                          {art.blueprint && (
                            <button
                              className="btn btn-primary btn-sm"
                              style={{ height: 26, fontSize: 11.5 }}
                              onClick={() => downloadBlob('/api/diagrams/export-pptx', { blueprint: art.blueprint }, 'paper_architecture.pptx')}
                            >
                              <Presentation size={12} /> .pptx
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Bottom Import/Export Paths + Workspace File Tree */}
            <div className="inspector-bottom">
              <div className="ctx-status-row">
                <span style={{ fontSize: 11.5, color: 'var(--ink-muted)' }}>3,000 篇语料库</span>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11.5, color: isProviderReady ? 'var(--sage)' : 'var(--amber)', fontWeight: 600 }}>
                  <span className={`dot-inline ${isProviderReady ? 'online' : 'offline'}`} />
                  {isProviderReady ? (lang === 'zh' ? '在线' : 'Online') : (lang === 'zh' ? '待配 Key' : 'No Key')}
                </span>
              </div>

              <div className="io-path-box">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <strong style={{ color: 'var(--ink-primary)' }}>{lang === 'zh' ? '导入 / 导出文件位置' : 'Import / Export Paths'}</strong>
                  <button
                    className="btn btn-ghost btn-sm"
                    style={{ height: 22, padding: '0 6px', fontSize: 11 }}
                    onClick={() => api.revealPath(lastExportPath || exportsDir)}
                  >
                    <FolderOpen size={12} /> {lang === 'zh' ? '打开目录' : 'Open'}
                  </button>
                </div>
                <div>
                  <span style={{ color: 'var(--ink-muted)' }}>{lang === 'zh' ? '导入来源：' : 'Imported: '}</span>
                  <span
                    className="io-path-line"
                    style={{ cursor: lastImportPath ? 'pointer' : 'default', textDecoration: lastImportPath ? 'underline' : 'none' }}
                    onClick={() => lastImportPath && api.revealPath(lastImportPath)}
                  >
                    {lastImportPath || (lang === 'zh' ? '点击导入选择本机 .docx / .tex / .pdf' : 'Not imported yet')}
                  </span>
                </div>
                <div>
                  <span style={{ color: 'var(--ink-muted)' }}>{lang === 'zh' ? '导出位置：' : 'Exported: '}</span>
                  <span
                    className="io-path-line"
                    style={{ cursor: 'pointer', textDecoration: 'underline', color: 'var(--accent)' }}
                    onClick={() => api.revealPath(lastExportPath || exportsDir)}
                    title={lang === 'zh' ? '点击在资源管理器中定位文件' : 'Reveal in Explorer'}
                  >
                    {lastExportPath || exportsDir || 'local_data/exports'}
                  </span>
                </div>
              </div>

              <div className="tree-section">
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <button className="tree-toggle" onClick={() => setTreeOpen((v) => !v)}>
                    {treeOpen ? <ChevronDown size={13.5} /> : <ChevronRight size={13.5} />}
                    <FolderOpen size={13.5} />
                    <span>{texWorkspace ? `${texWorkspace.project_name}/` : (lang === 'zh' ? '工作区文件' : 'Workspace')}</span>
                  </button>
                  <button
                    className="btn btn-ghost btn-sm"
                    style={{ height: 22, padding: '0 6px', fontSize: 11 }}
                    onClick={triggerOpenLatexFolder}
                    title={lang === 'zh' ? '打开或直接拖入整个 LaTeX 论文文件夹' : 'Open LaTeX Folder'}
                  >
                    <FolderInput size={12} /> {lang === 'zh' ? '导入目录' : 'Folder'}
                  </button>
                </div>

                {treeOpen && (
                  <div className="tree-list" style={{ maxHeight: 240, overflowY: 'auto' }}>
                    {texWorkspace ? (
                      <>
                        {texWorkspace.tex_files.map((f) => (
                          <button
                            key={f.rel}
                            className="tree-row"
                            style={{
                              fontWeight: texWorkspace.active_file === f.rel ? 700 : 400,
                              color: texWorkspace.active_file === f.rel ? 'var(--accent)' : undefined,
                              background: texWorkspace.active_file === f.rel ? 'var(--accent-soft)' : undefined,
                            }}
                            onClick={() => handleOpenWorkspaceTex(f.rel)}
                          >
                            <FileText size={12.5} color="var(--accent)" style={{ flexShrink: 0 }} />
                            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.rel}</span>
                          </button>
                        ))}

                        {texWorkspace.bib_files.map((bf) => (
                          <button key={bf.rel} className="tree-row" onClick={() => openToolStudio('citations', false)}>
                            <BookMarked size={12.5} color="var(--sage)" style={{ flexShrink: 0 }} />
                            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{bf.rel}</span>
                          </button>
                        ))}

                        {texWorkspace.data_files.map((df) => (
                          <button
                            key={df.rel}
                            className="tree-row"
                            onClick={async () => {
                              const r = await api.workspaceReadFile(df.rel);
                              setExternalChart({ id: Date.now(), sub_mode: 'figure', csv_text: r.content, title: df.name });
                              openToolStudio('charts', false);
                            }}
                          >
                            <BarChart3 size={12.5} color="var(--amber)" style={{ flexShrink: 0 }} />
                            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{df.rel}</span>
                          </button>
                        ))}

                        {texWorkspace.figures.length > 0 && (
                          <div style={{ fontSize: 10.5, fontWeight: 600, color: 'var(--ink-muted)', padding: '6px 4px 2px' }}>
                            {lang === 'zh' ? `论文图片 (${texWorkspace.figures.length}) · 点名称改字` : `Figures (${texWorkspace.figures.length})`}
                          </div>
                        )}
                        {texWorkspace.figures.map((fg) => (
                          <div key={fg.rel} style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                            <button
                              className="tree-row"
                              style={{ flex: 1, minWidth: 0 }}
                              title={lang === 'zh' ? `点击在「安全改图文字」中打开 ${fg.rel}` : `Edit text in ${fg.rel}`}
                              onClick={() => handleOpenWorkspaceFigureInPatcher(fg.rel)}
                            >
                              <Type size={12} color="var(--violet)" style={{ flexShrink: 0 }} />
                              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{fg.rel}</span>
                            </button>
                            <button
                              className="icon-flat-btn"
                              style={{ width: 22, height: 22, flexShrink: 0 }}
                              title={lang === 'zh' ? `把 ${fg.name} 附带到左侧对话框发给 AI` : `Send ${fg.name} to AI Chat`}
                              onClick={() => handleSendWorkspaceFigureToChat(fg.rel)}
                            >
                              <ImagePlus size={12} />
                            </button>
                          </div>
                        ))}
                      </>
                    ) : (
                      <>
                        <button className="tree-row" onClick={() => openToolStudio('manuscript', false)}>
                          <FileText size={13} color="var(--accent)" /> <span>manuscript.tex / .docx</span>
                        </button>
                        <button className="tree-row" onClick={() => openToolStudio('diagrams', false)}>
                          <Network size={13} color="var(--accent)" /> <span>architecture.pptx</span>
                        </button>
                        <button className="tree-row" onClick={() => openToolStudio('charts', false)}>
                          <BarChart3 size={13} color="var(--accent)" /> <span>figures_tables.csv</span>
                        </button>
                        <button className="tree-row" onClick={() => openToolStudio('patcher', false)}>
                          <Type size={13} color="var(--accent)" /> <span>figure_patcher.svg</span>
                        </button>
                        <button className="tree-row" onClick={() => openToolStudio('citations', false)}>
                          <BookMarked size={13} color="var(--accent)" /> <span>references.bib</span>
                        </button>
                      </>
                    )}
                  </div>
                )}
              </div>
            </div>
          </aside>
        )}
      </div>

      {settings && (
        <ModelHubModal
          open={modelHubOpen}
          initialTab={hubInitialTab}
          lang={lang}
          t={t}
          settings={settings}
          onClose={() => setModelHubOpen(false)}
          onRefresh={refreshSettings}
          onNotify={notify}
        />
      )}

      {toast && (
        <div className="toast">
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{toast.msg}</span>
          {toast.revealPath && (
            <button
              className="btn btn-sm"
              style={{ height: 24, padding: '0 8px', fontSize: 11.5, background: 'rgba(255,255,255,0.16)', borderColor: 'rgba(255,255,255,0.28)', color: 'inherit' }}
              onClick={() => api.revealPath(toast.revealPath!)}
            >
              <FolderOpen size={12} /> {lang === 'zh' ? '打开所在文件夹' : 'Open Folder'}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
