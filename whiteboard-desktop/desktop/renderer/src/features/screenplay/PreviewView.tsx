/** Readable Screenplay Preview — renders the pure buildPreview() output.
 *  (File named PreviewView to avoid a case-only clash with screenplayPreview.ts.) */

import { Fragment } from 'react';

import type { DocumentSettings } from '../whiteboard/documentSettings';
import type { WhiteboardBlock } from '../whiteboard/types';
import { toFountainBlocks } from './screenplayExport';
import { buildPreview, groupPreviewItems, previewSegments, type PreviewLine } from './screenplayPreview';

function Inline({ text }: { text: string }) {
  const segs = previewSegments(text);
  if (segs.length === 0) return <>{' '}</>; // keep empty lines from collapsing
  return (
    <>
      {segs.map((s, i) => {
        if (s.cls === 'sp-bold') return <strong key={i}>{s.text}</strong>;
        if (s.cls === 'sp-italic') return <em key={i}>{s.text}</em>;
        if (s.cls === 'sp-bold-italic')
          return (
            <strong key={i}>
              <em>{s.text}</em>
            </strong>
          );
        if (s.cls === 'sp-underline') return <u key={i}>{s.text}</u>;
        return <span key={i}>{s.text}</span>;
      })}
    </>
  );
}

function Line({ line }: { line: PreviewLine }) {
  return (
    <p className={`sp-${line.type}`}>
      <Inline text={line.text} />
    </p>
  );
}

const cap = (k: string) => k.charAt(0).toUpperCase() + k.slice(1);
// Fields rendered in their own slots; everything else falls to the meta block.
const NAMED = new Set(['title', 'credit', 'author', 'authors', 'draft date', 'date']);

interface Props {
  blocks: WhiteboardBlock[];
  settings: DocumentSettings;
}

export function PreviewView({ blocks, settings }: Props) {
  const preview = buildPreview(toFountainBlocks(blocks), settings);
  const fields = preview.titlePage;
  const keys = Object.keys(fields);
  const author = fields.author ?? fields.authors;
  const draft = fields['draft date'] ?? fields.date;
  // Meta = leftover keys with a non-empty value; only show the page if some
  // slot actually has content (a bare "Title:" must not render an empty page).
  const metaKeys = keys.filter((k) => !NAMED.has(k) && fields[k]?.trim());
  const hasTitlePage = !!(fields.title || fields.credit || author || draft) || metaKeys.length > 0;
  const items = groupPreviewItems(preview.lines);
  // Preserve indented multi-line title-page continuations (parser joins with \n).
  const pre = { whiteSpace: 'pre-line' as const };

  return (
    <div className="wb-preview" role="document" aria-label="Screenplay preview">
      {hasTitlePage && (
        <div className="sp-titlepage">
          {fields.title && <div className="sp-pv-title" style={pre}>{fields.title}</div>}
          {fields.credit && <div className="sp-pv-credit" style={pre}>{fields.credit}</div>}
          {author && <div className="sp-pv-author" style={pre}>{author}</div>}
          {metaKeys.length > 0 && (
            <div className="sp-pv-meta">
              {metaKeys.map((k) => (
                <div key={k} style={pre}>
                  {cap(k)}: {fields[k]}
                </div>
              ))}
            </div>
          )}
          {draft && <div className="sp-pv-draft" style={pre}>{draft}</div>}
        </div>
      )}
      <div className="sp-pv-body">
        {items.length === 0 ? (
          <p className="sp-pv-empty">Nothing to preview yet.</p>
        ) : (
          items.map((item, i) => {
            if (item.kind === 'dual') {
              return (
                <div key={i} className="sp-dual-dialogue">
                  <div className="sp-dual-col">
                    {item.left.map((l, j) => (
                      <Line key={j} line={l} />
                    ))}
                  </div>
                  <div className="sp-dual-col">
                    {item.right.map((l, j) => (
                      <Line key={j} line={l} />
                    ))}
                  </div>
                </div>
              );
            }
            if (item.kind === 'block') {
              return (
                <Fragment key={i}>
                  {item.lines.map((l, j) => (
                    <Line key={j} line={l} />
                  ))}
                </Fragment>
              );
            }
            return <Line key={i} line={item.line} />;
          })
        )}
      </div>
    </div>
  );
}
