// Demo records are fictional. baseValue controls included-event eligibility; addonPrice is a separate fee after the mandatory pass.
const make = (id, title, category, format, baseValue, addonPrice, featured = false) => ({
  id,
  slug: id,
  title,
  category,
  format,
  summary: `A hands-on ${category.toLowerCase()} experience for curious student innovators.`,
  description: `Explore ${title} in a friendly, challenge-led demo setting. Format, rules, schedule and capacity shown here are illustrative and require organizer approval.`,
  baseValue,
  addonPrice,
  teamMin: format === 'team' ? 2 : 1,
  teamMax: format === 'team' ? 4 : 1,
  eligibility: 'Student status will require organizer verification in the production service.',
  capacity: 'To be announced',
  registrationState: 'Planning preview',
  rules: [
    'Bring curiosity and a willingness to collaborate.',
    'Final rules and equipment requirements will be published by organizers.',
  ],
  schedule: 'Day and time to be announced',
  venue: 'Venue to be announced',
  featured,
});
export const events = [
  make('circuit-lab', 'Circuit Lab', 'Engineering', 'individual', 100, 150, true),
  make('future-builders', 'Future Builders', 'Design', 'team', 150, 200, true),
  make('code-sprint', 'Code Sprint', 'Computing', 'individual', 100, 150, true),
  make('robot-rally', 'Robot Rally', 'Robotics', 'team', 200, 250),
  make('ideas-in-motion', 'Ideas in Motion', 'Innovation', 'team', 150, 200),
  make('pixel-perfect', 'Pixel Perfect', 'Design', 'individual', 100, 150),
  make('data-detective', 'Data Detective', 'Computing', 'individual', 150, 200),
  make('bridge-the-gap', 'Bridge the Gap', 'Engineering', 'team', 200, 250),
];
