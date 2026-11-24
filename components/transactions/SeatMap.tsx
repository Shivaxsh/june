"use client";
import type { SeatMap as Map } from "@/lib/transactions";

const WORDS = { free: "free", taken: "taken", blocked: "not available", accessible: "wheelchair space", selected: "June's pick for you" } as const;

/** A read-only seat map: the screen is at the top, rows go back from it, aisles are gaps. June's chosen block is
 * highlighted; choosing happens through the offers (never by tapping a single seat, so a group is never split). */
export default function SeatMap({ map, title }: { map: Map; title: string }) {
  const picked = map.rows.flatMap(r => r.seats.filter(s => s.status === "selected").map(s => `${r.label}${s.label}`));
  return <figure className="seat-map" aria-label={`Seat map for ${title}`}>
    <div className="seat-screen" aria-hidden="true">Screen</div>
    <div className="seat-rows">
      {map.rows.map(row => <div key={row.label} className="seat-row" role="group" aria-label={`Row ${row.label}`}>
        <span className="seat-row-label" aria-hidden="true">{row.label}</span>
        {row.seats.map((seat, i) => <span key={seat.id} className="seat-wrap">
          <span className={`seat is-${seat.status}`} role="img" aria-label={`Row ${row.label} seat ${seat.label}, ${WORDS[seat.status]}`} title={`${row.label}${seat.label}`} />
          {row.gapsAfter?.includes(i) && <span className="seat-aisle" aria-hidden="true" />}
        </span>)}
      </div>)}
    </div>
    <figcaption className="plan-step-meta">{picked.length ? `June's pick: ${picked.join(", ")} (together)` : "No seats picked yet"} · <span className="seat-key is-taken" aria-hidden="true" /> taken · <span className="seat-key is-accessible" aria-hidden="true" /> wheelchair space</figcaption>
  </figure>;
}
