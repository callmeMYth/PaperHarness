/** Lean typed client for PaperHarness local API. */

async function req<T>(url: string, body?: unknown, method = 'POST'): Promise<T> {
  const res = await fetch(url, {
    method: body === undefined && method === 'POST' ? 'GET' : method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error((await res.text()) || `HTTP ${res.status}`);
  return res.json();
}

async function upload<T>(url: string, fd: FormData): Promise<T> {
  const res = await fetch(url, { method: 'POST', body: fd });
  if (!res.ok) throw new Error((await res.text()) || `HTTP ${res.status}`);
  return res.json();
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || '').split(',')[1] || '');
    reader.onerror = () => reject(new Error('文件编码失败'));
    reader.readAsDataURL(blob);
  });
}

function emitFileIo(kind: 'export' | 'import', filename: string, path: string) {
  window.dispatchEvent(new CustomEvent('ph:file-io', { detail: { kind, filename, path } }));
}

export async function saveExportBlob(blob: Blob, filename: string): Promise<{ saved: boolean; path?: string; filename: string }> {
  const b64 = await blobToBase64(blob);
  const pyApi = (window as any).pywebview?.api;

  // 1. Native standalone desktop app: pop real Windows "Save As" dialog & return exact disk path!
  if (pyApi?.save_file_b64) {
    const res = await pyApi.save_file_b64(filename, b64);
    if (res?.cancelled) return { saved: false, filename };
    if (res?.ok && res?.path) {
      emitFileIo('export', res.filename || filename, res.path);
      return { saved: true, path: res.path, filename: res.filename || filename };
    }
  }

  // 2. Fallback / Browser dev mode: also write a copy to local_data/exports/ so exact path is always known & revealable!
  let savedPath = '';
  try {
    const srv = await req<{ ok: boolean; path: string; filename: string }>('/api/system/save-export', { filename, data_b64: b64 });
    if (srv?.ok && srv.path) savedPath = srv.path;
  } catch {
    // ignore
  }
  const href = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = href;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(href), 2000);
  if (savedPath) emitFileIo('export', filename, savedPath);
  return { saved: true, path: savedPath || filename, filename };
}

export async function saveDataUri(b64: string, mime: string, filename: string): Promise<{ saved: boolean; path?: string; filename: string }> {
  const bin = atob(b64.split(',').pop() || '');
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  return saveExportBlob(new Blob([arr], { type: mime }), filename);
}

export async function saveTextFile(text: string, mime: string, filename: string): Promise<{ saved: boolean; path?: string; filename: string }> {
  return saveExportBlob(new Blob([text], { type: mime }), filename);
}

export async function downloadBlob(url: string, body: unknown, fallback: string): Promise<{ saved: boolean; path?: string; filename: string }> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  const blob = await res.blob();
  const m = (res.headers.get('Content-Disposition') || '').match(/filename="([^"]+)"/);
  return saveExportBlob(blob, m ? m[1] : fallback);
}

export const api = {
  health: () => req<any>('/api/health', undefined, 'GET'),
  revealPath: (path: string) => {
    const pyApi = (window as any).pywebview?.api;
    if (pyApi?.open_file_location) return pyApi.open_file_location(path);
    return req<any>('/api/system/reveal', { path });
  },
  sample: () => req<any>('/api/sample', undefined, 'GET'),
  getSettings: () => req<any>('/api/settings', undefined, 'GET'),
  saveProvider: (p: any) => req<{ ok: boolean }>('/api/settings/provider', p),
  deleteProvider: (id: string) => req<{ ok: boolean }>(`/api/settings/provider/${encodeURIComponent(id)}`, undefined, 'DELETE'),
  saveRouting: (p: any) => req<any>('/api/settings/routing', p),
  testProvider: (p: any) => req<any>('/api/settings/test-provider', p),

  glossary: (text: string) => req<any>('/api/manuscript/glossary', { text }),
  corpus: (query: string, section?: string, k = 6) => req<any>('/api/manuscript/corpus', { query, section, k }),
  typography: (text: string, mode = 'auto', cjk_latin_space = false) =>
    req<any>('/api/manuscript/typography', { text, mode, cjk_latin_space }),
  outline: (text: string) => req<any>('/api/manuscript/outline', { text }),
  importArxiv: (arxiv_id: string) => req<any>('/api/manuscript/import-arxiv', { arxiv_id }),
  importFile: (file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return upload<any>('/api/manuscript/import-file', fd);
  },

  workspaceOpenFolder: (folder_path: string, expand_inputs = false) =>
    req<any>('/api/workspace/open-folder', { folder_path, expand_inputs }),
  workspaceImportZip: (file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return upload<any>('/api/workspace/import-zip', fd);
  },
  workspaceImportFiles: (projectName: string, items: Array<{ file: File; rel: string }>) => {
    const fd = new FormData();
    fd.append('project_name', projectName);
    items.forEach(({ file, rel }) => {
      fd.append('files', file);
      fd.append('rel_paths', rel);
    });
    return upload<any>('/api/workspace/import-files', fd);
  },
  workspaceReadFile: (rel: string, expand_inputs = false) =>
    req<any>(`/api/workspace/read-file?rel=${encodeURIComponent(rel)}&expand_inputs=${expand_inputs ? 'true' : 'false'}`, undefined, 'GET'),
  workspaceSaveFile: (rel: string, content: string, preamble = '') =>
    req<any>('/api/workspace/save-file', { rel, content, preamble }),
  workspaceFigurePatcher: (rel: string) => req<any>('/api/workspace/figure-patcher', { rel }),
  workspaceFigureDataUrl: (rel: string) => req<any>('/api/workspace/figure-data-url', { rel }),

  formulaAnalyze: (text: string) => req<any>('/api/formula/analyze', { text }),
  formulaRebuild: (blocks: any[], sync_refs = true) => req<any>('/api/formula/rebuild', { blocks, sync_refs }),

  chartAnalyze: (csv_text: string) => req<any>('/api/charts/analyze', { csv_text }),
  chartRender: (p: any) => req<any>('/api/charts/render', p),
  tableGenerate: (p: any) => req<any>('/api/tables/generate', p),

  diagramRender: (blueprint: any) => req<{ svg: string }>('/api/diagrams/render', { blueprint }),
  diagramAiAsset: (prompt: string) => req<any>('/api/diagrams/ai-asset', { prompt }),

  patcherInspect: (file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return upload<any>('/api/patcher/inspect', fd);
  },
  patcherPatchSvg: (svg: string, edits: any[]) => req<any>('/api/patcher/patch-svg', { svg, edits }),
  patcherPatchRaster: (image_b64: string, boxes: any[]) => req<any>('/api/patcher/patch-raster', { image_b64, boxes }),

  glossaryList: () => req<{ terms: any[] }>('/api/glossary', undefined, 'GET'),
  glossaryUpsert: (p: { en: string; zh: string; keep_en?: boolean; note?: string }) => req<any>('/api/glossary', p),
  glossaryDelete: (en: string) => req<any>('/api/glossary/delete', { en }),
  searchWeb: (query: string, max_results = 5) => req<any>('/api/search/web', { query, max_results }),
  searchTerm: (term: string, domain = '多模态深度学习') => req<any>('/api/search/term', { term, domain }),

  citationsAudit: (manuscript: string, bibtex: string, verify_online = false) =>
    req<any>('/api/citations/audit', { manuscript, bibtex, verify_online }),

  listCorpusPacks: () => req<any>('/api/corpus/packs', undefined, 'GET'),
  createCorpusPack: (p: any) => req<any>('/api/corpus/packs', p),
  updateCorpusPack: (id: string, p: { enabled?: boolean; weight?: number }) =>
    req<any>(`/api/corpus/packs/${encodeURIComponent(id)}`, p, 'PATCH'),
  deleteCorpusPack: (id: string) => req<any>(`/api/corpus/packs/${encodeURIComponent(id)}`, undefined, 'DELETE'),
  ingestPackFiles: (id: string, files: FileList, venue: string, year: number, group: string) => {
    const fd = new FormData();
    Array.from(files).forEach((f) => fd.append('files', f));
    fd.append('venue', venue);
    fd.append('year', String(year));
    fd.append('group', group);
    return upload<any>(`/api/corpus/packs/${encodeURIComponent(id)}/ingest-files`, fd);
  },
  ingestPackArxiv: (id: string, arxiv_ids: string[], venue: string, year: number, group: string) =>
    req<any>(`/api/corpus/packs/${encodeURIComponent(id)}/ingest-arxiv`, { arxiv_ids, venue, year, group }),
  ingestPackText: (id: string, p: { title: string; content: string; venue: string; year: number; group: string }) =>
    req<any>(`/api/corpus/packs/${encodeURIComponent(id)}/ingest-text`, p),
  distillPack: (id: string) => req<any>(`/api/corpus/packs/${encodeURIComponent(id)}/distill`, {}),
  buildPackVectors: (id: string) => req<any>(`/api/corpus/packs/${encodeURIComponent(id)}/build-vectors`, {}),
  importPackZip: (file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return upload<any>('/api/corpus/packs/import-zip', fd);
  },
  recordFeedback: (p: {
    original: string;
    revised: string;
    tag: string;
    reason: string;
    decision: 'accepted' | 'rejected';
    venue: string;
    mode: string;
  }) => req<any>('/api/corpus/feedback', p).catch(() => {}),
};

async function readSse(url: string, payload: unknown, onEvent: (evt: any) => void, signal?: AbortSignal): Promise<void> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  });
  if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const parts = buf.split('\n\n');
    buf = parts.pop() || '';
    for (const chunk of parts) {
      const line = chunk.split('\n').find((l) => l.startsWith('data:'));
      if (!line) continue;
      try {
        onEvent(JSON.parse(line.slice(5).trim()));
      } catch {
        // ignore partial JSON
      }
    }
  }
}

export const streamAgent = (
  payload: { mode: string; text: string; instruction?: string; section?: string; venue?: string },
  onEvent: (evt: any) => void,
) => readSse('/api/agent/stream', payload, onEvent);

export const streamDiagramAgents = (
  payload: {
    method_text: string;
    venue_theme: string;
    concurrency: number;
    generate_ai_icons?: boolean;
    layout_mode?: string;
    custom_colors?: Record<string, string>;
  },
  onEvent: (evt: any) => void,
) => readSse('/api/diagrams/generate-stream', payload, onEvent);

export const streamOmniChat = (
  payload: {
    messages: Array<{ role: string; content: string; images?: string[] }>;
    context: Record<string, any>;
    enable_thinking?: boolean;
  },
  onEvent: (evt: any) => void,
  signal?: AbortSignal,
) => readSse('/api/chat/stream', payload, onEvent, signal);
