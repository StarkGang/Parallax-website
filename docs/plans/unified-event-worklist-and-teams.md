# Plan: one event worklist + optional teams

**Status:** implemented through Phase 1–3 and Phase 6 (pricing core, teams,
worklist, invite funnel, shared basket, event room). Phase 4–5 (full admin
surface, reconciliation report) remain. This plan supersedes the split "free vs
paid" event selection and the "create a team before you can register" flow.
**Scope:** participant portal, team lifecycle, event pricing/checkout, admin
pricing & team rules, invite links. Backend (FastAPI/SQLAlchemy) + frontend
(React/Vite). No new third-party service.
**Owner:** product + portal squad.

---

## 1. Why we are changing this

Three complaints, one root cause: the product models *how we charge* instead of
*what the attendee is doing*.

| Complaint | What it looks like today | Root cause |
|---|---|---|
| "I don't know what's free and what I pay for" | `Select Events` has an "Eligible included events" block and a separate "Additional paid events" block, each with its own price logic, plus a pass-allowance meter that only applies to the first block. | Pricing is a *screen layout*. The same event can appear in two lists with two prices. |
| "I have to make a team before I can register" | `create_addon_registrations()` refuses team-format events with `TEAM_EVENT_REQUIRES_TEAM`; only `create_team()` writes a seat for a team event. | The team is a *precondition* for the booking instead of an option on top of it. |
| "My team vanished when the leader left" / "the invite link did nothing" | Leader leave calls `disband_team()`, cancelling every seat and refunding; the invite code is a string you type, with no link and no guided funnel. | Leadership and payment ownership hang off the leader's own registration row. |

The fix is not a restyle. We make **one registration ("seat") the unit of
truth**, price it on the server, and let a team be an optional attachment to that
seat.

---

## 2. What exists today (audit)

This is what we are discarding or reworking, with the exact places that carry the
behaviour.

**Frontend**

- `frontend/src/pages/Portal.jsx`
  - `PORTAL_NAV` (line ~78): `My Pass & Ticket` · `Select Events` · `My Registrations & Teams` · `Profile`.
  - `PortalSelectEvents`: allowance meter, "Eligible included events", "Additional paid events", client-side cap/count math (`withinCap`, `canAdd`, `addonTotal`).
  - `PortalRegistrations`: tabs `My Event Registrations` / `My Teams & Invites`; `PortalTeams` has its own create form and join-by-code form.
- `frontend/src/lib/api.js`: `saveSelections`, `registerAddons`, `teams`, `createTeam`, `joinTeam`, `rotateInvite`, `toggleTeamLock`. No invite-link or quote endpoints.

**Backend**

- `backend/app/services/passes.py`: `IncludedEventSelection` is a second
  entitlement store next to `Registration` (`kind="included"`), dual-written by
  `set_selections` and read by `selection_state`. Releasing a pass has to update
  both stores.
- `backend/app/services/registrations.py`: `create_addon_registrations()`
  rejects team events (`TEAM_EVENT_REQUIRES_TEAM`), books a batch in one order,
  and computes free/paid with `fee == 0`.
- `backend/app/services/teams.py`: team is created *with* the seat
  (`_maybe_register_team`, `_seat_for`); `leave_team()` disbands on leader
  leave; `_team_order()` finds the team payment through the **leader's**
  registration, so a per-team order is orphaned the moment the leader leaves;
  `purge_user_from_teams()` promotes the oldest member, but only on pass
  rejection/suspension — the other two leader-exit paths still disband.
- `backend/app/services/events.py` `capacity_usage()`: for
  `capacity_unit="entries"` it counts `Team` rows only. A solo entry has no team,
  so it would consume zero capacity.
- `frontend/src/pages/PortalRegistration.jsx` (2.4k lines): pass purchase,
  verification, tickets and receipts; it repeats allowance labels that the
  worklist will own.

**Conflicting half-built work (must be removed in Phase 0)**

`backend/tests/test_team_formation.py` is untracked and asserts the **opposite**
model: "a team exists as soon as the seat does" (`formationState="unset"`,
`teamId` returned by selection, auto-generated team names, join merges and
retires the joiner's own team). It imports `normalize_team_name`,
`validate_team_name`, `default_team_name`, `TEAM_NAME_MAX`, none of which exist.
It is a leftover of an earlier direction. We delete it and write new tests; we
keep only the name normalisation/validation helpers idea (see §4.2).

---

## 3. Product decisions (locked)

- **D1 — One worklist.** Every published event appears once, with one price that
  the server computes. "Included", "free" and "paid" are *properties of the
  row*, not sections of the page.
- **D2 — The seat is the truth.** A `Registration` row is the entitlement. Pass
  allowance (`kind="included"`), free (`fee=0`), paid and team seats are all the
  same row type. `IncludedEventSelection` becomes derived and is retired as a
  source of truth.
- **D3 — Solo is the default.** Registering for any event, team-format
  included, creates a solo entry (`team_id = NULL`) with no `Team` row. Team
  creation is never a precondition. "Ignore teams and just compete" is a
  supported, first-class path.
- **D4 — Teams are optional and always available.** A solo entrant can create a
  team or join one at any time before the roster deadline; both actions *attach*
  to the existing seat and never charge it twice.
- **D5 — Pay the difference only.** The checkout charges
  `sum(effective price of newly claimed seats)`, never the whole
  basket again. The client cannot compute this; it posts a selection and gets a
  server `quote`.
- **D6 — Leader leaves ⇒ elder leads.** The earliest-joined remaining member is
  promoted. A team disbands only when its **last** member leaves. The team's
  payment is owned by the team, not by the leader's seat.
- **D7 — Invite links are funnel, not code.** A public link opens a preview and
  a 3-step join (sign in → get entitlement → join). No dead ends.
- **D8 — Everything is configuration, not code.** Price, allowance, team basis,
  min/max size, pass requirement, solo allowance, handover rule live in
  `EditionPolicy` / `Event`, editable in Admin, versioned on save.
- **D9 — Team membership never changes the price.** A team event is priced by
  exactly the same quote as an individual event: the pass allowance can cover
  it (`Included with pass`, ₹0), it can be free, or it can be paid. Creating or
  joining a team must never force a payment and must never take away the
  included/free option. Team formation is a *roster* action, not a checkout.
- **D10 — An unpaid leader is replaced, not abandoned.** If the leader of a
  `per_team` team leaves before paying, the earliest-joined member is promoted
  and the same team-owned payment becomes theirs. If nobody pays before the
  hold expires, the team entry expires for everyone (nobody is charged) and
  each member keeps their own seat option. See §5.4.
- **D12 — No credit wallet.** Every cancellation and every negative price
  difference is refunded directly to the original payment method. Nothing is
  kept "on account", so there is no balance to expire, transfer or explain.
- **D11 — The basket is server state.** Separate event pages are allowed because
  the open basket (`event_quotes`) is one row per attendee per edition. Event
  pages add/remove by id and render the returned quote; they never compute a
  price. The cap is a pricing rule that decides which lines are covered, never a
  validation error that blocks a fourth event.

---

## 4. Target experience

### 4.1 The worklist (replaces both event screens)

```
┌ My Pass ─────────────────────────────────────────────────────────────┐
│ Pass ₹1,200 · covers 2 of 3 events · ₹200 of ₹450 value used        │
├ Event worklist ────────────── [All] [Selected] [Team] [Free] [₹] ────┤
│ ▢ Code Sprint        Fri 10:00 · individual   Included with pass     │
│ ▣ AI Workshop        Fri 14:00 · individual   Due ₹300               │
│ ▣ Robotics           Sat 09:00 · individual   Included with pass     │
│ ▣ Hackathon          Sat 09:00 · team (2–4)   Included possible · ₹0   │
│     └ Team: none yet —  Create a team · Join with a link  (no fee)    │
│ ▢ Paper Presentation Sat 11:00 · individual   Free                   │
├──────────────────────────────────────────────────────────────────────┤
│ 3 selected · covered ₹500 · due ₹300            [Review & pay ₹300] │
└──────────────────────────────────────────────────────────────────────┘
```

Rules the UI follows:

- A row has exactly **one primary action** derived from state: `Add`, `Remove`,
  `Pay ₹X`, `Create team`, `Join team`, `Open ticket`.
- **Pricing never depends on team membership.** The same event shows the same
  price whether the attendee is solo, creates a team or joins one. A team event
  that the pass covers shows `Included with pass`, and `Create team` / `Join`
  are roster actions that do not open a payment sheet. If the seat is not
  covered, the row shows `₹X due` and the *seat* is paid once — before or after
  the team is formed, never twice.
- Team actions live on the row (expand → `TeamPanel`). There is no separate
  "team settings" page where a second, different price appears.
- Price pill vocabulary is limited to four: `Included with pass`, `Free`,
  `₹X due`, `Solo entry`. No "base value" jargon on the participant surface;
  that term stays in Admin and the pass explainer.
- The basket bar shows a **server quote** (`GET /participant/worklist` already
  returns it). It is never recomputed in JS.
- Filters are views, not separate data fetches. One endpoint feeds all tabs.
- Team rows expand inline into a `TeamPanel` (members, invite link, lock,
  leave). There is no second page for teams.

Remove from the participant IA: `Select Events` page, the
`My Registrations & Teams` tab switcher, and the duplicate "Additional paid
events" block. New nav:

```
My Pass · My Events · My Tickets · Profile
                └ worklist + teams + receipts by row
```

Tickets/receipts stay at `/portal/registration`; "My Events" links each row to
its ticket.

### 4.2 Team lifecycle

```
                    ┌──────────────┐
  register event ──▶│  SOLO SEAT   │──create team──▶ ┌──────────────┐
  (any format)      │ team_id=NULL │                 │ TEAM, leader │
                    └──────┬───────┘◀──leave (seat  └──────┬───────┘
                           │            converts back)    │
                           │ join link                      │ others join
                           ▼                                ▼
                    ┌──────────────┐                 ┌──────────────┐
                    │ TEAM, member │◀────────────────│ TEAM, roster │
                    └──────┬───────┘                 └──────┬───────┘
                           │ leave                          │ leader leaves
                           ▼                                ▼
                    ┌──────────────┐                 ┌──────────────┐
                    │  SOLO SEAT   │                 │ ELDER LEADS  │
                    └──────────────┘                 └──────────────┘
                                                   last member leaves
                                                           │
                                                           ▼
                                                     team disbanded
```

Rules:

1. **Create team** (leader): name prompt prefilled `Team <first name>`
   (3–48 chars, normalise whitespace/punctuation, reject a name that is only
   emoji/symbols); creates `Team` + first `TeamMember` (`is_leader=True`),
   attaches the caller's existing seat. If the caller has no seat yet, the
   dialog prices that one seat through the **same worklist quote** — so it can
   be `Included with pass`, `Free` or paid — and attaches the seat in the same
   transaction. It never creates a second, team-only price.
2. **Join team** (member): by invite link or code. Attaches the caller's
   existing seat for that event if there is one. If the caller has no seat, the
   join sheet runs the same allowance step and one `Add & join` button; the
   seat and the membership are created together. A join must never demand
   payment when the pass would have covered the seat.
3. **Solo is not "a team of one" in storage.** `Team` is only created when a
   person asks to create/join one. The UI may *say* "Solo entry" and may show
   "team of one" copy, but no rows exist until they act.
4. **Minimum size is a warning by default.** If `event.team_min_size > 1`, the
   entry is `provisional` and the row shows "Need 1 more member by <date>".
   Enforcement is a policy flag (`team_min_size_enforced`, default **off**).
   When on, unqualified entries are moved to waitlist at
   `registration_closes_at`, not silently cancelled.
5. **Leader exit → elder leads.** `promote_or_disband(team, leaving_user)` is the
   single helper used by `leave_team`, `on_team_registration_cancelled`,
   `purge_user_from_teams` and admin removal:
   ```
   remaining = active members ordered by joined_at ASC, id ASC
   if remaining: earliest.is_leader = True; team.leader_id = earliest.user_id
                 audit team.leader_handover
   else:         team.status = disbanded; handle team order per §5.4
   ```
   No leader-exit path may call `disband_team()` while members remain.
6. **Seat on leave:** if the seat was paid by the leaver, it converts to a solo
   seat (ticket stays valid; no refund). If it was paid by a `per_team` team
   order, the seat is cancelled and the team keeps its paid entry (no refund to
   the leaver). Covered/free seats convert to solo or are released per policy.
7. **Concurrency:** lock the `User` row on create/join (already done), lock the
   `Team` row on join/leave, guard one live team per (user, event) with a
   serialisable check plus an index-backed validation test.
8. **Locked roster:** joining and leaving stay blocked while locked; leadership
   handover still happens if the leader's account is removed by an admin (the
   roster must not keep pointing at a dead leader).
9. **No payment on team actions.** `POST /teams` and `POST /teams/join` return a
   `seat` and at most the *same* order the worklist would have created for that
   event. If the seat is included or free, they return no order at all. The UI
   must never show a team dialog whose only outcome is "pay": it shows
   `Add included seat & create team`, `Add free seat & join`, or `Add ₹X & join`.
10. **Unpaid leader exit (D10).** `promote_or_disband()` moves leadership and
    `Team.order_id` stays with the team. The promoted member sees
    `Team fee ₹X due` and can pay from the team card. Nobody is charged twice,
    and if the hold expires every member's seat is released with no charge.

### 4.3 Invite link

- Share text the leader copies:
  `Join <Team> for <Event> at Parallax — <origin>/team/<code>`
  plus a WhatsApp `wa.me` variant only after the link is copied.
- The shareable link is **derived, never stored**: `<origin>/team/<code>`. Only the code lives on the team row, so the link cannot go stale when the domain changes.
- `GET /public/teams/{code}` returns **non-PII only**: team name, event
  title/slug/date/venue, member count and max, leader first name, whether a pass
  is required, entry price basis (`included|free|₹X|team fee paid by leader`),
  and the team state (`open|full|locked|closed`). No emails, no member list.
- Landing page `/team/:code` behaviour by viewer state:

| Viewer | What happens |
|---|---|
| Signed out | Preview + `Sign in to join` → `/login?next=/team/<code>`; `next` survives the college-registration step and the OAuth round trip. |
| Signed in, no pass, pass required | Preview + inline 3-step card: `Get your pass` → returns to the invite with `?resume=<code>` → seat/allowance step → `Join team`. |
| Signed in, has pass, no seat for event | Preview shows the **allowance outcome** and one button: `Add included seat & join` (₹0), `Add free seat & join` (₹0), or `Add ₹X & join`. Never a bare "pay to join". |
| Signed in, seat already covered by pass | One button `Join <Team>`; no price is shown because the seat already costs ₹0. |
| Signed in, has a seat | One button `Join <Team>` (attaches the seat). |
| Already in this team | "You're already on this team" + `Open my event`. |
| In another team for this event | Blocked with clear copy; option to leave that team first (no silent merge). |
| Team full / locked / event closed | Preview explains why and offers `Create your own team` / `Browse events`. |

- The code is rotatable (`rotate_invite` exists) and invalidated by rotation.
  Links resolve only while the team is live and the event is open.
- Rate-limit preview (10/min/IP) and join attempts (10/min/user), both already
  available via `limiter()`.

---

## 5. Financial model

All money is integer **paise**. One currency (INR). Prices are inclusive of GST;
the policy's `gst_note` is copy, not a calculation. No floating point anywhere.

### 5.1 Terms

| Symbol | Meaning | Source |
|---|---|---|
| `B_e` | Base value the pass allowance consumes | `Event.base_value_paise` |
| `P_e` | Price outside the pass (what you pay) | `Event.addon_price_paise` |
| `C` | Allowance value cap (nullable = no cap) | `EditionPolicy.included_value_cap_paise` |
| `N` | Included event count | `EditionPolicy.included_event_count` |
| `mode` | `exact` or `up_to` | `EditionPolicy.included_selection_mode` |
| `F` | Pass price | `EditionPolicy.pass_price_paise` |
| `basis` | `per_participant` or `per_team` | `Event.team_fee_basis` → `EditionPolicy.team_fee_basis_default` |

### 5.2 Effective price (the only price rule)

For one user and one event, the **effective price** is:

```
covered(selection) → due = 0
otherwise          → due = P_e
```

`P_e = 0` is free regardless of allowance and **never consumes allowance**
(base value is ignored for a zero-priced event). Included coverage is decided by
a deterministic pack, not by click order:

```
pack(selected, C, N):
  sort selected by (B_e ASC, starts_at ASC, event_id ASC)
  covered = []
  for e in sorted:
      if len(covered) == N: break
      if C is not None and sum(B of covered) + B_e > C: continue
      covered.append(e)
  return covered
```

Consequences that must hold and be tested:

- **Team membership is not a price input.** Coverage is computed from the
  event's base value and the attendee's allowance, exactly as for an individual
  event. A `per_team` event that is covered by the pass costs ₹0 for the whole
  entry; a `per_participant` event that is covered costs ₹0 per covered member.
  `Team.order_id` only exists when something is actually due.
- Adding a cheaper event can *repack* coverage; an event that was "Included"
  yesterday can become "₹X due" today **only before checkout**. Once a seat is
  `confirmed`, its `kind`/price is frozen and is never re-priced or cancelled by
  a later selection.
- The repack is deterministic for the same basket, so the quote a user sees is
  the quote they pay.
- `mode="exact"` validates `count == N`; `up_to` validates `count <= N`. If the
  user has fewer than `N` selected, the shortfall is *allowed and shown*, never
  silently charged.

### 5.3 Quote and checkout (pay the difference)

```
POST /participant/quote  {eventIds:[...]}
  → { quoteId, lines:[{eventId, listPaise, coveredPaise, duePaise, reason}],
      coveredPaise, duePaise, expiresAt }

POST /participant/checkout {quoteId, idempotencyKey}
  → { status:'confirmed' }                       // duePaise == 0
  → { order:{orderId, amountPaise, gatewayOrderId, razorpayKeyId, mock} }
```

- `duePaise = Σ due_e`, floored at 0. There is no balance to apply.
- Already `confirmed` seats for the same event are excluded from the quote
  (`due=0`, line shows "already confirmed"). Re-clicking pay can never charge a
  seat twice.
- One open quote per (user, edition); a new quote expires the previous one.
  `expire_reservations()` continues to release abandoned held seats.
- Every order line points at the `Registration` it pays for
  (`PaymentOrder.linked_record_id` / `notes.eventIds`). The order-to-seat
  mapping is what reconciles.
- Partial failure is not allowed: the gateway captures the full quoted amount
  or nothing. We do not split one basket into two charges.

### 5.4 Teams and money

- `per_participant`: each member has their own `Registration`, own `P_e`, own
  order. Joining never shares or duplicates a charge.
- `per_team`: **one** order for the entry, owned by the team:
  - Add `Team.order_id` (FK `payment_orders.id`, nullable),
    `Team.paid_by_user_id`. Backfill from the leader's registration order.
  - The creator pays the team entry **only if the quote says it is due**.
    Joiners are `₹0` and see "covered by team fee".
  - If the entry is included (`pass allowance`) or free, no order exists at
    all. The team is formed, the seat is `confirmed`, the ticket is issued, and
    no member is ever asked to pay.
  - If the creator leaves before paying, `Team.order_id` stays with the team and
    the promoted elder sees `Pay ₹X for the team`. This is D10: the order is
    never orphaned and the roster is never penalised for the leader's exit.
  - If nobody pays before the hold expires, the whole entry expires: every
    member's seat is released, the team is disbanded, nobody is charged, and
    each member can still add the event solo (subject to capacity).
  - If the team disbands (last member) or the event is cancelled, refund the
    team order once, per §5.5.
- Members' `Registration.fee_paise` for a `per_team` seat is `0`; the paid amount
  lives on the team order. Reporting reads `Team.order_id` for team revenue so
  the ledger closes.
- **Covered team entries:** the leader's `Registration.kind` is `included`
  (or `free`) and `Team.order_id` is `NULL`. Changing basis (`per_team` ↔
  `per_participant`) never re-prices a confirmed seat.

### 5.5 Refunds and "negative difference"

There is no credit wallet (D12). A negative difference is refunded to the
original payment method, capped at the amount actually paid for that seat. The
`refunds` table is the ledger; `PaymentOrder` + `Refund` must always reconcile.

Refund matrix (must be enforced server-side):

| Situation | Seat | Money |
|---|---|---|
| Cancel own paid seat, outside 24 h cutoff | released | refund to the original payment method |
| Cancel own paid seat, inside 24 h cutoff | blocked | helpdesk only |
| Cancel own included seat | released | ₹0; allowance restored |
| Cancel free seat | released | ₹0 |
| Member leaves a `per_participant` team | converts to solo | no money moves; their own paid seat stays theirs |
| Member leaves a `per_team` team | released | no refund to them (they did not pay); team keeps the entry |
| Leader leaves | own seat as above | team order untouched; leadership moves; unpaid order moves to the elder (D10) |
| Leader leaves before the team entry is paid | roster handed over | promoted member can pay; if the hold expires, **no one is charged** and every seat is released |
| Team entry hold expires unpaid | all released | nothing charged; team disbanded; members may re-add solo |
| Last member leaves | team disbanded | `per_team` order refunded per policy |
| Organiser cancels event | all released | 100% refund |
| Pass rejected / suspended / refunded | all released | paid seats refunded (`release_event_entitlements`) |
| Unpaid hold expires | released | nothing charged; order `expired` |
| Repack makes a paid seat coverable | seat stays confirmed | refund the difference, capped at `min(paid, P_e)`; no account balance |
| Category upgrade | stays | charge `to_fee − from_fee` only (`RegistrationCategoryChange.settlement_type="pay_difference"`) |
| Category downgrade | stays | refund the negative difference |

Rules:

- One refund per cancelled seat per source order; a retry reuses the pending
  refund rather than creating a second one.
- A refund is capped by what was actually paid on that order and by what the
  order still holds un-refunded.
- A gateway outage records a `pending` refund for finance; it never silently
  keeps the money and never turns into credit.

### 5.6 Worked example (default policy)

Pass `F=₹1,200`, `N=3`, `C=₹450`, `up_to`, cap inclusive.

| Event | `B_e` | `P_e` | Coverage | Due |
|---|---|---:|---|---:|
| Code Sprint | ₹100 | ₹0 | covered | ₹0 |
| AI Workshop | ₹200 | ₹300 | covered | ₹0 |
| Robotics | ₹150 | ₹150 | covered | ₹0 |
| Hackathon (team) | ₹250 | ₹200 | not covered | ₹200 |
| Paper Presentation | ₹0 | ₹0 | free | ₹0 |

Basket `{Code, AI, Robotics, Hackathon}`: pack `{Code 100, Robotics 150, AI 200}`
= 3 events, `B=450` → covered. Hackathon due. **Checkout charges ₹200**, not
₹650. That is the "pay the difference" promise, and it is a single integer
computed from the quote.

Repack case: user removes AI and adds `Gaming (B=180, P=120)`. New pack
`{Code 100, Robotics 150, Gaming 180} = 430 ≤ 450` → all covered, due ₹0. No
money moves, because nothing beyond the pass had been paid.

Team case: Hackathon at `per_team ₹600`. Solo = ₹600. Creator pays ₹600 once;
three joiners pay ₹0. Leader leaves → elder leads, the ₹600 order stays with the
team. Last member leaves → disband, one ₹600 refund.

Included team case: the same Hackathon inside the pass allowance. `B=250`,
`P=600`; if the pack covers it, the leader's seat is `included`, the team entry
is ₹0, and **no member is ever asked to pay**. Creating or joining the team is a
roster action only. If the leader later leaves, the elder leads and still owes
nothing.

### 5.7 Invariants (asserted in tests and in a nightly reconciliation)

1. `Σ paid orders − Σ refunds = Σ confirmed seat prices + Σ active pass prices`
   per edition (team orders counted once, on `Team.order_id`).
2. No `Registration` with `fee_paise > 0` may be `confirmed` without a `paid`
   order (or an explicit organiser comp with an audit row).
3. One live registration per `(user, event)`; one live team per `(user, event)`.
4. `quote.duePaise == Σ line.duePaise`, exactly.
5. A refunded order has no live seats; a live paid seat has no refund.
6. The same basket always produces the same coverage and the same total,
   whatever order the events were added in.

### 5.8 Multi-event baskets across separate event pages

Event pages are allowed to be separate **only because the basket is not**. The
basket is a server row, not page state, and every page reads and writes the same
one.

**One basket per (user, edition).** The open `event_quotes` row *is* the basket.
`POST /quote` rebuilds it; checkout consumes it. Add/remove from any page run
through the same builder:

```
POST   /participant/basket/events      {eventIds:[...]}   # add one or many
DELETE /participant/basket/events/{id}                    # remove a draft seat
GET    /participant/basket                              # lines + totals
```

A per-event page never sends a price. It sends "add this event id" and renders
whatever the server returns. That is the only way two pages can agree.

**How 3 events + a cap behave.** The cap is a *pricing* rule, never a validation
error. A basket can hold 5 events; the pack decides which 3 are covered.

| Basket (N=3, cap ₹450) | Coverage | Due |
|---|---|---|
| A(100) | A included | ₹0 |
| A(100) + B(200) | A, B included | ₹0 |
| A + B + C(150) | A, B, C included (Σ450) | ₹0 |
| A + B + C + D(250, price 200) | A, B, C included; D paid | ₹200 |
| A + C + D (B removed) | A, C, D? Σ=500 > cap → D paid | ₹200 |
| A + B + C + E(free, price 0) | A, B, C included; E free | ₹0 |

The UI must say **which** events are covered, not just a total, because adding a
fourth can move the line. On every basket change the server returns the full
line set; pages render it verbatim. `exact` mode is also non-blocking: a short
basket is allowed and labelled "2 of 3 included slots used".

**Confirmed seats never re-enter the pack.** Already-confirmed seats are
subtracted first (`frozen_count`, `frozen_value`). A new page can only affect
seats that are not yet confirmed, so navigating around can never un-cover a
paid seat. If an already-paid seat *would* become covered after a later change
(pass upgrade, repack), the difference is refunded to the original payment
method, capped at what was paid; it is never a silent re-price.

**Two tabs / back button / refresh**

- Basket mutations lock the user row and rebuild the quote, so two tabs cannot
  create two baskets.
- The client never keeps a second copy of coverage: after every mutation it
  stores the returned quote id and lines.
- Checkout is keyed to the quote id plus an idempotency key. A second tab
  checking out the same quote reuses the order; checking out an expired or
  superseded quote fails with `QUOTE_STALE` / `QUOTE_EXPIRED`, and the page
  rebuilds instead of charging an old basket.
- A page loaded before a change shows a stale price only until its next fetch;
  checkout revalidates prices and policy version and refuses to charge a stale
  basket.

**What the event page may promise**

- Seat already confirmed: the frozen price (“Included with pass”, “Paid ₹200”).
- Seat only in the basket (not checked out): “Included if you confirm now” or
  “₹X due” — always with the caveat that the basket total is what counts.
- Never “₹0 guaranteed” for an unconfirmed seat, because a later addition can
  change the pack.

The event page also shows the basket bar with `N selected · covered ₹X · due ₹Y`
and one link to the review sheet, so a person can add three events from three
pages and pay once.

**Bug ledger — failure mode → prevention → test**

| Failure | Prevention | Test |
|---|---|---|
| Page A says ₹0, checkout charges ₹200 | page only renders server quote; tentative label until checkout | add event on page A, another on page B, assert page A quote refreshes |
| Adding a 4th event fails with “cap exceeded” | cap is pricing, not validation; over-cap line is marked due | 4-event basket returns due, not 4xx |
| Same basket, different add order, different coverage | deterministic pack (base, start, id) | add A,B,C and C,B,A, compare line sets |
| Two tabs create two baskets | one open quote per user/edition + user row lock | parallel quote calls, assert one open quote |
| Double checkout from two tabs | idempotency key + consumed quote | repeat checkout, assert one order, one seat set |
| Paid seat silently re-priced by repack | confirmed seats frozen; only a capped refund is possible | confirm seat, add cheaper event, assert paid seat unchanged |
| Old page checks out after a price change | quote pins price + policy version; checkout revalidates | change price, checkout old quote → 409 |
| Basket lost on navigation/refresh | basket is server state, not localStorage | add on page, reload, same lines |
| Team page charges again for an existing seat | team attach reuses seat; only missing seat goes through quote | add seat, create team, assert no second order |
| Free event eats an included slot | zero-price events excluded from the pack | free + 3 paid test |

---

## 6. Data model changes

### 6.1 New / changed columns

| Table | Change | Why |
|---|---|---|
| `registrations` | keep `team_id` nullable (already); add `price_basis` (`included|free|addon|team_per_team|team_per_participant`), `quote_id` (nullable) | freeze how a seat was priced; audit |
| `teams` | add `order_id` FK, `paid_by_user_id` FK, `formation_state` (`solo|forming|ready|locked|disbanded`), `min_size` snapshot, `name_normalised` | team-owned payment; lifecycle; deterministic naming |
| `team_members` | add `left_at`, `role` (`leader|member`) kept in sync with `is_leader` | elder order + history |
| `event_quotes` | new table: `user_id`, `edition_id`, `lines JSON`, `covered_paise`, `due_paise`, `status`, `expires_at`, `idempotency_key` | quote is a real object, not client state |
| `included_event_selections` | stop writing; keep read-only for one release, then drop | D2 single entitlement store |

### 6.2 Migration and backfill (one Alembic revision)

1. Add columns (all nullable / with defaults) and the two tables.
2. Backfill `teams.order_id` / `paid_by_user_id` from the leader's live team
   registration's paid order (only `per_team`).
3. Backfill `registrations.price_basis`: `included` → `included`,
   `fee=0 && addon` → `free`, `team_id NOT NULL` → team basis, else `addon`.
4. Backfill `teams.formation_state` from `status`.
5. Reconcile `included_event_selections` against `registrations kind='included'`
   and report mismatches before dropping the table.
6. No destructive change to `college_registrations`, `convention_passes`,
   `payment_orders`, `tickets`.

### 6.3 Capacity correction

`capacity_usage()` for `capacity_unit="entries"` must count **distinct live
entries**:

```
entries = count(live teams) + count(live solo registrations on that event)
```

Where live solo = `team_id IS NULL AND status IN ('confirmed','reserved','pending')`
and the user is not on a live team for that event. Without this, solo entries
are invisible and a team event can be oversold. Add a test that a solo entry
consumes one entry and creating a team does not consume a second.

---

## 7. API changes

### New

| Method + path | Purpose |
|---|---|
| `GET /participant/worklist` | rows + allowance meter + open quote + my teams, in one payload |
| `POST /participant/quote` | server price for `eventIds`; returns `quoteId` |
| `POST /participant/checkout` | confirm quote; returns `confirmed` or a Razorpay order |
| `DELETE /participant/events/{eventId}` | remove a seat (cancel/reserved release, direct refund per matrix) |
| `GET /public/teams/{code}` | invite preview (non-PII) |
| `PATCH /participant/teams/{id}` | rename (leader, before roster deadline) |
| `POST /participant/teams/{id}/transfer` | optional manual handover to a chosen member |

### Changed

- `POST /participant/teams` — attaches/reuses the caller's seat; creates it if
  missing (same quote path); returns `team`, `seat`, `payment` (team or seat).
- `POST /participant/teams/join` — accepts `inviteCode` **or** `inviteToken`;
  never requires an existing team; returns `joined`, `seatCreated`, `payment`.
- `DELETE /participant/teams/{id}` — promotes the elder instead of disbanding;
  returns `newLeaderId` when leadership moved.
- `GET /participant/registrations` — unchanged contract; `kind` values gain
  `free`/`team` but old values still parse.

### Deprecated (thin wrappers for one release)

- `PUT /pass/selections` → delegates to quote+checkout with `eventIds`.
- `POST /registrations` → same, except team events are now allowed (this removes
  `TEAM_EVENT_REQUIRES_TEAM`).

### Response shape (worklist)

```json
{
  "allowance": { "count": 2, "required": 3, "mode": "up_to",
                 "capPaise": 45000, "valuePaise": 30000, "remainingPaise": 15000 },
  "quote": { "quoteId": "...", "coveredPaise": 30000, "duePaise": 30000,
             "expiresAt": "..." },
  "rows": [{
    "eventId": "...", "title": "Hackathon", "slug": "hackathon",
    "format": "team", "startsAt": "...", "category": "Coding",
    "price": { "listPaise": 20000, "duePaise": 20000, "basis": "addon" },
    "state": "solo", "seat": { "id": "...", "status": "reserved", "kind": "addon" },
    "team": { "status": "none", "canCreate": true, "canJoin": true },
    "actions": ["pay", "create_team", "join_team"]
  }]
}
```

The frontend renders `state`, `price` and `actions`; it owns no pricing logic.

---

## 8. UI specification

### 8.1 Screens

| Route | Screen | Notes |
|---|---|---|
| `/portal/events` | **My Events** (worklist + basket) | replaces `Select Events` + registrations tab |
| `/portal/events/:eventSlug` | **Event room** (signed in) | hero, personal price, five step cards, solo/team guides; the public `/events/:eventSlug` stays the catalogue view |
| `/portal/events?event=<slug>` | worklist with one row expanded | deep link from public event page |
| `/portal/registration` | My Pass & Ticket | pass purchase/status/receipt, unchanged core |
| `/portal/tickets` | My Tickets | extracted from the old registrations tab |
| `/team/:code` | Invite landing | public preview + guided join |
| `/manage` → Events & Pricing | Admin | §9 |

### 8.2 Components (new files)

```
frontend/src/pages/Worklist.jsx          page shell, filters, allowance meter
frontend/src/pages/EventRoom.jsx         signed-in event page + step cards
frontend/src/components/worklist/StepCard.jsx  done / active / optional / pending
frontend/src/components/worklist/BasketBar.jsx shared basket bar (worklist + event room)
frontend/src/components/worklist/Row.jsx one row + primary action
frontend/src/components/worklist/Basket.jsx sticky quote bar + pay sheet
frontend/src/components/worklist/TeamPanel.jsx members, invite link, lock, leave
frontend/src/components/worklist/TeamDialog.jsx create/join dialog (reused by /join)
frontend/src/pages/JoinInvite.jsx        /team/:code funnel
frontend/src/lib/pricing.js              formatting + state labels only (no math)
```

Deleted: the `PortalSelectEvents` component, the `PortalTeams` section inside
`Portal.jsx`, and the subtab switcher in `PortalRegistrations`.

### 8.3 Row states and copy (single source of truth)

| `state` | Pill | Primary action | Secondary |
|---|---|---|---|
| `available` | — | `Add` | — |
| `included` | `Included with pass` | `Remove` | — |
| `free` | `Free` | `Remove` | — |
| `addon_unpaid` | `₹300 due` | `Pay ₹300` | `Remove` |
| `confirmed` | `Confirmed` | `Open ticket` | `Cancel` |
| `solo` (team event, seat covered) | `Included with pass` / `Free` | `Create team` | `Join with a link` |
| `solo` (team event, seat unpaid) | `Solo · ₹200 due` | `Pay ₹200` | `Remove` |
| `team_included` | `Team <name> · Included` | `Open team` | `Leave` |
| `team_member` | `Team <name>` | `Open team` | `Leave` |
| `team_leader` | `You lead <name>` | `Invite` | `Open team` |
| `team_unpaid` | `Team fee ₹600 due` | `Pay team fee` | `Remove` |
| `locked` | `Roster locked` | `Open team` | — |
| `closed` | `Closed` | — | `Waitlist` (if enabled) |

Every destructive action gets a confirmation sheet showing money impact from the
quote ("₹0 moves", "₹300 refunded to source"), so no one has to guess.

### 8.4 Accessibility & mobile

- Filters are a real tablist (`role="tablist"`), rows are `<article>` with the
  primary action as a button, not a nested link.
- Sticky basket bar respects safe-area insets; the review sheet is a focus
  trap and returns focus to the trigger.
- Price is never colour-only: pill text changes with state.
- Loading/empty/error states per filter, not one global spinner.

---

## 9. Configuration (Admin)

One new panel, **Events & pricing**, plus an extended **Pricing rules** card in
the edition settings. Saving writes a **new `EditionPolicy` version** (the model
already versions), so in-flight quotes keep the policy they were priced under.

| Setting | Where | Default | Effect |
|---|---|---|---|
| `included_event_count` | policy | 3 | `N` |
| `included_value_cap_paise` | policy | 45000 | `C`, null = none |
| `cap_inclusive` | policy | true | `≤` vs `<` |
| `included_selection_mode` | policy | `up_to` | exact vs up to |
| `addon_requires_pass` | policy | true | gate on the worklist |
| `team_members_require_pass` | policy | true | gate on create/join |
| `team_fee_basis_default` | policy | `per_participant` | fallback basis |
| `hold_minutes` | policy | 15 | seat hold |
| `selection_change_deadline` | policy | null | freeze |
| `team_solo_allowed` **(new)** | policy | true | team event without a team |
| `team_min_size_enforced` **(new)** | policy | false | provisional → waitlist |
| `leader_handover` **(new)** | policy | `eldest` | `eldest` (fixed in v1) |
| `base_value_paise` | event | — | `B_e` |
| `addon_price_paise` | event | — | `P_e` |
| `team_fee_basis` | event | null | override policy |
| `team_min_size` / `team_max_size` | event | 1 / 4 | roster bounds |
| `included_eligible` | event | true | allowed in allowance |
| `capacity` / `capacity_unit` | event | 0 / participants | seats or entries |
| `format` | event | individual | individual vs team |

Guardrails in the admin form: `team_max_size ≥ team_min_size ≥ 1`, price
`≥ 0`, `C ≥ 0`, count `≥ 0`, and `P_e ≤ B_e` warns (a priced event worth more
than its allowance value is legitimate but surprising). A "Preview as attendee"
button renders the worklist for a sample basket using the unsaved values, so
pricing changes are testable without publishing.

---

## 10. Delivery plan

Estimates assume one backend + one frontend engineer. Each phase ships behind
the `worklist_v2` flag and is independently reversible.

### Phase 0 — clear the ground (0.5 day)

- Delete `backend/tests/test_team_formation.py` (conflicting model, §2).
- Remove `PortalSelectEvents`, the `PortalTeams` block, and the subtab switcher.
- Add `worklist_v2` flag (config) and keep old endpoints as wrappers.
- **Exit:** old flow still works; tree clean of the abandoned auto-team design.

### Phase 1 — pricing core (2–3 days)

- `event_quotes` table (no credit wallet), one Alembic revision.
- `services/pricing.py`: `pack_allowance()`, `quote_for()`, `effective_price()`
  — pure functions, unit-tested first.
- `POST /quote`, `POST /checkout`, `GET /worklist`; checkout reuses
  `attach_gateway_order`, `verify`, idempotency.
- Rewrite `create_addon_registrations` on top of the quote path (team events
  allowed now).
- **Exit:** invariants §5.7 pass; a quote for any basket is reproducible.

### Phase 2 — teams without preconditions (2 days)

- Schema: `teams.order_id`, `paid_by_user_id`, `formation_state`, member
  `left_at`; backfill.
- `create_team` / `join_team`: attach-or-create seat **through the pricing
  quote** (included/free respected); team-owned payment only when the quote
  says something is due; `promote_or_disband()` used by all four leader-exit
  paths.
- `capacity_usage()` solo-entry fix; tests for counts.
- Remove `TEAM_EVENT_REQUIRES_TEAM` from `create_addon_registrations`.
- **Exit:** solo registration on a team event works; a pass-covered team entry
  costs ₹0 and never opens checkout; leader leave promotes; per-team order
  survives a leader change; unpaid hold expires without charging anyone.

### Phase 3 — new worklist UI (2–3 days)

- New components (§8.2), delete old screens, new nav.
- One payload, server price, filters, sticky basket, team panel. Team create /
  join uses the same quote and shows the allowance outcome before the button
  label is chosen — no team flow that is payment-only.
- **Exit:** every §8.3 state renders with the right single action; a covered team
  row shows `Included` and its team dialog never mentions a fee; no price math
  in the browser; axe pass on the page.

### Phase 4 — invite funnel (1–2 days)

- `GET /public/teams/{code}`, `/team/:code`, resume-after-pass state,
  `next`/`resume` preservation through login and college registration.
- Share sheet: copy link + WhatsApp text.
- **Exit:** new user → invite link → pass → add event → joined, in one sitting,
  with no dead end; full/locked/closed paths all explain and offer a way out.

### Phase 5 — configurability, docs, reconciliation (1 day)

- Admin panel (§9), policy versioning, preview; docs updates
  (`docs/features/public-and-portals.md`, `docs/api/reference.md`, this plan's
  index entry); nightly reconciliation query and admin "Finance health" card.
- **Exit:** a pricing/team change ships from Admin with no deploy.

### Phase 6 — event detail room + workflow cards (2–3 days)

Depends on Phase 1 (basket) and Phase 3 (worklist). This is the per-event page
with the five status cards; it does **not** add a second checkout.

- Server basket endpoints (§5.8): `POST/DELETE /basket/events`, `GET /basket`.
  The open quote becomes the basket; every page mutation rebuilds it.
- Event page `/events/:slug` while signed in → `EventRoom`: hero, personal
  price, five step cards, solo/team guide, rules/prizes.
- `StepCard` component with four states: `done`, `active`, `optional`,
  `pending`. Done = muted + strikethrough; optional never blocks completion.
  The required set is 4 (pass, seat, ticket, attend) — team is optional.
- `GET /participant/events/{id}/offer` (or reuse `worklist` row) for the
  personal price. It always returns a basket-based answer + a `tentative` flag.
- New admin content fields: `solo_guide_md`, `team_guide_md` on `Event` (added
  with the admin form); the
  existing description/rules/prizes stay as they are.
- Event page CTA: primary `Add to my plan`, secondary `Add & pay just this`.
  Both call the basket; the second only auto-opens review.
- **Exit:** adding three events from three separate event pages produces one
  basket and one checkout; removing one repacks correctly; a fourth event is
  priced as due, never rejected; opening a page twice in two tabs never creates
  a second basket; the step cards always agree with the worklist.

Total: **10–14 engineer-days**, plus review/QA. Phase 1 and 2 can overlap; Phase 3
depends on 1, Phase 4 depends on 2, Phase 6 depends on 1 and 3.

---

## 11. Test plan

**Unit (fast, pure)**

- allowance pack: cap inclusive/exclusive, no cap, `exact`/`up_to`, repack on
  add/remove, ties broken deterministically.
- quote: already-paid excluded; free never consumes allowance; paise rounding
  impossible.
- team naming: whitespace collapse, 3–48 length, emoji-only rejected, HTML
  characters stripped.
- leader promotion order: `joined_at` then id.

**API (pytest, existing `lifecycle_helpers`)**

- solo register on a team event → one live seat, `team_id IS NULL`, one entry of
  capacity.
- create team with an existing seat → no new order, no second charge.
- create team without a seat → one quote, one order, seat attached.
- join with seat (included / paid / free) → attaches, price unchanged.
- join without seat **on a pass-covered event** → seat is `included`, no order,
  no payment prompt, roster shows the new member.
- create team on a pass-covered event → no order, `Team.order_id` stays NULL.
- per_team leader leaves unpaid → elder leads, `Team.order_id` moves with the
  team, promoted member sees the fee; hold expiry releases everyone with zero
  charged.
- leader leaves with 2 members paid `per_participant` → elder leads, leaver's
  seat solo, no other seat touched, no refund.
- leader leaves with `per_team` paid → order stays on team, new leader sees
  paid.
- last member leaves → team disbanded, exactly one refund.
- invite preview leaks no PII; rotated code 404s; full/locked/closed states.
- concurrent double join → one membership, one seat.
- capacity: solo + team do not double-count; oversell blocked.
- `GET /worklist` totals equal `/quote` for the same basket.
- 3 events inside count and cap → all included, due ₹0; a 4th → cheapest three
  covered, 4th due; adding never returns 4xx for exceeding the cap.
- Deterministic basket: add A,B,C and C,B,A in two sessions → identical coverage
  and due.
- Basket across pages: add on three separate requests, reload, then checkout →
  one order, one seat per event, no duplicates.
- Two parallel quote calls → one open quote; two checkouts → one order.
- Free event in a full basket → does not change the pack.
- A confirmed included seat stays covered when a cheaper event is added later
  (it is frozen, not repacked).

**Finance**

- property test: random baskets and prices satisfy §5.7 invariants 1–5 over 1000
  simulations.
- lifecycle test: buy pass → add 4 → pay diff → cancel one → the refund lands
  on the original order and the next basket starts clean.
- a cancellation never creates a second settlement for the same seat.

**Manual E2E script (release gate)**

1. New account → buy pass → worklist shows included/free/paid/team rows.
2. Add three covered + one paid → pay only the difference.
3. Register solo for Hackathon → create team → copy invite → second account
   opens link → signs in → pass → joins → roster shows 2.
4. Leader leaves → second account becomes leader; invite code still valid.
5. Leader (now) leaves as last member → team gone, refund row correct.
6. Admin changes cap → preview → publish; existing confirmed seats unchanged.

---

## 12. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Double charging on retry / double-click | med | high | idempotency key + one open quote + confirmed seats excluded from quotes |
| Repack silently "un-covers" a seat the user believed included | med | high | freeze price at checkout; quote shows the pack before payment; no post-confirmation re-pricing |
| Leader handover misses a path (admin removal, pass rejection, expiry) | med | high | one `promote_or_disband()` helper; grep test forbidding `disband_team` calls outside it |
| Team order orphaned when the leader leaves | high today | high | `Team.order_id`; backfill; pays on team, not seat |
| Solo entries not counted in entries capacity | high today | med | §6.3 + test |
| Double refund on retry | low | high | refund rows are checked by order and status; invariant test |
| Invite links used to probe private data | low | med | non-PII preview, rate-limited, live-team-only |
| Migration mismatches between `included_event_selections` and registrations | med | med | dry-run reconciliation report before dropping; keep table one release |
| Admin changes price mid-edition | med | med | policy version pinned to quotes; price history already exists (`EventPriceHistory`) |
| Old mobile clients on deprecated endpoints | low | med | wrappers for one release; flag rollout |

---

## 13. Out of scope (this plan)

- Waitlists and lottery allocation (only a `Waitlist` CTA placeholder).
- Automatic teammate matching / "find a team" discovery.
- Multi-team membership per event (explicitly one).
- Partial/proportional refunds by percentage rules (keep the existing policy
  dict; matrix above is the contract).
- Payment provider change; GST invoicing (already a copy-level `gst_note`).
- Admin bulk import of teams.

## 14. Decisions and remaining defaults

Answered:

1. **`per_team` leader leaves before paying** → **elder takes over and pays**
   (D10). The team-owned order survives; if nobody pays before the hold expires,
   every seat is released and nobody is charged.
2. **`team_min_size` enforcement** → **warning only, not a gate** (default
   `team_min_size_enforced=false`). Enforcing it would contradict D3 (solo is a
   valid default); the row shows "Need 1 more member by <date>" and the admin
   can turn enforcement on per edition.

Defaults chosen for the two that were still open (change them in Admin, not
code):

3. **Cancellation outside the cutoff** → **refund to the original method,
   always**. No account credit exists (D12).
4. **Free events** (`list price ₹0`) → **never consume the included allowance**.

---

## Appendix A — old → new mapping

| Today | After |
|---|---|
| `Select Events` page | `My Events` worklist |
| "Eligible included events" + "Additional paid events" | one row list with a price pill |
| client `withinCap` / `addonTotal` | server `quote` |
| `POST /registrations` batch | `POST /quote` + `POST /checkout` |
| `TEAM_EVENT_REQUIRES_TEAM` | allowed solo; team optional |
| create team creates the seat | seat exists first; team attaches |
| `My Registrations & Teams` tabs | teams inline on the worklist row |
| invite **code** typed by hand | invite **link** `/team/<code>` + code fallback |
| leader leave → `disband_team()` | elder promoted; disband only when empty |
| team payment via leader's registration | `Team.order_id` |
| `capacity_usage` counts teams only | live teams + solo entries |
| `IncludedEventSelection` source of truth | derived; `Registration.kind` is truth |

## Appendix B — files to change

**Backend:** `models/commerce.py`, `models/edition.py` (no change expected),
`schemas/participant.py`, `services/pricing.py` (new), `services/registrations.py`,
`services/teams.py`, `services/passes.py`, `services/events.py`,
`services/payments.py` (refunds), `api/v1/participant.py`,
`api/v1/public.py`, `migrations/versions/<new>.py`, tests.

**Frontend:** `pages/Portal.jsx` (shrinks), `pages/Worklist.jsx` (new),
`pages/JoinInvite.jsx` (new), `components/worklist/*` (new),
`lib/api.js`, `App.jsx` (routes), `pages/Admin.jsx` (Events & pricing),
`style.css` / `styles/inner-pages.css` (worklist styles).

**Docs:** this file, `docs/README.md` (index), `docs/api/reference.md`,
`docs/features/public-and-portals.md`.
