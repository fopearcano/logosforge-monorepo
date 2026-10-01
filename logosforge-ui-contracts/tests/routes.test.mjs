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

const psykeConsoleRoute = ROUTES.psykeConsoleSuggestions(42);
if (psykeConsoleRoute !== '/api/projects/42/psyke/console/suggestions') {
  throw new Error(`PSYKE Console route mismatch: ${psykeConsoleRoute}`);
}

const projectSearchRoute = ROUTES.projectSearch(42);
if (projectSearchRoute !== '/api/projects/42/search') {
  throw new Error(`project search route mismatch: ${projectSearchRoute}`);
}

if (ROUTES.liveContext !== '/api/live-context') {
  throw new Error(`live context route mismatch: ${ROUTES.liveContext}`);
}

const storyStructureRoute = ROUTES.storyStructure(42);
if (storyStructureRoute !== '/api/projects/42/story-structure') {
  throw new Error(`story structure route mismatch: ${storyStructureRoute}`);
}

const manuscriptSnapshotRoute = ROUTES.manuscriptSnapshot(42);
if (manuscriptSnapshotRoute !== '/api/projects/42/manuscript-snapshot') {
  throw new Error(`manuscript snapshot route mismatch: ${manuscriptSnapshotRoute}`);
}

const psykeCommandRoutes = [
  ROUTES.psykeConsolePlan(42),
  ROUTES.psykeConsoleExecute(42),
];
const expectedPsykeCommandRoutes = [
  '/api/projects/42/psyke/console/plan',
  '/api/projects/42/psyke/console/execute',
];
if (JSON.stringify(psykeCommandRoutes) !== JSON.stringify(expectedPsykeCommandRoutes)) {
  throw new Error(`PSYKE command route mismatch: ${psykeCommandRoutes}`);
}

console.log('Contract route/event tests: 9 passed, 0 failed');

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

const pythonWhiteboardAnchor = pythonSchemas.match(
  /class WhiteboardImportCommentAnchorDTO\(BaseModel\):([\s\S]*?)\n\nclass /,
)?.[1] ?? '';
const typescriptWhiteboardAnchor = typescriptSchemas.match(
  /export interface WhiteboardImportCommentAnchorDTO \{([\s\S]*?)\n\}/,
)?.[1] ?? '';
for (const field of ['surface', 'drafter_page_id']) {
  if (!pythonWhiteboardAnchor.includes(`${field}:`)) {
    throw new Error(`Python WhiteboardImportCommentAnchorDTO is missing ${field}`);
  }
  if (!typescriptWhiteboardAnchor.includes(`${field}?`)) {
    throw new Error(`TypeScript WhiteboardImportCommentAnchorDTO is missing optional ${field}`);
  }
}

console.log('Whiteboard comment-scope parity tests: 2 fields mirrored');
