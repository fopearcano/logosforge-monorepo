import { ROUTES } from '../dist/routes.js';
import { KNOWN_EVENTS } from '../dist/events.js';
import { readFileSync } from 'node:fs';

const actual = ROUTES.plotBlock(42, 'A Plot / Main');
const expected = '/api/projects/42/plot/blocks/A%20Plot%20%2F%20Main';

if (actual !== expected) {
  throw new Error(`plotBlock route mismatch: expected ${expected}, got ${actual}`);
}

const commentRoutes = [
  ROUTES.comments(42),
  ROUTES.comment(42, 7),
  ROUTES.commentReplies(42, 7),
  ROUTES.commentReply(42, 7, 9),
];
const expectedCommentRoutes = [
  '/api/projects/42/comments',
  '/api/projects/42/comments/7',
  '/api/projects/42/comments/7/replies',
  '/api/projects/42/comments/7/replies/9',
];
if (JSON.stringify(commentRoutes) !== JSON.stringify(expectedCommentRoutes)) {
  throw new Error(`comment route mismatch: expected ${expectedCommentRoutes}, got ${commentRoutes}`);
}
if (!KNOWN_EVENTS.includes('comments_changed')) {
  throw new Error('comments_changed is missing from the known project events');
}

console.log('Contract route/event tests: 3 passed, 0 failed');

const pythonSchemas = readFileSync('../logosforge/logosforge/api/schemas.py', 'utf8');
const typescriptSchemas = readFileSync('src/types.ts', 'utf8');
const pythonDtos = new Set([...pythonSchemas.matchAll(/^class\s+(\w+DTO)\b/gm)].map((match) => match[1]));
const typescriptDtos = new Set(
  [...typescriptSchemas.matchAll(/^export\s+(?:interface|type)\s+(\w+DTO)\b/gm)]
    .map((match) => match[1]),
);
const onlyPython = [...pythonDtos].filter((name) => !typescriptDtos.has(name)).sort();
const onlyTypescript = [...typescriptDtos].filter((name) => !pythonDtos.has(name)).sort();
if (onlyPython.length || onlyTypescript.length) {
  throw new Error(
    `DTO drift detected. Python-only: ${onlyPython.join(', ') || '(none)'}; `
    + `TypeScript-only: ${onlyTypescript.join(', ') || '(none)'}`,
  );
}

console.log(`DTO parity tests: ${pythonDtos.size} Python = ${typescriptDtos.size} TypeScript`);
