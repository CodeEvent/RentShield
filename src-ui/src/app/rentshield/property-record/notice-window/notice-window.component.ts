import { CommonModule } from '@angular/common'
import { Component, Input, computed, signal } from '@angular/core'
import { NgxBootstrapIconsModule } from 'ngx-bootstrap-icons'

export type NoticeWindowState = 'on-track' | 'approaching' | 'lapsed'

export interface NoticeWindow {
  /** Ejari contract expiry (the anchor for all the maths). */
  expiry: Date
  /** Statutory serve-by deadline = expiry minus 365 days (Art. 25(2)). */
  serveBy: Date
  /** Whole days from today to the serve-by deadline (negative once passed). */
  daysToServeBy: number
  /** Whole days from today to lease expiry (negative once passed). */
  daysToExpiry: number
  state: NoticeWindowState
  /** 0-100: how far "today" sits across the 365-day window (serveBy -> expiry). */
  progressPct: number
}

const MS_PER_DAY = 24 * 60 * 60 * 1000
/** A 12-month notice (sale / personal use / demolition / renovation) must be
 *  served at least this many days before the contract expiry. */
const STATUTORY_BUFFER_DAYS = 365
/** Inside this many days of the serve-by deadline we raise the amber alert. */
const APPROACH_ALERT_DAYS = 30

/** Midnight of the given date, so day counts never drift on part-days. */
function atMidnight(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate())
}

function diffDays(from: Date, to: Date): number {
  return Math.round((atMidnight(to).getTime() - atMidnight(from).getTime()) / MS_PER_DAY)
}

/**
 * Pure, deterministic Notice Window maths. No heuristics, no AI: given the
 * contract expiry date (and "today", injectable for tests), it returns the
 * serve-by deadline, the day counts, the state, and a progress percentage.
 */
export function computeNoticeWindow(expiry: Date, now: Date = new Date()): NoticeWindow {
  const serveBy = new Date(expiry.getTime() - STATUTORY_BUFFER_DAYS * MS_PER_DAY)
  const daysToServeBy = diffDays(now, serveBy)
  const daysToExpiry = diffDays(now, expiry)

  let state: NoticeWindowState
  if (daysToServeBy < 0) {
    state = 'lapsed'
  } else if (daysToServeBy <= APPROACH_ALERT_DAYS) {
    state = 'approaching'
  } else {
    state = 'on-track'
  }

  // Position of "today" across the 365-day window (serveBy -> expiry).
  const span = expiry.getTime() - serveBy.getTime()
  const raw = ((now.getTime() - serveBy.getTime()) / span) * 100
  const progressPct = Math.max(0, Math.min(100, raw))

  return { expiry, serveBy, daysToServeBy, daysToExpiry, state, progressPct }
}

/**
 * Deterministic "Notice Window" timeline for the property header. It renders
 * the statutory 365-day buffer as a three-milestone timeline (Today ->
 * Serve-by deadline -> Lease expiry) and warns when the window is approaching
 * or has lapsed. Purely date-driven; the same inputs always give the same
 * output.
 */
@Component({
  selector: 'app-notice-window',
  standalone: true,
  imports: [CommonModule, NgxBootstrapIconsModule],
  templateUrl: './notice-window.component.html',
  styleUrl: './notice-window.component.scss',
})
export class NoticeWindowComponent {
  readonly today = new Date()
  private readonly expiryDate = signal<Date | null>(null)

  /** Ejari contract expiry as an ISO date string (e.g. "2027-11-01"). */
  @Input({ required: true }) set expiry(value: string | Date | null | undefined) {
    if (!value) {
      this.expiryDate.set(null)
      return
    }
    const d = value instanceof Date ? value : new Date(value)
    this.expiryDate.set(isNaN(d.getTime()) ? null : d)
  }

  readonly win = computed<NoticeWindow | null>(() => {
    const e = this.expiryDate()
    return e ? computeNoticeWindow(e) : null
  })

  /** Absolute day counts for display (we show "ago" separately via state). */
  absServeBy = () => Math.abs(this.win()?.daysToServeBy ?? 0)
  absExpiry = () => Math.abs(this.win()?.daysToExpiry ?? 0)
}
