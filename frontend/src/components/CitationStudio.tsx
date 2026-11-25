import React, { useEffect, useState } from 'react';
import { AlertCircle, BookMarked, CheckCircle2, ExternalLink, Globe, Loader2, ShieldAlert } from 'lucide-react';
import { api } from '../api';
import { I18nDict, Lang } from '../i18n';

interface Props {
  lang: Lang;
  t: I18nDict;
  manuscript: string;
  bibtex: string;
  onBibtexChange: (b: string) => void;
  onNotify: (msg: string) => void;
}

export const CitationStudio: React.FC<Props> = ({ lang, t, manuscript, bibtex, onBibtexChange, onNotify }) => {
  const [report, setReport] = useState<any>(null);
  const [verifying, setVerifying] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => {
      api.citationsAudit(manuscript, bibtex, false).then(setReport).catch(() => {});
    }, 250);
    return () => clearTimeout(timer);
  }, [manuscript, bibtex]);

  const handleVerify = async () => {
    setVerifying(true);
    try {
      const res = await api.citationsAudit(manuscript, bibtex, true);
      setReport(res);
      const okCount = (res.verified_entries || []).filter((e: any) => e.status === 'verified').length;
      onNotify(lang === 'zh' ? `Crossref 核验完成：${okCount}/${res.bib_count} 篇真实匹配` : `Crossref verified ${okCount}/${res.bib_count}`);
    } catch (e: any) {
      onNotify(e.message);
    } finally {
      setVerifying(false);
    }
  };

  const entries = report?.verified_entries || report?.entries || [];

  return (
    <div className="studio-split-wide">
      <aside className="control-sidebar">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span className="eyebrow">{t.bib_lib}</span>
          <span className="badge badge-neutral">{report?.bib_count || 0}</span>
        </div>
        <textarea className="textarea mono" style={{ flex: 1, minHeight: 400 }} value={bibtex} onChange={(e) => onBibtexChange(e.target.value)} />
        <button className="btn btn-primary" onClick={handleVerify} disabled={verifying}>
          {verifying ? <Loader2 size={14} className="spin" /> : <Globe size={14} />}
          {verifying ? t.verifying : t.verify_crossref}
        </button>
      </aside>

      <main className="canvas-area">
        <div className="card" style={{ padding: '18px 22px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
            <div>
              <div style={{ fontFamily: 'var(--font-serif)', fontSize: 19, fontWeight: 600 }}>{t.cit_title}</div>
              <div style={{ fontSize: 12, color: 'var(--ink-secondary)' }}>{t.cit_sub}</div>
            </div>
            <BookMarked size={20} color="var(--accent)" />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
            {[
              [lang === 'zh' ? '正文引用' : 'Cited', report?.cited_count ?? 0, 'var(--ink-primary)'],
              [lang === 'zh' ? 'BibTeX 条目' : 'BibTeX', report?.bib_count ?? 0, 'var(--ink-primary)'],
              [lang === 'zh' ? '缺失文献' : 'Missing', report?.missing_in_bib?.length ?? 0, (report?.missing_in_bib?.length ?? 0) > 0 ? 'var(--vermilion)' : 'var(--sage)'],
              [lang === 'zh' ? '未引用冗余' : 'Unused', report?.unused_in_text?.length ?? 0, (report?.unused_in_text?.length ?? 0) > 0 ? 'var(--amber)' : 'var(--sage)'],
            ].map(([label, val, color]: any) => (
              <div key={label} className="card" style={{ padding: '10px 12px', background: 'var(--bg-subtle)' }}>
                <div className="eyebrow">{label}</div>
                <div style={{ fontSize: 22, fontWeight: 700, fontFamily: 'var(--font-serif)', color, marginTop: 2 }}>{val}</div>
              </div>
            ))}
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {entries.map((e: any) => {
            const st = e.status || 'local';
            return (
              <div key={e.key} className="card" style={{ padding: '13px 16px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginBottom: 5 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <code style={{ fontSize: 12, fontWeight: 600, color: 'var(--accent)' }}>{e.key}</code>
                    <span className="badge badge-neutral">@{e.type}</span>
                    {e.year && <span className="badge badge-neutral">{e.year}</span>}
                  </div>
                  {st === 'verified' && (
                    <span className="badge badge-sage">
                      <CheckCircle2 size={12} /> {lang === 'zh' ? '已核验' : 'Verified'} ({Math.round((e.confidence || 1) * 100)}%)
                    </span>
                  )}
                  {(st === 'mismatch' || st === 'partial') && (
                    <span className="badge badge-amber">
                      <AlertCircle size={12} /> {lang === 'zh' ? '年份/标题存疑' : 'Mismatch'}
                    </span>
                  )}
                  {st === 'not_found' && (
                    <span className="badge badge-vermilion">
                      <ShieldAlert size={12} /> {lang === 'zh' ? '未检索到' : 'Not Found'}
                    </span>
                  )}
                  {st === 'local' && <span className="badge badge-neutral">{lang === 'zh' ? '待联网核验' : 'Pending'}</span>}
                </div>
                <div style={{ fontFamily: 'var(--font-serif)', fontSize: 15, fontWeight: 500 }}>{e.title || '(Untitled)'}</div>
                <div style={{ fontSize: 11.8, color: 'var(--ink-secondary)', marginTop: 2 }}>
                  {e.author} {e.venue ? `· ${e.venue}` : ''}
                </div>
                {e.note && (
                  <div style={{ fontSize: 11.5, color: st === 'verified' ? 'var(--sage)' : 'var(--ink-muted)', marginTop: 6, display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span>{e.note}</span>
                    {e.matched_doi && (
                      <a href={`https://doi.org/${e.matched_doi}`} target="_blank" rel="noreferrer" style={{ color: 'var(--accent)', display: 'inline-flex', alignItems: 'center', gap: 3, textDecoration: 'none' }}>
                        DOI <ExternalLink size={11} />
                      </a>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </main>
    </div>
  );
};
