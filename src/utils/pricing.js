import { convention } from '../config/convention.config.js';
export const selectedBaseValue = (selected, all) =>
  all.filter((e) => selected.includes(e.id)).reduce((sum, e) => sum + e.baseValue, 0);
export const checkIncludedSelection = (selected, all, config = convention) => {
  const chosen = all.filter((e) => selected.includes(e.id));
  const value = chosen.reduce((s, e) => s + e.baseValue, 0);
  return {
    valid:
      (config.selectionMode === 'exact'
        ? chosen.length === config.includedEventCount
        : chosen.length <= config.includedEventCount) && value <= config.includedEventValueCap,
    count: chosen.length,
    value,
    remainingValue: config.includedEventValueCap - value,
    countExceeded: chosen.length > config.includedEventCount,
    capExceeded: value > config.includedEventValueCap,
  };
};
export const addonTotal = (ids, all) =>
  all.filter((e) => ids.includes(e.id)).reduce((sum, e) => sum + e.addonPrice, 0);
export const formatPrice = (amount) =>
  new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(amount);
