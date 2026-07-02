/**
 * Render the paginated screenplay into printable US-Letter pages and invoke the
 * browser's print → "Save as PDF". A hidden #lf-print-root holds the pages; the
 * print stylesheet (app.css, body.lf-paginating) swaps the app out for it.
 */

import { paginateScreenplay, type ScreenplayPage } from './screenplayPaginate';
import type { FountainBlock } from './fountainTypes';

function esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function renderPage(page: ScreenplayPage): string {
  const num = page.number > 1 ? `<div class="pp-pagenum">${page.number}.</div>` : '';
  const rows = page.lines
    .map((l) => {
      if (!l) return '<div class="pp-row"></div>';
      if (l.align === 'right') return `<div class="pp-row pp-right">${esc(l.text)}</div>`;
      return `<div class="pp-row" style="padding-left:${l.col}ch">${esc(l.text)}</div>`;
    })
    .join('');
  return `<div class="pp-page">${num}${rows}</div>`;
}

/** Build the print DOM, print, then clean it up. */
export function printScreenplayPdf(blocks: FountainBlock[]): void {
  if (typeof document === 'undefined') return;
  const pages = paginateScreenplay(blocks);
  const root = document.createElement('div');
  root.id = 'lf-print-root';
  root.innerHTML = pages.map(renderPage).join('');
  document.body.appendChild(root);
  document.body.classList.add('lf-paginating');

  let done = false;
  const cleanup = () => {
    if (done) return;
    done = true;
    document.body.classList.remove('lf-paginating');
    root.remove();
    window.removeEventListener('afterprint', cleanup);
  };
  window.addEventListener('afterprint', cleanup);
  // Safety net if afterprint never fires (some embedded browsers).
  setTimeout(cleanup, 60000);

  window.print();
}
