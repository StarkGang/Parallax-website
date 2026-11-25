// Display-only "list price" used for the struck-through price on pass tiers and
// event cards. It is a deterministic marketing number: the amount actually
// charged is always the stored fee (category.feePaise / event.addonPricePaise),
// never this value.
const EVENT_SAVINGS_PAISE = [5000, 10000, 15000];
const PASS_SAVINGS_PAISE = 10000;

function hashKey(value) {
  const text = String(value || '');
  let hash = 0;
  for (let index = 0; index < text.length; index += 1) {
    hash = (hash * 31 + text.charCodeAt(index)) | 0;
  }
  return Math.abs(hash);
}

// Events get a natural-looking ₹50 / ₹100 / ₹150 saving, stable per event.
export function eventListPricePaise(pricePaise, key = '') {
  const price = Number(pricePaise || 0);
  if (price <= 0) return 0;
  const saving = EVENT_SAVINGS_PAISE[hashKey(key) % EVENT_SAVINGS_PAISE.length];
  return price + saving;
}

// Pass tiers show a flat ₹100 saving off the list price.
export function passListPricePaise(pricePaise) {
  const price = Number(pricePaise || 0);
  return price > 0 ? price + PASS_SAVINGS_PAISE : 0;
}
