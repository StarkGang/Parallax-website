export const canIncludeEvent = (event, config) =>
  event.registrationState !== 'Closed' && event.baseValue <= config.includedEventValueCap;
