/**
 * pages/ReferralTracker.tsx
 * Track and advance the status of open obstetric referrals.
 *
 * Status lifecycle:
 *   raised → bed_booked → ambulance_dispatched → arrived
 *                                              ↘ lost
 *
 * Each card shows woman info, time elapsed since raised, and one-tap
 * buttons to advance to the next valid status or mark as lost.
 */
import { useEffect, useState, useCallback } from 'react'
import axios from 'axios'

// ── Types ────────────────────────────────────────────────────────────────────

type ReferralStatus =
  | 'raised'
  | 'bed_booked'
  | 'ambulance_dispatched'
  | 'arrived'
  | 'lost'

interface Referral {
  event_id:   string
  woman_id:   string
  woman_name: string
  district:   string
  status:     ReferralStatus
  raised_at:  string
}

// ── Status helpers ────────────────────────────────────────────────────────────

/** Maps each status to the single "next" status in the lifecycle. */
const NEXT_STATUS: Partial<Record<ReferralStatus, ReferralStatus>> = {
  raised:               'bed_booked',
  bed_booked:           'ambulance_dispatched',
  ambulance_dispatched: 'arrived',
}

/** Human-readable label for each status. */
const STATUS_LABEL: Record<ReferralStatus, string> = {
  raised:               'Raised',
  bed_booked:           'Bed Booked',
  ambulance_dispatched: 'Ambulance Dispatched',
  arrived:              'Arrived',
  lost:                 'Lost to Follow-up',
}

/** Tailwind classes for the status badge. */
const STATUS_BADGE: Record<ReferralStatus, string> = {
  raised:               'badge bg-yellow-100 text-yellow-800 border border-yellow-200',
  bed_booked:           'badge bg-blue-100 text-blue-800 border border-blue-200',
  ambulance_dispatched: 'badge bg-orange-100 text-orange-800 border border-orange-200',
  arrived:              'badge bg-green-100 text-green-800 border border-green-200',
  lost:                 'badge bg-red-100 text-red-800 border border-red-200',
}

/** Label for the "advance" button at each stage. */
const ADVANCE_LABEL: Partial<Record<ReferralStatus, string>> = {
  raised:               'Confirm Bed Booked',
  bed_booked:           'Dispatch Ambulance',
  ambulance_dispatched: 'Mark Arrived',
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function timeSince(isoString: string): string {
  const ms   = Date.now() - new Date(isoString).getTime()
  const mins = Math.floor(ms / 60_000)
  if (mins < 60)    return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24)     return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function ReferralTracker() {
  const [referrals, setReferrals] = useState<Referral[]>([])
  const [loading,   setLoading]   = useState(true)
  const [error,     setError]     = useState<string | null>(null)
  /** Tracks which event IDs are currently being updated to disable buttons. */
  const [updating,  setUpdating]  = useState<Set<string>>(new Set())

  const fetchReferrals = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await axios.get<{ referrals: Referral[] }>('/api/referral/open')
      setReferrals(res.data.referrals ?? [])
    } catch (err) {
      console.warn('[MAITRI] Referral fetch failed:', err)
      setError('Could not load referrals. Backend may be offline.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchReferrals() }, [fetchReferrals])

  // ── Status advance ────────────────────────────────────────────────────────

  const advanceStatus = async (eventId: string, newStatus: ReferralStatus) => {
    setUpdating(prev => new Set(prev).add(eventId))
    try {
      await axios.post(`/api/referral/${eventId}/status`, { status: newStatus })
      // Optimistic update — re-fetch to ensure server state is reflected
      await fetchReferrals()
    } catch (err) {
      console.error('[MAITRI] Status update failed:', err)
      alert('Could not update referral status. Please try again.')
    } finally {
      setUpdating(prev => {
        const next = new Set(prev)
        next.delete(eventId)
        return next
      })
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900">Referral Tracker</h2>
          <p className="text-sm text-gray-500">Track and advance open obstetric referrals</p>
        </div>
        <button
          onClick={fetchReferrals}
          disabled={loading}
          className="btn-secondary text-sm"
        >
          {loading ? '⟳ Loading…' : '⟳ Refresh'}
        </button>
      </div>

      {/* ── Error banner ── */}
      {error && (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 px-4 py-3 rounded-lg text-sm">
          ⚠️ {error}
        </div>
      )}

      {/* ── Loading skeleton ── */}
      {loading && (
        <div className="space-y-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="card animate-pulse h-28 bg-gray-100" />
          ))}
        </div>
      )}

      {/* ── Empty state ── */}
      {!loading && referrals.length === 0 && !error && (
        <div className="text-center py-16 text-gray-400">
          <p className="text-4xl mb-3">🚑</p>
          <p className="font-medium">No open referrals</p>
          <p className="text-sm">All referrals are closed or none have been raised yet.</p>
        </div>
      )}

      {/* ── Referral cards ── */}
      {!loading && referrals.map(ref => {
        const nextStatus = NEXT_STATUS[ref.status]
        const isBusy     = updating.has(ref.event_id)

        return (
          <div
            key={ref.event_id}
            className="card border-l-4"
            style={{
              borderLeftColor:
                ref.status === 'raised'               ? '#eab308' :
                ref.status === 'bed_booked'           ? '#3b82f6' :
                ref.status === 'ambulance_dispatched' ? '#f97316' :
                ref.status === 'arrived'              ? '#22c55e' :
                                                        '#ef4444'
            }}
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="font-semibold text-gray-900">{ref.woman_name}</p>
                <p className="text-sm text-gray-500">{ref.district}</p>
                <p className="text-xs text-gray-400 mt-1">
                  Raised {timeSince(ref.raised_at)}
                </p>
              </div>
              <span className={STATUS_BADGE[ref.status]}>
                {STATUS_LABEL[ref.status]}
              </span>
            </div>

            {/* Action buttons — only shown for non-terminal statuses */}
            {ref.status !== 'arrived' && ref.status !== 'lost' && (
              <div className="mt-4 flex flex-wrap gap-2">
                {nextStatus && (
                  <button
                    disabled={isBusy}
                    onClick={() => advanceStatus(ref.event_id, nextStatus)}
                    className="btn-primary text-sm py-1.5 disabled:opacity-50"
                  >
                    {isBusy ? 'Updating…' : ADVANCE_LABEL[ref.status]}
                  </button>
                )}
                <button
                  disabled={isBusy}
                  onClick={() => advanceStatus(ref.event_id, 'lost')}
                  className="btn-secondary text-sm py-1.5 text-red-600 border-red-200 hover:bg-red-50"
                >
                  Mark Lost
                </button>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
