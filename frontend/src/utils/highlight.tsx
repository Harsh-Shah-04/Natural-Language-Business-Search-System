import type { ReactNode } from 'react';

/** Escape a string so it can be used as a literal inside a RegExp. */
function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Wrap occurrences of the query's terms in `<mark>` for highlighting.
 *
 * XSS-safe by construction: the source text is split on the terms and the
 * pieces are returned as React text nodes / elements — never injected as HTML
 * (no dangerouslySetInnerHTML). Matching is case-insensitive and per-term, so
 * a multi-word query highlights each word independently. Terms shorter than 2
 * characters are ignored to avoid highlighting noise.
 */
export function highlightText(text: string, query: string): ReactNode {
  const terms = query
    .trim()
    .split(/\s+/)
    .filter((term) => term.length >= 2);

  if (terms.length === 0) return text;

  const lowered = new Set(terms.map((term) => term.toLowerCase()));
  const pattern = new RegExp(`(${terms.map(escapeRegExp).join('|')})`, 'gi');

  // String.split with a capturing group keeps the matched delimiters as
  // separate array entries, so the pieces that equal a term (case-insensitively)
  // are exactly the ones to mark.
  const pieces = text.split(pattern);
  return pieces.map((piece, index) =>
    lowered.has(piece.toLowerCase()) ? (
      <mark className="hl" key={index}>
        {piece}
      </mark>
    ) : (
      piece
    ),
  );
}
