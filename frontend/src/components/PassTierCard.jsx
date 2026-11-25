import {
  ArrowRight,
  Award,
  CalendarDays,
  Check,
  GraduationCap,
  ShieldCheck,
  Sparkles,
  Ticket,
  Utensils,
} from 'lucide-react';

import { money } from '../lib/format.js';
import { passListPricePaise } from '../lib/pricing.js';
import './PassTierCard.css';

const FRAMES = {
  iste_member: {
    src: `${import.meta.env.BASE_URL}images/pass_frame_iste.png`,
    tag: 'ISTE Discount',
    tierCode: '2-DAY PASS',
    tone: 'iste',
  },
  non_iste: {
    src: `${import.meta.env.BASE_URL}images/pass_frame_non_iste.png`,
    tag: 'Standard Pass',
    tierCode: '2-DAY PASS',
    tone: 'standard',
  },
  polytechnic: {
    src: `${import.meta.env.BASE_URL}images/pass_frame_polytechnic.png`,
    tag: 'Polytechnic',
    tierCode: '2-DAY PASS',
    tone: 'polytechnic',
  },
};

function frameFor(category) {
  if (FRAMES[category?.code]) return FRAMES[category.code];
  const text = `${category?.name || ''} ${category?.description || ''}`.toLowerCase();
  if (text.includes('iste')) return FRAMES.iste_member;
  if (text.includes('polytechnic') || text.includes('diploma')) return FRAMES.polytechnic;
  return FRAMES.non_iste;
}

export function PassTierCard({ category, selected = false, disabled = false, onSelect }) {
  const frame = frameFor(category);
  const docs = category?.requiredDocuments || [];
  const TagIcon = frame.tone === 'iste' ? Sparkles : frame.tone === 'polytechnic' ? GraduationCap : Ticket;

  return (
    <button
      type="button"
      className={`pass-tier-card is-${frame.tone}${selected ? ' is-selected' : ''}`}
      aria-pressed={selected}
      aria-label={`${selected ? 'Selected' : 'Select'} ${category?.name || 'pass'}, ${money(category?.feePaise || 0)} per person`}
      disabled={disabled}
      onClick={() => onSelect?.(category)}
    >
      <img className="pass-tier-frame" src={frame.src} alt="" draggable="false" decoding="async" />

      <span className="pass-tier-bay">
        <span className="pass-tier-top-row">
          <span className="pass-tier-tag">
            <TagIcon size="0.95em" strokeWidth={2.2} aria-hidden="true" />
            {frame.tag}
          </span>
          <span className="pass-tier-code">{frame.tierCode}</span>
        </span>

        <span className="pass-tier-name">{category?.name || 'Convention pass'}</span>

        <span className="pass-tier-price">
          <s className="pass-tier-was">
            {money(passListPricePaise(category?.feePaise || 0))}
          </s>
          <b>{money(category?.feePaise || 0)}</b>
          <small>/ person</small>
        </span>

        <span className="pass-tier-desc">
          {category?.description ||
            'Full 2-day access with lunch, delegate kit and an official certificate.'}
        </span>

        <span className="pass-tier-perks">
          <span>
            <CalendarDays size="1em" strokeWidth={2.4} aria-hidden="true" />
            All 2-Day Events
          </span>
          <span>
            <Utensils size="1em" strokeWidth={2.4} aria-hidden="true" />
            Lunch &amp; Delegate Kit
          </span>
          <span>
            <Award size="1em" strokeWidth={2.4} aria-hidden="true" />
            Official Certificate
          </span>
        </span>
      </span>

      <span className="pass-tier-verify">
        <b className="pass-tier-verify-title">
          <ShieldCheck size="1em" strokeWidth={2.4} aria-hidden="true" />
          Required Verification
        </b>
        <span className="pass-tier-docs">
          {docs.length ? (
            docs.map((doc) => (
              <span className="pass-tier-doc" key={doc.type || doc.label}>
                {doc.label}
              </span>
            ))
          ) : (
            <span className="pass-tier-doc">College / University ID card</span>
          )}
        </span>
      </span>

      <span className="pass-tier-dock">
        {selected ? (
          <>
            <span>Selected</span>
            <Check size="1.05em" strokeWidth={2.75} aria-hidden="true" />
          </>
        ) : (
          <>
            <span>Select Pass</span>
            <ArrowRight size="1.05em" strokeWidth={2.6} aria-hidden="true" />
          </>
        )}
      </span>
    </button>
  );
}
