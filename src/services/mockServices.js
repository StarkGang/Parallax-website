import { events } from '../data/events.js';
import { addonTotal, checkIncludedSelection, formatPrice } from '../utils/pricing.js';
import { convention } from '../config/convention.config.js';

// Replace these local adapters with API-backed implementations; pages should not call fetch directly.
export const eventService = {
  list: async () => events,
  get: async (slug) => events.find((event) => event.slug === slug),
};

export const participantService = {
  getProfile: async () => ({
    name: 'Demo Participant',
    college: 'Example Engineering College',
    verification: 'Demo only \u2014 not verified',
  }),
  getVerificationState: async () => ({ state: 'demo', message: 'No student has been verified.' }),
};

export const registrationService = {
  list: async () => [
    { title: 'Circuit Lab', status: 'Demo selection' },
    { title: 'Future Builders', status: 'Draft preview' },
  ],
  create: async () => ({ message: 'Demo only \u2014 no registration was saved.' }),
  cancel: async () => ({ message: 'Demo only \u2014 no registration was cancelled.' }),
};

export const pricingService = {
  checkIncluded: (selectedIds) => checkIncludedSelection(selectedIds, events, convention),
  calculateAddons: (selectedIds) => addonTotal(selectedIds, events),
  format: formatPrice,
  getPassPrice: () => convention.passPrice,
};

export const paymentService = {
  status: async () => ({
    connected: false,
    message: 'Demo only \u2014 payment integration not connected.',
  }),
  createOrder: async () => ({
    connected: false,
    message: 'Demo only \u2014 no payment order was created.',
  }),
};

export const managementService = {
  listEvents: async () => events,
  createEvent: async () => ({ message: 'Demo only \u2014 event changes are not saved.' }),
  updateEvent: async () => ({ message: 'Demo only \u2014 event changes are not saved.' }),
  archiveEvent: async () => ({ message: 'Demo only \u2014 event changes are not saved.' }),
  assignCoordinator: async () => ({
    message: 'Demo only \u2014 coordinator assignments are not saved.',
  }),
  getReports: async () => ({ message: 'Demo only \u2014 reporting data is illustrative.' }),
};
