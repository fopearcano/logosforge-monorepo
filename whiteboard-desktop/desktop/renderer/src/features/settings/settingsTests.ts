/** Pure AI-settings regression tests (no React/DOM/network). */

import {
  PROVIDER_DEFAULT_URL,
  settingsAfterProviderChange,
  validateAiSettings,
  type AiSettings,
} from './settingsApi';

let passed = 0;
const failures: string[] = [];
const check = (label: string, cond: boolean) => (cond ? (passed += 1) : failures.push(label));

const openai: AiSettings = {
  provider: 'OpenAI',
  model: 'gpt-4.1',
  base_url: PROVIDER_DEFAULT_URL.OpenAI,
  timeout: 120,
};

const anthropic = settingsAfterProviderChange(openai, 'Anthropic');
check('provider switch updates provider', anthropic.provider === 'Anthropic');
check('provider switch resets URL', anthropic.base_url === 'https://api.anthropic.com');
check('provider switch clears incompatible model', anthropic.model === '');
check('provider switch preserves neutral timeout', anthropic.timeout === 120);

check(
  'cloud provider switch requires fresh key',
  validateAiSettings({ ...anthropic, model: 'claude-sonnet-test' }, '', 'OpenAI') ===
    'Enter the Anthropic API key after switching providers.',
);
check(
  'same provider may keep stored write-only key',
  validateAiSettings({ ...anthropic, model: 'claude-sonnet-test' }, '', 'Anthropic') === null,
);
check(
  'cloud model is required',
  validateAiSettings(anthropic, 'key', 'OpenAI') === 'Enter a model for Anthropic.',
);
check(
  'base URL is required',
  validateAiSettings({ ...openai, base_url: '' }, 'key', 'OpenAI') ===
    'Enter a Base URL (or click Default).',
);
check(
  'LM Studio may let the local server choose its loaded model',
  validateAiSettings(
    { provider: 'LM Studio', model: '', base_url: PROVIDER_DEFAULT_URL['LM Studio'], timeout: 0 },
    '',
    'LM Studio',
  ) === null,
);

console.log(`AI settings tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.log('  FAIL: ' + failure);
if (failures.length) throw new Error(`${failures.length} AI settings test(s) failed`);
console.log('AI SETTINGS TESTS: PASS');
