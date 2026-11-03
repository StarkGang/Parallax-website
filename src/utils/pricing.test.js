import { test } from 'node:test';
import assert from 'node:assert/strict';
import { checkIncludedSelection, addonTotal } from './pricing.js';
const config = { includedEventCount: 3, includedEventValueCap: 450 };
const events = [
  { id: 'a', baseValue: 100, addonPrice: 80 },
  { id: 'b', baseValue: 150, addonPrice: 120 },
  { id: 'c', baseValue: 200, addonPrice: 160 },
  { id: 'd', baseValue: 150, addonPrice: 30 },
];
test('included selections can reach cap; pass amount is not part of sum', () => {
  assert.deepEqual(checkIncludedSelection(['a', 'b', 'c'], events, config), {
    valid: true,
    count: 3,
    value: 450,
    remainingValue: 0,
    countExceeded: false,
    capExceeded: false,
  });
});
test('selection over count or cap is rejected', () => {
  assert.equal(checkIncludedSelection(['a', 'b', 'c', 'd'], events, config).countExceeded, true);
  assert.equal(checkIncludedSelection(['b', 'c', 'd'], events, config).capExceeded, true);
});
test('add-on total uses only add-on prices', () =>
  assert.equal(addonTotal(['a', 'd'], events), 110));
test('exact selection mode requires the configured count', () => {
  assert.equal(
    checkIncludedSelection(['a'], events, { ...config, selectionMode: 'exact' }).valid,
    false,
  );
  assert.equal(
    checkIncludedSelection(['a', 'b', 'c'], events, { ...config, selectionMode: 'exact' }).valid,
    true,
  );
});
