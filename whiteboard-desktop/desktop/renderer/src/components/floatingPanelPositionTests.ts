import {
  clampFloatingPanelPosition,
  defaultFloatingPanelPosition,
} from './floatingPanelPosition';

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

console.log(`Floating panel tests: ${passed} passed, ${failures.length} failed`);
for (const failure of failures) console.log(`  FAIL: ${failure}`);
if (failures.length) throw new Error(`${failures.length} floating-panel test(s) failed`);
console.log('FLOATING PANEL TESTS: PASS');
