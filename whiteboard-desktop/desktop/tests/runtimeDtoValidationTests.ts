import { readdirSync, readFileSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';

import {
  RuntimeDtoValidationError,
  validateAiSettingsResponse,
  validateAiTestResult,
  validateBackendHealthResponse,
  validateBillyChatResponse,
  validateComment,
  validateCommentDeleteResponse,
  validateCommentMutationResponse,
  validateCommentsResponse,
  validateDocumentCreateResponse,
  validateDocumentDeleteResponse,
  validateDocumentExistsResponse,
  validateDocumentListResponse,
  validateDrafterPagesDocument,
  validateLogosInlineResponse,
  validateOutlineItemsResponse,
  validateProjectBundleSnapshot,
  validatePsykeCreateResponse,
  validatePsykeDeleteAcknowledgement,
  validatePsykeDeleteResponse,
  validatePsykeElementMutationResponse,
  validatePsykeSearchResponse,
  validateRecoveryNoticesResponse,
  validateResourceRevisionEnvelope,
  validateWhiteboardDocument,
  validateWritingModesResponse,
  validateProjectBundleForDocument,
  type RuntimeDtoValidator,
} from '../renderer/src/api/runtimeDtoValidation';

let passed = 0;
const failures: string[] = [];

function test(name: string, run: () => void): void {
  try {
    run();
    passed += 1;
  } catch (error) {
    failures.push(`${name}: ${error instanceof Error ? error.message : String(error)}`);
  }
}

function accepts<T>(validate: RuntimeDtoValidator<T>, value: unknown): T {
  return validate(structuredClone(value));
}

function rejects<T>(validate: RuntimeDtoValidator<T>, value: unknown, expectedPath?: string): void {
  try {
    validate(structuredClone(value));
  } catch (error) {
    if (!(error instanceof RuntimeDtoValidationError)) throw error;
    if (expectedPath && error.valuePath !== expectedPath) {
      throw new Error(`rejected at ${error.valuePath}, expected ${expectedPath}`);
    }
    return;
  }
  throw new Error('malformed payload was accepted');
}

const REVISION = '0123456789abcdef0123456789abcdef';
const INCARNATION = 'fedcba9876543210fedcba9876543210';
const BLOCK = {
  id: 'block-1',
  type: 'paragraph',
  text: 'Hello world',
  level: null,
  sp: null,
  marks: [{ type: 'italic', from: 0, to: 5 }],
};
const DOCUMENT = {
  id: '7',
  incarnation: INCARNATION,
  revision: REVISION,
  title: 'A manuscript',
  mode: 'novel',
  blocks: [BLOCK],
  settings: { typeface: 'serif' },
  updated_at: '2026-10-07T10:00:00+00:00',
};
const COMMENT = {
  id: 'comment-1',
  anchor: {
    surface: 'manuscript',
    drafter_page_id: null,
    block_index: 0,
    block_id: 'block-1',
    from_offset: 0,
    to_offset: 5,
    end_block_index: null,
    end_block_id: null,
    prefix: '',
    suffix: ' world',
  },
  quote: 'Hello',
  body: 'Keep this.',
  resolved: false,
  replies: [{
    id: 'reply-1',
    body: 'Agreed.',
    author: 'you',
    created_at: '2026-10-07T10:01:00+00:00',
  }],
  created_at: '2026-10-07T10:00:00+00:00',
  updated_at: '2026-10-07T10:01:00+00:00',
};
const PSYKE_ENTRY = {
  id: '12',
  name: 'Mara',
  entry_type: 'character',
  aliases: ['Captain'],
  description: 'A navigator.',
  notes: '',
  created_at: null,
  updated_at: null,
};

test('manuscript decoder accepts the backend shape including nullable marks', () => {
  const document = accepts(validateWhiteboardDocument, {
    ...DOCUMENT,
    blocks: [{ ...BLOCK, marks: null }],
  });
  if (document.blocks[0]?.marks !== null) throw new Error('nullable marks were not preserved');
});

test('manuscript decoder rejects an invalid inline range', () => {
  rejects(validateWhiteboardDocument, {
    ...DOCUMENT,
    blocks: [{ ...BLOCK, marks: [{ type: 'bold', from: 4, to: 99 }] }],
  }, '$.blocks[0].marks[0]');
});

test('manuscript decoder rejects duplicate block identities', () => {
  rejects(validateWhiteboardDocument, {
    ...DOCUMENT,
    blocks: [BLOCK, { ...BLOCK, text: 'Again' }],
  }, '$.blocks[1].id');
});

test('document library decoders accept canonical list/create/exists/delete payloads', () => {
  accepts(validateDocumentListResponse, { documents: [{
    id: DOCUMENT.id,
    incarnation: INCARNATION,
    revision: REVISION,
    title: DOCUMENT.title,
    mode: DOCUMENT.mode,
    updated_at: DOCUMENT.updated_at,
  }] });
  accepts(validateDocumentCreateResponse, { ok: true, document: DOCUMENT });
  accepts(validateDocumentExistsResponse, { exists: false });
  accepts(validateDocumentDeleteResponse, { ok: true, deleted: '7', cleanup_pending: false });
});

test('document library decoders reject malformed acknowledgements', () => {
  rejects(validateDocumentListResponse, { documents: [{ ...DOCUMENT, revision: '1' }] }, '$.documents[0].revision');
  rejects(validateDocumentCreateResponse, { ok: false, document: DOCUMENT }, '$.ok');
  rejects(validateDocumentExistsResponse, { exists: 'yes' }, '$.exists');
  rejects(validateDocumentDeleteResponse, { ok: true, deleted: 7, cleanup_pending: false }, '$.deleted');
});

test('resource revision decoder accepts only opaque 32-character revisions', () => {
  accepts(validateResourceRevisionEnvelope, { revision: REVISION });
  rejects(validateResourceRevisionEnvelope, { revision: 3 }, '$.revision');
});

test('Drafter decoder preserves the intentional legacy timestamp fallback', () => {
  const document = accepts(validateDrafterPagesDocument, {
    pages: [{ id: 'draft-1', title: 'Alternate scene', blocks: [BLOCK] }],
    revision: REVISION,
  });
  if (!document.pages[0]?.created_at || !document.pages[0]?.updated_at) {
    throw new Error('legacy page timestamps were not normalized');
  }
});

test('Drafter decoder rejects duplicate pages and malformed manuscript blocks', () => {
  rejects(validateDrafterPagesDocument, {
    pages: [
      { id: 'draft-1', title: 'A', blocks: [] },
      { id: 'draft-1', title: 'B', blocks: [] },
    ],
    revision: REVISION,
  }, '$.pages[1].id');
  rejects(validateDrafterPagesDocument, {
    pages: [{ id: 'draft-1', title: 'A', blocks: [{ id: 4, type: 'paragraph', text: '' }] }],
    revision: REVISION,
  }, '$.pages[0].blocks[0].id');
  rejects(validateDrafterPagesDocument, {
    pages: [{ id: 'draft-1', title: 'A', blocks: [], created_at: 7 }],
    revision: REVISION,
  }, '$.pages[0].created_at');
});

test('Outline decoder preserves opaque legacy rows but validates its envelope', () => {
  const decoded = accepts(validateOutlineItemsResponse, {
    items: [{ legacy: 'row' }, null, 3],
    revision: REVISION,
  });
  if (decoded.items.length !== 3) throw new Error('opaque rows were changed');
  rejects(validateOutlineItemsResponse, { items: {}, revision: REVISION }, '$.items');
  rejects(validateOutlineItemsResponse, { items: [], revision: 'stale' }, '$.revision');
});

test('comment decoders accept collection, mutation, and delete payloads', () => {
  accepts(validateComment, COMMENT);
  accepts(validateCommentsResponse, { comments: [COMMENT], revision: REVISION });
  accepts(validateCommentDeleteResponse, { ok: true, deleted: 'comment-1' });
});

test('comment decoders reject invalid anchors, replies, and collection revisions', () => {
  rejects(validateComment, {
    ...COMMENT,
    anchor: { ...COMMENT.anchor, surface: 'drafter', drafter_page_id: null },
  }, '$.anchor.drafter_page_id');
  rejects(validateComment, {
    ...COMMENT,
    replies: [{ ...COMMENT.replies[0], author: 7 }],
  }, '$.replies[0].author');
  rejects(validateCommentsResponse, { comments: [COMMENT] }, '$.revision');
});

test('comment mutation decoder rejects a different returned thread identity', () => {
  accepts((value) => validateCommentMutationResponse(value, 'comment-1'), COMMENT);
  rejects(
    (value) => validateCommentMutationResponse(value, 'comment-2'),
    COMMENT,
    '$.id',
  );
});

test('Billy and Logos decoders accept valid assistant payloads', () => {
  accepts(validateBillyChatResponse, {
    ok: true,
    conversation_id: 'conversation-1',
    message: { role: 'assistant', content: 'Try a stronger verb.' },
    provider: 'ollama',
    note: null,
  });
  accepts(validateLogosInlineResponse, {
    ok: true,
    action: 'rewrite',
    result: 'The revised sentence.',
    suggested_replacement: 'The revised sentence.',
    provider: 'ollama',
    note: null,
  });
});

test('Billy and Logos decoders reject malformed assistant payloads', () => {
  rejects(validateBillyChatResponse, {
    ok: true,
    conversation_id: 'conversation-1',
    message: { role: 'tool', content: 'bad' },
    provider: 'ollama',
  }, '$.message.role');
  rejects(validateLogosInlineResponse, {
    ok: true,
    action: 'rewrite',
    result: ['not text'],
    provider: 'ollama',
  }, '$.result');
});

test('PSYKE decoders accept revisioned read/write and numeric delete payloads', () => {
  accepts(validatePsykeSearchResponse, { query: 'mar', results: [PSYKE_ENTRY], revision: REVISION });
  accepts(validatePsykeCreateResponse, { ok: true, element: PSYKE_ENTRY, revision: REVISION });
  const deleted = accepts(validatePsykeDeleteResponse, { ok: true, deleted: 12 });
  if (deleted.deleted !== 12) throw new Error('numeric deleted id was changed');
});

test('PSYKE decoders reject malformed entries, missing revisions, and string delete ids', () => {
  rejects(validatePsykeSearchResponse, {
    query: 'mar',
    results: [{ ...PSYKE_ENTRY, aliases: 'Captain' }],
    revision: REVISION,
  }, '$.results[0].aliases');
  rejects(validatePsykeCreateResponse, { ok: true, element: PSYKE_ENTRY }, '$.revision');
  rejects(validatePsykeDeleteResponse, { ok: true, deleted: '12' }, '$.deleted');
});

test('PSYKE mutation decoders reject different returned element identities', () => {
  accepts(
    (value) => validatePsykeElementMutationResponse(value, '12'),
    { ok: true, element: PSYKE_ENTRY, revision: REVISION },
  );
  rejects(
    (value) => validatePsykeElementMutationResponse(value, '13'),
    { ok: true, element: PSYKE_ENTRY, revision: REVISION },
    '$.element.id',
  );
  accepts(
    (value) => validatePsykeDeleteAcknowledgement(value, '12'),
    { ok: true, deleted: 12 },
  );
  rejects(
    (value) => validatePsykeDeleteAcknowledgement(value, '13'),
    { ok: true, deleted: 12 },
    '$.deleted',
  );
});

test('AI settings and connection-test decoders accept valid payloads', () => {
  accepts(validateAiSettingsResponse, {
    provider: 'Ollama', model: 'qwen', base_url: 'http://localhost:11434/v1', timeout: 60,
    api_key: null,
  });
  accepts(validateAiTestResult, { ok: true, provider: 'Ollama', reply: 'ok', error: null });
});

test('AI settings and connection-test decoders reject malformed or leaked fields', () => {
  rejects(validateAiSettingsResponse, {
    provider: 'OpenAI', model: 'gpt', base_url: 'https://api.openai.com/v1', timeout: 60,
    api_key: 'secret',
  }, '$.api_key');
  rejects(validateAiTestResult, { ok: 'yes', provider: 'Ollama' }, '$.ok');
});

test('writing-mode decoder requires a returned default mode', () => {
  const payload = {
    modes: [{
      id: 'novel',
      label: 'Novel',
      structural_units: ['chapter', 'scene'],
      default_writing_format: 'prose',
      medium_constraints: '',
    }],
    default_mode: 'novel',
  };
  accepts(validateWritingModesResponse, payload);
  rejects(validateWritingModesResponse, { ...payload, default_mode: 'screenplay' }, '$.default_mode');
});

test('recovery and health decoders accept valid payloads and reject malformed fields', () => {
  accepts(validateRecoveryNoticesResponse, { notices: [{
    id: 'notice-1',
    label: 'Manuscript',
    message: 'Recovered the last valid snapshot.',
    recovered_from: 'whiteboard.json',
    quarantined_path: 'whiteboard.corrupt.json',
    recovered_at: '2026-10-07T10:00:00+00:00',
  }] });
  accepts(validateBackendHealthResponse, {
    status: 'ok',
    service: 'logosforge-whiteboard',
    instance_nonce: 'nonce',
    project_id: 7,
    api_version: '1',
    core_version: null,
    core: { status: 'ok' },
  });
  rejects(validateRecoveryNoticesResponse, { notices: [{ id: 'notice-1' }] }, '$.notices[0].label');
  rejects(validateBackendHealthResponse, {
    status: 'starting', service: 'logosforge-whiteboard', instance_nonce: 'nonce', project_id: 7,
    api_version: null, core_version: null, core: {},
  }, '$.status');
});

const PROJECT_BUNDLE = {
  format: 'logosforge-project-bundle',
  version: '1.0',
  exportedAt: '2026-10-07T10:00:00+00:00',
  source: { app: 'logosforge-whiteboard' },
  project: {
    id: '7',
    title: 'A manuscript',
    mode: 'novel',
    settings: {},
    manuscript: { blocks: [BLOCK] },
    outline: [{ id: 'legacy-outline-row' }],
    comments: [COMMENT],
    drafter: { pages: [{
      id: 'draft-1',
      title: 'Alternate scene',
      blocks: [BLOCK],
      created_at: '2026-10-07T10:00:00+00:00',
      updated_at: '2026-10-07T10:01:00+00:00',
    }] },
    psyke: {
      elements: [PSYKE_ENTRY],
      relations: [{
        id: '12:13', source_id: 12, target_id: 13, source: 'Mara', target: 'Bex',
        relation_type: 'allies',
      }],
      progressions: [{
        id: 1, entry_id: 12, text: 'Mara takes command.', scene_id: null,
        scene_title: '', sort_order: 0,
      }],
    },
  },
};

test('project-bundle decoder accepts the complete backend export shape', () => {
  const bundle = accepts(validateProjectBundleSnapshot, PROJECT_BUNDLE);
  if (bundle.project.drafter.pages[0]?.id !== 'draft-1') {
    throw new Error('valid project bundle was not preserved');
  }
});

test('project-bundle decoder rejects a different requested project identity', () => {
  accepts((value) => validateProjectBundleForDocument(value, '7'), PROJECT_BUNDLE);
  rejects(
    (value) => validateProjectBundleForDocument(value, '8'),
    PROJECT_BUNDLE,
    '$.project.id',
  );
});

test('project-bundle decoder rejects incomplete and malformed nested snapshots', () => {
  rejects(validateProjectBundleSnapshot, {
    ...PROJECT_BUNDLE,
    project: {
      ...PROJECT_BUNDLE.project,
      drafter: { pages: [{ id: 'draft-1', title: 'Draft', blocks: [] }] },
    },
  }, '$.project.drafter.pages[0].created_at');
  rejects(validateProjectBundleSnapshot, {
    ...PROJECT_BUNDLE,
    project: {
      ...PROJECT_BUNDLE.project,
      psyke: {
        ...PROJECT_BUNDLE.project.psyke,
        relations: [{
          id: '12:13', source_id: '12', target_id: 13, source: 'Mara', target: 'Bex',
          relation_type: 'allies',
        }],
      },
    },
  }, '$.project.psyke.relations[0].source_id');
});

function sourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return sourceFiles(path);
    return /\.(?:ts|tsx)$/.test(entry.name) && !/Tests\.tsx?$/.test(entry.name) ? [path] : [];
  });
}

test('static audit finds no unchecked renderer Response.json consumption', () => {
  const rendererRoot = resolve(process.cwd(), 'renderer', 'src');
  const violations: string[] = [];
  for (const path of sourceFiles(rendererRoot)) {
    const rel = relative(rendererRoot, path).replaceAll('\\', '/');
    const lines = readFileSync(path, 'utf8').split(/\r?\n/);
    lines.forEach((line, index) => {
      if (!line.includes('.json()')) return;
      if (rel === 'api/responseError.ts' && line.includes('as unknown')) return;
      if (/validate[A-Za-z0-9_]*\s*\(.*\.json\(\)/.test(line)) return;
      violations.push(`${rel}:${index + 1}: ${line.trim()}`);
    });
  }
  if (violations.length) {
    throw new Error(`unchecked JSON response(s):\n${violations.join('\n')}`);
  }
});

test('static audit validates raw project-export text before every export format', () => {
  const path = resolve(
    process.cwd(),
    'renderer',
    'src',
    'features',
    'files',
    'useImportExport.ts',
  );
  const source = readFileSync(path, 'utf8');
  const parse = 'validateProjectBundleForDocument(';
  const rawRead = source.indexOf('const projectContent = await resp.text()');
  const validation = source.indexOf(parse, rawRead);
  const bundleBranch = source.indexOf("if (id === 'project-bundle')", rawRead);
  if (rawRead < 0 || validation < rawRead || bundleBranch < validation) {
    throw new Error('project export reaches a format branch before DTO validation');
  }
});

console.log(`Runtime DTO validation tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.error(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} runtime DTO validation test(s) failed`);
console.log('RUNTIME DTO VALIDATION TESTS: PASS');
