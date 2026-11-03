# Configuration guide

Edit `src/config/convention.config.js` to create an edition. Keep the currency, pass, lunch, included count, cap, selection mode, contact placeholders and demo switch together. Selection modes `up_to` and `exact` are both implemented; the current, clearly marked demo default is `up_to`, and the policy remains open. Add an edition ID/year when organizers establish edition governance.

Events are records in `src/data/events.js`. Stable `id` and `slug` fields connect UI routes. `baseValue` is used only for included-event cap arithmetic; `addonPrice` is a separate fee and never waives the pass. Team records define min/max sizes. Replace only after organizer sign-off. See root README for a complete annotated sample and calculations.

Theme variables, type stacks, component styling and breakpoints are in `src/style.css`. Do not alter official marks; update assets only after approval and document mappings in the inventory.
