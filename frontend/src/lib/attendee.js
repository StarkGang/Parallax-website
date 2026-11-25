/**
 * Attendee logistics vocabulary, shared by the pass form, the ID card studio and
 * the desk scan result.
 *
 * The values are what the API stores; the labels are what a person reads. Keeping
 * them in one place means a new option cannot appear in one screen and be missing
 * from another.
 */

// The API stores 0 for male and 1 for female; these names are the wire format.
export const GENDER_OPTIONS = [
  { value: 'male', label: 'Male' },
  { value: 'female', label: 'Female' },
];

export const FOOD_OPTIONS = [
  { value: 'veg', label: 'Vegetarian', short: 'Veg' },
  { value: 'non_veg', label: 'Non-vegetarian', short: 'Non-veg' },
];

const GENDER_LABELS = Object.fromEntries(
  GENDER_OPTIONS.map((option) => [option.value, option.label]),
);

const FOOD_LABELS = Object.fromEntries(
  FOOD_OPTIONS.map((option) => [option.value, option.label]),
);

const FOOD_SHORT = Object.fromEntries(
  FOOD_OPTIONS.map((option) => [option.value, option.short]),
);

export function genderLabel(value) {
  if (!value) return '';
  return GENDER_LABELS[value] || value;
}

export function foodLabel(value) {
  if (!value) return '';
  return FOOD_LABELS[value] || value;
}

export function foodShortLabel(value) {
  if (!value) return '';
  return FOOD_SHORT[value] || value;
}

/**
 * One line for a printed card: "Female · Veg · Hostel stay".
 * Returns '' when nothing is known, so the card does not print empty labels.
 */
export function logisticsLine({ gender, foodPreference, needsAccommodation } = {}) {
  return [
    genderLabel(gender),
    foodShortLabel(foodPreference),
    needsAccommodation === undefined || needsAccommodation === null
      ? ''
      : needsAccommodation
        ? 'Hostel stay'
        : 'No stay',
  ]
    .filter(Boolean)
    .join(' · ');
}
