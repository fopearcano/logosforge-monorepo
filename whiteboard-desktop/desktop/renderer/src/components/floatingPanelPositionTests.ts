import {
  clampFloatingPanelPosition,
  defaultFloatingPanelPosition,
  initialFloatingPanelPosition,
} from './floatingPanelPosition';
import {
  loadPanelTransparency,
  normalizePanelTransparency,
  opacityForPanelTransparency,
  PANEL_TRANSPARENCY_MAX,
  savePanelTransparency,
} from './panelTransparency';

let passed = 0;
const failures: string[] = [];
const check = (label: string, condition: boolean) => {
  if (condition) passed += 1;
  else failures.push(label);
};

const viewport = { width: 1000, height: 700 };
check(
  'right default observes edge gap',
  defaultFloatingPanelPosition(320, viewport, 'right', 70).x === 660,
);
check(
  'left default observes edge gap',
  defaultFloatingPanelPosition(320, viewport, 'left', 70).x === 20,
);
check(
  'negative coordinates clamp into viewport',
  JSON.stringify(clampFloatingPanelPosition({ x: -50, y: -20 }, 320, viewport))
    === JSON.stringify({ x: 8, y: 8 }),
);
check(
  'right and bottom keep panel/header reachable',
  JSON.stringify(clampFloatingPanelPosition({ x: 9999, y: 9999 }, 320, viewport))
    === JSON.stringify({ x: 672, y: 644 }),
);
check(
  'narrow viewport still exposes a movable panel',
  clampFloatingPanelPosition({ x: 100, y: 20 }, 320, { width: 280, height: 400 }).x === 8,
);
check('panel transparency parses persisted values', normalizePanelTransparency('35') === 35);
check('panel transparency clamps low', normalizePanelTransparency(-5) === 0);
check(
  'panel transparency clamps high',
  normalizePanelTransparency(999) === PANEL_TRANSPARENCY_MAX,
);
check('panel transparency rejects invalid values', normalizePanelTransparency('invalid') === 0);
check(
  'panel transparency converts to opacity',
  Math.abs(opacityForPanelTransparency(70) - 0.3) < Number.EPSILON * 2,
);
const transparencyValues = new Map<string, string>();
const transparencyStorage = {
  getItem: (key: string) => transparencyValues.get(key) ?? null,
  setItem: (key: string, value: string) => {
    transparencyValues.set(key, value);
  },
};
savePanelTransparency('panel-a', 45, transparencyStorage);
check('panel transparency saves normalized values', transparencyValues.get('panel-a') === '45');
check('panel transparency loads persisted values', loadPanelTransparency('panel-a', transparencyStorage) === 45);
savePanelTransparency('panel-a', 999, transparencyStorage);
check(
  'panel transparency clamps persisted values',
  loadPanelTransparency('panel-a', transparencyStorage) === PANEL_TRANSPARENCY_MAX,
);
check(
  'contextual initial position is preserved',
  JSON.stringify(initialFloatingPanelPosition(340, viewport, {
    side: 'right',
    top: 70,
    preferred: { x: 245, y: 180 },
  })) === JSON.stringify({ x: 245, y: 180 }),
);
check(
  'contextual initial position is clamped into the viewport',
  JSON.stringify(initialFloatingPanelPosition(340, viewport, {
    side: 'right',
    preferred: { x: 9999, y: -10 },
  })) === JSON.stringify({ x: 652, y: 8 }),
);

console.log(`Floating panel tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.log(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} floating-panel test(s) failed`);
console.log('FLOATING PANEL TESTS: PASS');
