import { useMemo } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, CalendarDays, MapPin } from "lucide-react";
import HudFrame from "../components/HudFrame.jsx";
import "./ScheduleBoard.css";

const MIN_BLOCK = 46;
const HOUR_H = 84;

const TONES = ["blue", "violet", "green", "amber", "rose", "cyan"];

function toneFor(text = "") {
  let hash = 0;
  for (let i = 0; i < text.length; i += 1) hash = (hash * 31 + text.charCodeAt(i)) % 997;
  return TONES[hash % TONES.length];
}

function minutesOf(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.getHours() * 60 + d.getMinutes();
}

function clockLabel(minutes) {
  const h24 = Math.floor(minutes / 60) % 24;
  const mins = minutes % 60;
  const suffix = h24 >= 12 ? "PM" : "AM";
  const h12 = h24 % 12 === 0 ? 12 : h24 % 12;
  return `${h12}${mins ? `:${String(mins).padStart(2, "0")}` : ""} ${suffix}`;
}

function durationLabel(mins) {
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  if (h && m) return `${h}h ${m}m`;
  if (h) return `${h}h`;
  return `${m}m`;
}

function dayName(dateStr, index) {
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return `Day 0${index + 1}`;
  return d.toLocaleDateString("en-US", { weekday: "long" });
}

function dayNumber(dateStr) {
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString("en-US", { day: "2-digit", month: "short" });
}

/** Greedy lane packing so overlapping sessions sit side by side. */
function layout(items) {
  const sorted = [...items].sort((a, b) => a.start - b.start || a.end - b.end);
  const lanes = [];
  const placed = sorted.map((item) => {
    let lane = lanes.findIndex((end) => end <= item.start);
    if (lane === -1) {
      lane = lanes.length;
      lanes.push(item.end);
    } else {
      lanes[lane] = item.end;
    }
    return { ...item, lane };
  });
  return { placed, laneCount: Math.max(1, lanes.length) };
}

export default function ScheduleBoard({ days }) {
  const model = useMemo(() => {
    const parsedDays = (days || []).map((day, index) => {
      const items = (day.items || [])
        .map((item) => {
          const start = minutesOf(item.startsAt);
          const end = minutesOf(item.endsAt);
          if (start === null) return null;
          return {
            ...item,
            start,
            end: end !== null && end > start ? end : start + 60,
            room: item.room || "Room TBA",
          };
        })
        .filter(Boolean);
      return { ...day, index, items };
    });

    const starts = parsedDays.flatMap((d) => d.items.map((i) => i.start));
    const ends = parsedDays.flatMap((d) => d.items.map((i) => i.end));
    const from = starts.length ? Math.floor(Math.min(...starts) / 60) * 60 : 9 * 60;
    const to = ends.length ? Math.ceil(Math.max(...ends) / 60) * 60 : 18 * 60;
    const hours = [];
    for (let m = from; m <= to; m += 60) hours.push(m);

    return { parsedDays, from, to: Math.max(to, from + 60), hours };
  }, [days]);

  const { parsedDays, from, to, hours } = model;
  const height = ((to - from) / 60) * HOUR_H;
  const total = parsedDays.reduce((sum, d) => sum + d.items.length, 0);
  const rangeLabel =
    parsedDays.length > 0
      ? `${dayNumber(parsedDays[0].date)} — ${dayNumber(parsedDays[parsedDays.length - 1].date)}`
      : "To be announced";

  return (
    <HudFrame as="section" className="sched-board" aria-label="Convention timetable">
      <header className="sched-head">
        <div className="sched-head-left">
          <span className="sched-head-icon" aria-hidden="true">
            <CalendarDays size={19} strokeWidth={1.7} />
          </span>
          <div>
            <h2 className="sched-head-title">The Programme</h2>
            <p className="sched-head-sub">
              {total} {total === 1 ? "session" : "sessions"} · {parsedDays.length}{" "}
              {parsedDays.length === 1 ? "day" : "days"}
            </p>
          </div>
        </div>

        <span className="sched-range-pill">{rangeLabel}</span>
      </header>

      <div
        className="sched-grid"
        style={{ "--hours": hours.length - 1, "--hour-h": `${HOUR_H}px` }}
      >
        <div className="sched-gutter" aria-hidden="true">
          <div className="sched-gutter-spacer" />
          {hours.slice(0, -1).map((m) => (
            <div key={m} className="sched-gutter-label">
              {clockLabel(m)}
            </div>
          ))}
        </div>

        {parsedDays.map((day) => {
          const { placed, laneCount } = layout(day.items);
          return (
            <div className="sched-day" key={day.date}>
              <div className="sched-day-head">
                <span className="sched-day-name">{dayName(day.date, day.index)}</span>
                <span className="sched-day-date">{dayNumber(day.date) || day.label}</span>
              </div>

              <div className="sched-day-track" style={{ height }}>
                {placed.length === 0 ? (
                  <p className="sched-empty">Sessions to be announced.</p>
                ) : (
                  placed.map((item) => {
                    const top = ((item.start - from) / 60) * HOUR_H;
                    const raw = ((item.end - item.start) / 60) * HOUR_H;
                    const blockHeight = Math.max(
                      MIN_BLOCK,
                      Math.min(raw - 6, height - top - 4)
                    );
                    const width = 100 / laneCount;
                    return (
                      <Link
                        key={item.id}
                        to={`/events/${item.slug}`}
                        className={`sched-block tone-${toneFor(item.category || item.title)}`}
                        style={{
                          top: `${top}px`,
                          height: `${blockHeight}px`,
                          left: `calc(${item.lane * width}% + 2px)`,
                          width: `calc(${width}% - 4px)`,
                        }}
                      >
                        <span className="sched-block-time">
                          {clockLabel(item.start)}
                          <em>{durationLabel(item.end - item.start)}</em>
                        </span>
                        <b className="sched-block-title">{item.title}</b>
                        <span className="sched-block-room">
                          <MapPin size={10} strokeWidth={1.9} />
                          {item.room}
                        </span>
                        <ArrowUpRight
                          size={12}
                          strokeWidth={1.9}
                          className="sched-block-arrow"
                        />
                      </Link>
                    );
                  })
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* small screens: the calendar becomes a plain, scannable agenda */}
      <div className="sched-agenda">
        {parsedDays.map((day) => (
          <section className="sched-agenda-day" key={`agenda-${day.date}`}>
            <header className="sched-agenda-head">
              <h3>{dayName(day.date, day.index)}</h3>
              <span>{dayNumber(day.date) || day.label}</span>
            </header>

            {day.items.length === 0 ? (
              <p className="sched-agenda-empty">Sessions to be announced.</p>
            ) : (
              <ul className="sched-agenda-list">
                {[...day.items]
                  .sort((a, b) => a.start - b.start)
                  .map((item) => (
                    <li key={`row-${item.id}`}>
                      <Link
                        to={`/events/${item.slug}`}
                        className={`sched-agenda-row tone-${toneFor(item.category || item.title)}`}
                      >
                        <span className="sched-agenda-time">
                          <b>{clockLabel(item.start)}</b>
                          <em>{durationLabel(item.end - item.start)}</em>
                        </span>
                        <span className="sched-agenda-body">
                          <b>{item.title}</b>
                          <span className="sched-agenda-room">
                            <MapPin size={10} strokeWidth={1.9} />
                            {item.room}
                          </span>
                        </span>
                        <ArrowUpRight size={14} strokeWidth={1.8} />
                      </Link>
                    </li>
                  ))}
              </ul>
            )}
          </section>
        ))}
      </div>

      <footer className="sched-foot">
        <span className="sched-legend">
          {["Computing", "Electronics", "Robotics", "Design"].map((label) => (
            <span key={label} className={`sched-legend-item tone-${toneFor(label)}`}>
              <i aria-hidden="true" />
              {label}
            </span>
          ))}
        </span>
        <span className="sched-foot-note">Times are live · tap any session for details</span>
      </footer>
    </HudFrame>
  );
}
