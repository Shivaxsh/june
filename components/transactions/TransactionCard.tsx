"use client";
import type { ReactNode } from "react";
import { DOMAIN_WORDS, rupees, STATUS_WORDS, type Transaction } from "@/lib/transactions";
import SeatMap from "./SeatMap";

type Props = {
  transaction: Transaction;
  /** The existing plan card for this purchase (exact-fingerprint approval lives there, never here). */
  planCard?: ReactNode;
  busy?: boolean;
  onChoose?: (offerId: string) => void;
  now?: number;
};

const free = (t: Transaction) => t.domain === "dining";  // dining reservations never charge
const money = (t: Transaction, minor: number) => free(t) ? "No charge" : rupees(minor);

/** One simulated purchase or booking: what June still needs, the offers, the exact quote, approval (via the plan card)
 * and the simulated receipt. Everything is labelled simulated; no card or payment details ever appear here. */
export default function TransactionCard({ transaction: t, planCard, busy = false, onChoose, now = Date.now() }: Props) {
  const quote = t.quote, receipt = t.receipt;
  const left = quote ? Math.max(0, Math.round((quote.expiresAt - now) / 1000)) : 0;
  return <section className={`transaction-card is-${t.status}`} aria-label={`${DOMAIN_WORDS[t.domain]} (simulated)`} data-transaction-id={t.id}>
    <div className="timer-head">
      <span className="hud-label">{DOMAIN_WORDS[t.domain]} · Simulated</span>
      <span className="plan-step-meta">{STATUS_WORDS[t.status]}</span>
    </div>
    {t.lastReply && <p>{t.lastReply}</p>}
    {t.missing.length > 0 && <p className="handsfree-note">June still needs: {t.missing.join(", ")}. Reply in chat.</p>}
    {Object.keys(t.slots).length > 0 && <p className="plan-step-meta">{Object.entries(t.slots).map(([k, v]) => `${k}: ${v}`).join(" · ")}</p>}

    {t.offers.length > 0 && !quote && <ul className="command-list" aria-label="Options">{t.offers.map(offer => <li key={offer.id}>
      <div><strong>{offer.title}</strong> · {offer.merchant} <span className="plan-step-meta">{money(t, offer.totalMinor)}</span>
        {offer.description && <span className="plan-step-meta">{offer.description}</span>}
        {!offer.available && <span className="plan-step-meta">Not available</span>}</div>
      {offer.seatMap && <SeatMap map={offer.seatMap} title={offer.title} />}
      {onChoose && <div className="timer-buttons"><button type="button" className="quiet-button" disabled={busy || !offer.available} onClick={() => onChoose(offer.id)}>Choose this</button></div>}
    </li>)}</ul>}

    {quote && <div className="transaction-quote" aria-label="Quote">
      <p><strong>{quote.summary}</strong></p>
      <table className="quote-lines"><tbody>
        {quote.lines.map((line, i) => <tr key={i}><td>{line.label}{line.quantity > 1 ? ` × ${line.quantity}` : ""}</td><td>{money(t, line.totalMinor)}</td></tr>)}
        <tr className="quote-total"><td>Total</td><td>{money(t, quote.totalMinor)}</td></tr>
      </tbody></table>
      {quote.terms && <p className="plan-step-meta">{quote.terms}</p>}
      {(t.status === "quoted" || t.status === "awaiting-approval") && <p className="plan-step-meta">{left > 0 ? `Price held for ${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}` : "This quote has expired; ask June for a fresh one."}</p>}
    </div>}

    {planCard}

    {receipt && <div className="transaction-receipt" aria-label="Simulated receipt">
      <p><strong>{receipt.status === "confirmed" ? "Simulated receipt" : "Simulated cancellation"}</strong> · {money(t, receipt.totalMinor)}</p>
      <p className="plan-step-meta">{receipt.detail} · {new Date(receipt.createdAt).toLocaleString()} · ref {receipt.id}</p>
      <p className="handsfree-note">Nothing was really bought, booked or charged: this is a simulation.</p>
    </div>}
    {t.status === "unknown" && <p className="handsfree-note">June couldn’t confirm the outcome. She’ll only read the receipt again, never place it twice.</p>}
  </section>;
}
