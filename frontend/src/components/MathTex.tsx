import React, { useMemo } from 'react';
import katex from 'katex';
import 'katex/dist/katex.min.css';

interface Props {
  tex: string;
  display?: boolean;
  className?: string;
}

export const MathTex: React.FC<Props> = ({ tex, display = false, className }) => {
  const html = useMemo(() => {
    try {
      return katex.renderToString(tex, {
        displayMode: display,
        throwOnError: false,
        strict: false,
      });
    } catch {
      return tex;
    }
  }, [tex, display]);

  return (
    <span
      className={className}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
};

/** Render inline prose containing $...$ math, \cite{}, \ref{}, and live workspace \includegraphics{} figures. */
export const TypesetParagraph: React.FC<{
  text: string;
  hasWorkspace?: boolean;
  onPatchWorkspaceFigure?: (ref: string) => void;
}> = ({ text, hasWorkspace, onPatchWorkspaceFigure }) => {
  // Detect \includegraphics[...]{path} inside figure blocks and render real preview from mounted LaTeX workspace
  const figMatches = useMemo(() => {
    const found: Array<{ ref: string; caption: string }> = [];
    const re = /\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}/g;
    let m: RegExpExecArray | null;
    const capMatch = text.match(/\\caption(?:\[[^\]]*\])?\{([\s\S]*?)\}/);
    const caption = capMatch ? capMatch[1].replace(/\s+/g, ' ').trim() : '';
    while ((m = re.exec(text)) !== null) {
      found.push({ ref: m[1].trim(), caption });
    }
    return found;
  }, [text]);

  const cleanedText = useMemo(() => {
    if (!figMatches.length) return text;
    return text
      .replace(/\\begin\{figure\*?\}(?:\[[^\]]*\])?|\\end\{figure\*?\}|\\centering|\\includegraphics(?:\[[^\]]*\])?\{[^}]+\}|\\caption(?:\[[^\]]*\])?\{[\s\S]*?\}|\\label\{[^}]+\}/g, '')
      .trim();
  }, [text, figMatches.length]);

  const tokens = useMemo(() => {
    const src = cleanedText;
    const out: Array<{ kind: 'text' | 'math' | 'cite' | 'ref'; val: string }> = [];
    const re = /(\$[^$\n]+\$|\\cite[a-zA-Z]*\*?(?:\[[^\]]*\])*\{[^}]+\}|\\(?:ref|eqref|Cref)\{[^}]+\})/g;
    let last = 0;
    let m: RegExpExecArray | null;
    while ((m = re.exec(src)) !== null) {
      if (m.index > last) out.push({ kind: 'text', val: src.slice(last, m.index) });
      const tok = m[0];
      if (tok.startsWith('$')) {
        out.push({ kind: 'math', val: tok.slice(1, -1) });
      } else if (tok.startsWith('\\cite')) {
        const inner = tok.match(/\{([^}]+)\}/)?.[1] || tok;
        out.push({ kind: 'cite', val: inner });
      } else {
        const inner = tok.match(/\{([^}]+)\}/)?.[1] || tok;
        out.push({ kind: 'ref', val: inner });
      }
      last = m.index + tok.length;
    }
    if (last < src.length) out.push({ kind: 'text', val: src.slice(last) });
    return out;
  }, [cleanedText]);

  return (
    <>
      {figMatches.map((fg, fi) => (
        <figure
          key={`fig-${fi}`}
          style={{
            margin: '14px 0',
            padding: '12px 14px',
            borderRadius: 10,
            border: '1px solid var(--border-hairline)',
            background: '#fff',
            textAlign: 'center',
          }}
        >
          {hasWorkspace ? (
            <img
              src={`/api/workspace/asset?ref=${encodeURIComponent(fg.ref)}`}
              alt={fg.ref}
              style={{ maxWidth: '100%', maxHeight: 420, height: 'auto', borderRadius: 6, display: 'block', margin: '0 auto 8px' }}
            />
          ) : (
            <div style={{ padding: '18px 10px', fontSize: 12, color: 'var(--ink-muted)', background: 'var(--bg-subtle)', borderRadius: 6, marginBottom: 8 }}>
              图片引用：{fg.ref}（拖入整个 LaTeX 文件夹后可实时预览）
            </div>
          )}
          <figcaption style={{ fontSize: 12.5, color: 'var(--ink-secondary)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, textAlign: 'left', flexWrap: 'wrap' }}>
            <span>
              <strong style={{ color: 'var(--ink-primary)' }}>{fg.ref}</strong>
              {fg.caption ? ` · ${fg.caption}` : ''}
            </span>
            {hasWorkspace && onPatchWorkspaceFigure && (
              <button className="btn btn-sm" style={{ height: 26, fontSize: 11.5 }} onClick={() => onPatchWorkspaceFigure(fg.ref)}>
                安全改图文字
              </button>
            )}
          </figcaption>
        </figure>
      ))}
      {cleanedText && (
        <p>
          {tokens.map((t, i) => {
            if (t.kind === 'math') return <MathTex key={i} tex={t.val} display={false} />;
            if (t.kind === 'cite') {
              return (
                <span
                  key={i}
                  style={{
                    fontFamily: 'var(--font-sans)',
                    fontSize: '11.5px',
                    color: 'var(--accent)',
                    background: 'var(--accent-soft)',
                    padding: '1px 6px',
                    borderRadius: '4px',
                    margin: '0 2px',
                  }}
                >
                  [{t.val}]
                </span>
              );
            }
            if (t.kind === 'ref') {
              return (
                <span
                  key={i}
                  style={{
                    fontFamily: 'var(--font-sans)',
                    fontSize: '12px',
                    color: 'var(--violet)',
                    fontWeight: 500,
                  }}
                >
                  ({t.val})
                </span>
              );
            }
            return <React.Fragment key={i}>{t.val}</React.Fragment>;
          })}
        </p>
      )}
    </>
  );
};
