import React, { useEffect, useMemo, useState } from 'react';
import {
  BookOpen,
  CheckCircle2,
  Cpu,
  Globe,
  KeyRound,
  Layers,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  Server,
  Trash2,
  X,
  Zap,
} from 'lucide-react';
import { api } from '../api';
import { I18nDict, Lang } from '../i18n';
import { ProviderConfig, SettingsPayload } from '../types';

interface Props {
  open: boolean;
  initialTab?: TabKey;
  lang: Lang;
  t: I18nDict;
  settings: SettingsPayload;
  onClose: () => void;
  onRefresh: () => Promise<void>;
  onNotify: (msg: string) => void;
}

export type TabKey = 'domestic' | 'international' | 'local' | 'routing' | 'glossary_search';

export const ModelHubModal: React.FC<Props> = ({ open, initialTab, lang, t, settings, onClose, onRefresh, onNotify }) => {
  const [tab, setTab] = useState<TabKey>(initialTab || 'domestic');
  const [selectedId, setSelectedId] = useState<string>('deepseek');
  const [keyInput, setKeyInput] = useState('');
  const [urlInput, setUrlInput] = useState('');
  const [protoInput, setProtoInput] = useState<'openai' | 'anthropic' | 'anthropic_relay' | 'gemini_native'>('openai');
  const [modelInput, setModelInput] = useState('');
  const [fetchedModels, setFetchedModels] = useState<string[]>([]);
  const [fetching, setFetching] = useState(false);
  const [testInfo, setTestInfo] = useState<{ ok: boolean; msg: string } | null>(null);

  // Quick inline 3rd-party creator
  const [addingCustom, setAddingCustom] = useState(false);
  const [customName, setCustomName] = useState('');

  // Multimodal DL Glossary & Multi-Provider Web Search
  const [searchProvider, setSearchProvider] = useState<string>(settings.search?.provider || 'builtin_free');
  const [searchKey, setSearchKey] = useState('');
  const [styleStrength, setStyleStrength] = useState<string>(settings.preferences?.style_strength || 'balanced');
  const [firstMentionEn, setFirstMentionEn] = useState<boolean>(settings.preferences?.first_mention_en ?? true);
  const [glossary, setGlossary] = useState<Array<{ en: string; zh: string; keep_en?: boolean; note?: string; custom?: boolean }>>([]);
  const [termQuery, setTermQuery] = useState('');
  const [termLookupRes, setTermLookupRes] = useState<any>(null);
  const [lookingUp, setLookingUp] = useState(false);
  const [newEn, setNewEn] = useState('');
  const [newZh, setNewZh] = useState('');

  useEffect(() => {
    if (open && initialTab) setTab(initialTab);
  }, [open, initialTab]);

  useEffect(() => {
    if (open && tab === 'glossary_search') {
      api.glossaryList().then((r) => setGlossary(r.terms || [])).catch(() => {});
    }
  }, [open, tab]);

  const filteredProviders = useMemo(() => {
    if (tab === 'domestic') return settings.providers.filter((p) => p.region === 'domestic');
    if (tab === 'local') return settings.providers.filter((p) => p.region === 'local');
    return settings.providers.filter((p) => p.region === 'international' || p.region === 'custom');
  }, [settings.providers, tab]);

  const activeProvider: ProviderConfig | undefined = useMemo(
    () => settings.providers.find((p) => p.id === selectedId) || filteredProviders[0],
    [settings.providers, selectedId, filteredProviders],
  );

  if (!open) return null;

  const selectProvider = (p: ProviderConfig) => {
    setAddingCustom(false);
    setSelectedId(p.id);
    setKeyInput('');
    setUrlInput(p.base_url);
    setProtoInput(p.protocol);
    setModelInput(p.default_model || p.models[0] || '');
    setFetchedModels(p.models || []);
    setTestInfo(null);
  };

  const startNewCustom = () => {
    setAddingCustom(true);
    setCustomName(lang === 'zh' ? '第三方中转 API' : 'Custom Relay API');
    setUrlInput('');
    setKeyInput('');
    setProtoInput('anthropic_relay');
    setModelInput('');
    setFetchedModels([]);
    setTestInfo(null);
  };

  const handleFetchModels = async () => {
    const base_url = addingCustom ? urlInput : urlInput || activeProvider?.base_url || '';
    const protocol = addingCustom ? protoInput : protoInput || activeProvider?.protocol || 'openai';
    setFetching(true);
    setTestInfo(null);
    try {
      const res = await api.testProvider({
        provider_id: addingCustom ? undefined : activeProvider?.id,
        base_url,
        api_key: keyInput || undefined,
        protocol,
      });
      if (res.ok) {
        const list: string[] = res.models || [];
        setFetchedModels(list);
        if (list.length > 0 && !list.includes(modelInput)) {
          setModelInput(list[0]);
        }
        setTestInfo({
          ok: true,
          msg: lang === 'zh'
            ? `连接成功（${res.latency_ms}ms），已实时拉取 ${list.length} 个模型`
            : `Connected (${res.latency_ms}ms) — fetched ${list.length} models`,
        });
        if (!addingCustom) await onRefresh();
      } else {
        setTestInfo({
          ok: false,
          msg: lang === 'zh'
            ? `拉取失败（${res.latency_ms}ms）：${res.error}。若该中转站隐藏了 /models，可直接手填模型 ID 后保存。`
            : `Fetch failed (${res.latency_ms}ms): ${res.error}. You can still enter a model ID manually.`,
        });
      }
    } finally {
      setFetching(false);
    }
  };

  const handleSave = async () => {
    const id = addingCustom ? `custom_${Date.now().toString(36)}` : activeProvider?.id;
    if (!id) return;
    const base = (urlInput || activeProvider?.base_url || '').trim();
    if (!base) {
      onNotify(lang === 'zh' ? '请填写接口 Base URL' : 'Please enter Base URL');
      return;
    }
    const models = fetchedModels.length
      ? fetchedModels
      : modelInput.trim()
        ? [modelInput.trim()]
        : activeProvider?.models || [];
    const chosenModel = modelInput.trim() || models[0] || '';

    await api.saveProvider({
      id,
      name: addingCustom ? customName.trim() || 'Custom API' : activeProvider?.name,
      region: addingCustom ? 'custom' : activeProvider?.region,
      protocol: protoInput,
      base_url: base,
      api_key: keyInput || undefined,
      models,
      default_model: chosenModel,
    });

    if (keyInput || addingCustom || chosenModel) {
      await api.saveRouting({
        routing: { writing: { provider_id: id, model: chosenModel } },
      });
    }

    setKeyInput('');
    setAddingCustom(false);
    setSelectedId(id);
    await onRefresh();
    onNotify(lang === 'zh' ? '已保存本地配置并设为当前写作模型' : 'Saved locally and activated for writing');
  };

  const handleRoutingChange = async (role: 'writing' | 'vision' | 'image', provider_id: string, model?: string) => {
    const prov = settings.providers.find((p) => p.id === provider_id);
    const chosen = model ?? prov?.default_model ?? prov?.models[0] ?? '';
    await api.saveRouting({ routing: { [role]: { provider_id, model: chosen } } });
    await onRefresh();
    onNotify(lang === 'zh' ? '已更新角色模型路由' : `Updated ${role} route`);
  };

  const availableModels = fetchedModels.length ? fetchedModels : activeProvider?.models || [];

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card" role="dialog" aria-modal="true" aria-label={t.hub_title} onClick={(e) => e.stopPropagation()}>
        <div className="panel-header" style={{ padding: '14px 20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <KeyRound size={17} color="var(--accent)" />
            <div>
              <div style={{ fontFamily: 'var(--font-serif)', fontSize: 18, fontWeight: 600 }}>{t.hub_title}</div>
              <div style={{ fontSize: 11.5, color: 'var(--ink-muted)' }}>{t.hub_sub}</div>
            </div>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>

        {/* Category Tabs */}
        <div
          style={{
            padding: '10px 20px',
            borderBottom: '1px solid var(--border-hairline)',
            background: 'var(--bg-subtle)',
            display: 'flex',
            gap: 8,
            flexWrap: 'wrap',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {(
              [
                ['domestic', t.hub_domestic, Zap],
                ['international', t.hub_intl, Globe],
                ['local', t.hub_local, Server],
                ['routing', t.hub_routing, Layers],
                ['glossary_search', lang === 'zh' ? '术语与联网搜索' : 'Glossary & Search', BookOpen],
              ] as const
            ).map(([k, label, Icon]) => (
              <button
                key={k}
                className={`seg-btn ${tab === k ? 'active' : ''}`}
                style={{ height: 30, padding: '0 12px', border: tab === k ? '1px solid var(--border-hairline)' : '1px solid transparent' }}
                onClick={() => {
                  setTab(k);
                  setAddingCustom(false);
                  setTestInfo(null);
                  const list = settings.providers.filter((p) =>
                    k === 'domestic' ? p.region === 'domestic' : k === 'local' ? p.region === 'local' : p.region === 'international' || p.region === 'custom',
                  );
                  if (list[0]) selectProvider(list[0]);
                }}
              >
                <Icon size={13.5} /> {label}
              </button>
            ))}
          </div>
          <button
            className="btn btn-primary btn-sm"
            style={{ height: 30 }}
            onClick={() => {
              setTab('international');
              startNewCustom();
            }}
          >
            <Plus size={13.5} /> {t.add_custom}
          </button>
        </div>

        {/* Body */}
        <div style={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex' }}>
          {tab === 'glossary_search' ? (
            <div className="view-fade" style={{ flex: 1, overflowY: 'auto', padding: 20, display: 'flex', flexDirection: 'column', gap: 14 }}>
              {/* Search Engine + Fluency Preferences */}
              <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <strong style={{ fontSize: 13.5 }}>{lang === 'zh' ? '联网搜索引擎 & 翻译流畅度设置' : 'Web Search & Translation Fluency'}</strong>
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={async () => {
                      await api.saveRouting({
                        search: { provider: searchProvider, ...(searchKey ? { api_key: searchKey } : {}) },
                        preferences: { style_strength: styleStrength, first_mention_en: firstMentionEn },
                      });
                      setSearchKey('');
                      await onRefresh();
                      onNotify(lang === 'zh' ? '已保存联网搜索与翻译流畅度配置' : 'Saved search & fluency settings');
                    }}
                  >
                    {lang === 'zh' ? '保存设置' : 'Save'}
                  </button>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
                  <div>
                    <label className="field-label">{lang === 'zh' ? '联网搜索方式（Agent 与查术语共用）' : 'Web Search Engine'}</label>
                    <select className="select" value={searchProvider} onChange={(e) => setSearchProvider(e.target.value)}>
                      <option value="builtin_free">内置免 Key 学术搜索（Bing + arXiv · 默认）</option>
                      <option value="bocha">博查 Bocha AI 搜索（国内极速）</option>
                      <option value="tavily">Tavily Search API</option>
                      <option value="serper">Serper (Google Search API)</option>
                    </select>
                  </div>
                  <div>
                    <label className="field-label">{lang === 'zh' ? '自定义搜索 API Key（免 Key 留空）' : 'Search API Key (Optional)'}</label>
                    <input
                      className="input mono"
                      type="password"
                      value={searchKey}
                      onChange={(e) => setSearchKey(e.target.value)}
                      placeholder={settings.search?.has_key ? settings.search.api_key_masked : '选择第三方搜索时填写'}
                    />
                  </div>
                  <div>
                    <label className="field-label">{lang === 'zh' ? '向量例句参考强度（防生硬缝合）' : 'Corpus Style Strength'}</label>
                    <select className="select" value={styleStrength} onChange={(e) => setStyleStrength(e.target.value)}>
                      <option value="natural">自然流畅优先（不塞例句，仅守术语表）</option>
                      <option value="balanced">平衡参考（默认 · 仅阈值精选 2-3 条）</option>
                      <option value="venue_strict">强顶会风格对齐（英文润色/仿写）</option>
                    </select>
                  </div>
                </div>
                <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12.5, color: 'var(--ink-secondary)', cursor: 'pointer' }}>
                  <input type="checkbox" checked={firstMentionEn} onChange={(e) => setFirstMentionEn(e.target.checked)} />
                  {lang === 'zh' ? '英译中时首次出现专业术语自动括注原文（例：交叉注意力（cross-attention）），且自动关闭英文向量库防翻译腔' : 'Bracket English term on first mention & isolate English corpus on EN->ZH'}
                </label>
              </div>

              {/* Online Term Lookup */}
              <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
                <strong style={{ fontSize: 13.5 }}>{lang === 'zh' ? '生词联网查证（多模态深度学习默认）' : 'Online Term Lookup'}</strong>
                <div style={{ display: 'flex', gap: 8 }}>
                  <input
                    className="input"
                    value={termQuery}
                    onChange={(e) => setTermQuery(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && termQuery.trim()) {
                        setLookingUp(true);
                        api.searchTerm(termQuery.trim()).then(setTermLookupRes).finally(() => setLookingUp(false));
                      }
                    }}
                    placeholder={lang === 'zh' ? '输入首次见到的英文术语（如 robustness / flow matching / token pruning）...' : 'Enter unfamiliar English term...'}
                  />
                  <button
                    className="btn btn-primary"
                    disabled={lookingUp || !termQuery.trim()}
                    onClick={() => {
                      setLookingUp(true);
                      api.searchTerm(termQuery.trim()).then(setTermLookupRes).finally(() => setLookingUp(false));
                    }}
                  >
                    {lookingUp ? <Loader2 size={14} className="spin" /> : <Search size={14} />}
                    {lang === 'zh' ? '联网查译法' : 'Lookup'}
                  </button>
                </div>
                {termLookupRes && (
                  <div className="view-fade" style={{ display: 'flex', flexDirection: 'column', gap: 7, background: 'var(--bg-subtle)', padding: 10, borderRadius: 8 }}>
                    <div style={{ fontSize: 12, color: 'var(--ink-secondary)' }}>
                      来源：{termLookupRes.search_provider} · {termLookupRes.note}
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
                      {(termLookupRes.candidates || []).map((c: any, idx: number) => (
                        <button
                          key={idx}
                          className={`btn btn-sm ${c.recommended ? 'btn-primary' : ''}`}
                          onClick={async () => {
                            const r = await api.glossaryUpsert({ en: termLookupRes.term, zh: c.zh, keep_en: termLookupRes.keep_en_recommended, note: c.scene || '' });
                            setGlossary(r.terms || []);
                            onNotify(`已锁定术语：${termLookupRes.term} → ${c.zh}`);
                          }}
                          title={c.scene}
                        >
                          <Plus size={12.5} /> 锁定：{c.zh} {c.scene ? `(${c.scene})` : ''}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Personal Multimodal DL Glossary */}
              <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
                  <strong style={{ fontSize: 13.5 }}>{lang === 'zh' ? `多模态深度学习术语表（${glossary.length} 条 · 本机可随时改）` : `Multimodal DL Glossary (${glossary.length})`}</strong>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <input className="input" style={{ width: 150, height: 30 }} value={newEn} onChange={(e) => setNewEn(e.target.value)} placeholder="English term" />
                    <input className="input" style={{ width: 150, height: 30 }} value={newZh} onChange={(e) => setNewZh(e.target.value)} placeholder="锁定中文译法" />
                    <button
                      className="btn btn-primary btn-sm"
                      disabled={!newEn.trim() || !newZh.trim()}
                      onClick={async () => {
                        const r = await api.glossaryUpsert({ en: newEn.trim(), zh: newZh.trim() });
                        setGlossary(r.terms || []);
                        setNewEn('');
                        setNewZh('');
                        onNotify('已添加/覆盖术语译法');
                      }}
                    >
                      <Plus size={13} /> 添加
                    </button>
                  </div>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, maxHeight: 220, overflowY: 'auto' }}>
                  {glossary.map((it) => (
                    <div key={it.en} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6, padding: '6px 9px', borderRadius: 7, background: it.custom ? 'var(--accent-soft)' : 'var(--bg-subtle)', fontSize: 12 }}>
                      <div style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        <strong>{it.en}</strong> → {it.zh}
                      </div>
                      {it.custom && (
                        <button
                          className="btn btn-ghost btn-sm"
                          style={{ height: 22, padding: '0 4px' }}
                          onClick={async () => {
                            const r = await api.glossaryDelete(it.en);
                            setGlossary(r.terms || []);
                          }}
                        >
                          <Trash2 size={11.5} />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : tab === 'routing' ? (
            <div className="view-fade" style={{ flex: 1, overflowY: 'auto', padding: 22, display: 'flex', flexDirection: 'column', gap: 14 }}>
              {(
                [
                  ['writing', lang === 'zh' ? '学术写作、翻译与审稿' : 'Academic Writing & Review'],
                  ['vision', lang === 'zh' ? '视觉识图与图表检查' : 'Vision & Figure Analysis'],
                  ['image', lang === 'zh' ? '流程图 AI 插画生成' : 'Diagram AI Asset Generation'],
                ] as const
              ).map(([role, title]) => {
                const cur = settings.routing[role];
                const prov = settings.providers.find((p) => p.id === cur?.provider_id);
                return (
                  <div key={role} className="card" style={{ display: 'grid', gridTemplateColumns: '1fr 220px 230px', gap: 12, alignItems: 'center' }}>
                    <div style={{ fontWeight: 600, fontSize: 13 }}>{title}</div>
                    <div>
                      <label className="field-label">{lang === 'zh' ? '服务商' : 'Provider'}</label>
                      <select className="select" value={cur?.provider_id || ''} onChange={(e) => handleRoutingChange(role, e.target.value)}>
                        {settings.providers.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.name} {p.has_key || p.region === 'local' ? '●' : ''}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="field-label">{lang === 'zh' ? '模型 ID' : 'Model ID'}</label>
                      <input
                        className="input mono"
                        list={`models-${role}`}
                        value={cur?.model || ''}
                        onChange={(e) => handleRoutingChange(role, cur.provider_id, e.target.value)}
                        placeholder={lang === 'zh' ? '先在服务商页拉取模型' : 'Fetch models first'}
                      />
                      <datalist id={`models-${role}`}>
                        {(prov?.models || []).map((m) => (
                          <option key={m} value={m} />
                        ))}
                      </datalist>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <>
              {/* Company List */}
              <div
                style={{
                  width: 264,
                  borderRight: '1px solid var(--border-hairline)',
                  background: 'var(--bg-sidebar)',
                  overflowY: 'auto',
                  padding: 10,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 4,
                }}
              >
                {filteredProviders.map((p) => {
                  const isSel = !addingCustom && activeProvider?.id === p.id;
                  const ready = (p.has_key || p.region === 'local') && Boolean(p.default_model || p.models.length);
                  return (
                    <button
                      key={p.id}
                      onClick={() => selectProvider(p)}
                      style={{
                        textAlign: 'left',
                        border: isSel ? '1px solid var(--accent-border)' : '1px solid transparent',
                        background: isSel ? 'var(--bg-paper)' : 'transparent',
                        borderRadius: 8,
                        padding: '9px 11px',
                        cursor: 'pointer',
                        boxShadow: isSel ? 'var(--shadow-xs)' : 'none',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6 }}>
                        <span style={{ fontWeight: 600, fontSize: 12.5, color: 'var(--ink-primary)' }}>{p.name}</span>
                        <span className={`dot-inline ${ready ? 'online' : 'offline'}`} />
                      </div>
                      <div style={{ fontSize: 11, color: 'var(--ink-muted)', marginTop: 2, fontFamily: 'var(--font-mono)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {p.default_model || (p.models.length ? `${p.models.length} models` : lang === 'zh' ? '待填 Key 拉取模型' : 'Enter key to fetch')}
                      </div>
                    </button>
                  );
                })}
              </div>

              {/* Right Configuration Form */}
              <div className="view-fade" style={{ flex: 1, overflowY: 'auto', padding: 22, display: 'flex', flexDirection: 'column', gap: 13 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <h3 style={{ margin: 0, fontFamily: 'var(--font-serif)', fontSize: 19 }}>
                      {addingCustom ? (lang === 'zh' ? '新增第三方 / 中转 API' : 'New 3rd-Party API') : activeProvider?.name}
                    </h3>
                    {!addingCustom && activeProvider?.has_key && (
                      <span className="badge badge-sage">{activeProvider.api_key_masked}</span>
                    )}
                  </div>
                  {!addingCustom && activeProvider?.region === 'custom' && (
                    <button
                      className="btn btn-danger btn-sm"
                      onClick={async () => {
                        await api.deleteProvider(activeProvider.id);
                        await onRefresh();
                        onNotify(lang === 'zh' ? '已删除自定义接口' : 'Deleted custom provider');
                      }}
                    >
                      <Trash2 size={13} />
                    </button>
                  )}
                </div>

                {addingCustom && (
                  <div>
                    <label className="field-label">{lang === 'zh' ? '自定义名称' : 'Display Name'}</label>
                    <input className="input" value={customName} onChange={(e) => setCustomName(e.target.value)} />
                  </div>
                )}

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 220px', gap: 10 }}>
                  <div>
                    <label className="field-label">{t.base_url}</label>
                    <input
                      className="input mono"
                      value={urlInput}
                      onChange={(e) => setUrlInput(e.target.value)}
                      placeholder="https://your-relay.com/v1"
                    />
                  </div>
                  <div>
                    <label className="field-label">{t.protocol}</label>
                    <select
                      className="select"
                      value={protoInput}
                      onChange={(e) => setProtoInput(e.target.value as 'openai' | 'anthropic' | 'anthropic_relay' | 'gemini_native')}
                    >
                      <option value="openai">{t.proto_openai}</option>
                      <option value="anthropic">{t.proto_anthropic}</option>
                      <option value="anthropic_relay">{t.proto_claude_relay}</option>
                      <option value="gemini_native">Gemini 原生 (/v1beta)</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="field-label">{t.api_key}</label>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <input
                      className="input mono"
                      type="password"
                      value={keyInput}
                      onChange={(e) => setKeyInput(e.target.value)}
                      placeholder={
                        !addingCustom && activeProvider?.has_key
                          ? `${activeProvider.api_key_masked}（留空保持不变，输入新 Key 替换）`
                          : t.api_key_ph
                      }
                      onKeyDown={(e) => e.key === 'Enter' && handleFetchModels()}
                    />
                    <button className="btn btn-primary" style={{ flexShrink: 0 }} onClick={handleFetchModels} disabled={fetching}>
                      {fetching ? <Loader2 size={14} className="spin" /> : <RefreshCw size={14} />}
                      {fetching ? t.fetching : t.fetch_models}
                    </button>
                  </div>
                </div>

                <div>
                  <label className="field-label">
                    {t.model_select} {availableModels.length > 0 ? `(${availableModels.length})` : ''}
                  </label>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <input
                      className="input mono"
                      value={modelInput}
                      onChange={(e) => setModelInput(e.target.value)}
                      placeholder={t.model_manual_ph}
                    />
                    {availableModels.length > 0 && (
                      <select
                        className="select mono"
                        style={{ width: 240 }}
                        value={availableModels.includes(modelInput) ? modelInput : ''}
                        onChange={(e) => e.target.value && setModelInput(e.target.value)}
                      >
                        <option value="">{lang === 'zh' ? '从已拉取列表选择…' : 'Pick fetched model…'}</option>
                        {availableModels.map((m) => (
                          <option key={m} value={m}>
                            {m}
                          </option>
                        ))}
                      </select>
                    )}
                  </div>
                </div>

                {testInfo && (
                  <div
                    className="card"
                    style={{
                      padding: '9px 13px',
                      fontSize: 12,
                      borderColor: testInfo.ok ? 'var(--sage-border)' : 'var(--vermilion-border)',
                      background: testInfo.ok ? 'var(--sage-soft)' : 'var(--vermilion-soft)',
                      color: testInfo.ok ? 'var(--sage)' : 'var(--vermilion)',
                    }}
                  >
                    {testInfo.msg}
                  </div>
                )}

                <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
                  <button className="btn btn-primary" onClick={handleSave}>
                    <CheckCircle2 size={14} /> {t.save_activate}
                  </button>
                  {!addingCustom && activeProvider && (
                    <button
                      className="btn"
                      onClick={() => handleRoutingChange('writing', activeProvider.id, modelInput || activeProvider.default_model)}
                    >
                      <Cpu size={14} /> {t.use_writing}
                    </button>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
