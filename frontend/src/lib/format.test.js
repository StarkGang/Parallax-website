import test from 'node:test';
import assert from 'node:assert/strict';
import { money, percent, titleCase, dateRange } from './format.js';

test('money renders paise as Indian rupees', () => {
  assert.equal(money(35000).replace(/\s/g, ''), '₹350');
  assert.equal(money(35550).replace(/\s/g, ''), '₹355.50');
  assert.equal(money(0).replace(/\s/g, ''), '₹0');
});

test('percent clamps to the 0-100 range', () => {
  assert.equal(percent(450, 900), 50);
  assert.equal(percent(1200, 900), 100);
  assert.equal(percent(3, 0), 0);
});

test('titleCase turns slugs into labels', () => {
  assert.equal(titleCase('paper-presentation'), 'Paper Presentation');
  assert.equal(titleCase('day1'), 'Day1');
});

test('dateRange collapses a same-year range', () => {
  const label = dateRange('2026-03-14T04:00:00Z', '2026-03-15T04:00:00Z');
  assert.match(label, /14 Mar/);
  assert.match(label, /15 Mar 2026/);
});
