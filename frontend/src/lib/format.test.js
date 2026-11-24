import test from 'node:test';
import assert from 'node:assert/strict';
import { money, percent, titleCase, dateRange, toLocalInput, fromLocalInput } from './format.js';

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

test('dateRange compares years in IST, not the browser zone', () => {
  // 19:00Z on 31 Dec is already 00:30 on 1 Jan in IST, so both ends are 2027.
  const label = dateRange('2026-12-31T19:00:00Z', '2027-01-02T00:00:00Z');
  assert.match(label, /^01 Jan - 02 Jan 2027$/);
});

test('dateRange keeps the year when the IST years differ', () => {
  const label = dateRange('2027-12-31T04:00:00Z', '2028-01-02T04:00:00Z');
  assert.match(label, /31 Dec 2027/);
  assert.match(label, /02 Jan 2028/);
});

test('toLocalInput renders IST wall-clock time', () => {
  assert.equal(toLocalInput('2027-01-01T18:30:00Z'), '2027-01-02T00:00');
  assert.equal(toLocalInput('2027-01-01T00:00:00Z'), '2027-01-01T05:30');
});

test('fromLocalInput reads the value as IST', () => {
  assert.equal(fromLocalInput('2027-01-02T00:00'), '2027-01-01T18:30:00.000Z');
});
