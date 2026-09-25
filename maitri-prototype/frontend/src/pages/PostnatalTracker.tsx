/**
 * pages/PostnatalTracker.tsx
 * Tracks scheduled postnatal contacts for recently delivered mothers.
 *
 * Scheduled contact days per GoI protocol: Day 1, 3, 7, 14, 28, 42
 *
 * Two sections:
 *  - Due Today  — contacts whose scheduled date is today
 *  - Overdue    — contacts whose scheduled date has passed without being made
 *
 * Checking the checkbox calls POST /api/postnatal/contact/:id and removes
 * the contact from the list on success.
 */
import { useEffect, useState, useCallback } from 'react'
import axios from 'axios'

// ── Types ────────────────────────────────────────────────────────────────────

interface PostnatalContact {
  id:            string
  woman_id:      string
  woman_name:    string
  contact_day:   number   // e.g. 1, 3, 7, 14, 28, 42
  scheduled_date: string  // ISO date string
  days_overdue:  number   // 0 = due today, >0 = overdue
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatDate(isoDate: string): string {
  return new Date(isoDate).toLocaleDateString('en-IN', {
    day: 'numeric', month: 'short', year: 'numeric'
  })
}

// ── Sub-component: single contact row ────────────────────────────────────────

interface ContactCardProps {
  contact:   PostnatalContact
  overdue:   boolean
  onMarked:  (id: string) => void
}

function ContactCard({ contact, overdue, onMarked }: ContactCardProps) {
  const [loading, setLoading] = useState(false)
  const [done,    setDone]    = useState(false)

  const handleCheck = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.checked) return
    setLoading(true)
    try {
      await axios.post(`/api/postnatal/contact/${contact.id}`)
      setDone(true)
      // Notify parent so the list can refresh
      setTimeout(() => onMarked(contact.id), 600)
    } catch (err) {
      console.error('[MAITRI] Postnatal contact mark failed:', err)
      alert('Could not save. Please try again.')
      e.target.checked = false
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className={`card flex items-center gap-4 transition-opacity ${
        done ? 'opacity-40' : ''
      } ${overdue ? 'border-l-4 border-red-400' : 'border-l-4 border-green-400'}`}
    >
      {/* Checkbox */}
      <label className="flex items-center gap-3 cursor-pointer flex-1">
        <input
          type="checkbox"
          disabled={loading || done}
          onChange={handleCheck}
          className="h-6 w-6 rounded border-gray-300 text-maitri-600 focus:ring-maitri-500 cursor-pointer"
        />
        <div>
          <p className="font-medium text-gray-900">{contact.woman_name}</p>
          <p className="text-sm text-gray-500">
            <span className="font-semibold text-maitri-700">Day {contact.contact_day}</span>
            {' '}postnatal contact
            {' · '}
            Scheduled: {formatDate(contact.scheduled_date)}
          </p>
          {overdue && contact.days_overdue > 0 && (
            <p className="text-xs text-red-600 font-semibold mt-0.5">
              ⚠ {contact.days_overdue} day{contact.days_overdue !== 1 ? 's' : ''} overdue
            </p>
          )}
        </div>
      </label>

      {/* Status pill */}
      <span className={`text-xs font-medium px-2 py-1 rounded-full ${
        done    ? 'bg-green-100 text-green-700' :
        loading ? 'bg-gray-100 text-gray-500'   :
        overdue ? 'bg-red-100 text-red-700'     :
                  'bg-blue-100 text-blue-700'
      }`}>
        {done ? 'Done ✓' : loading ? 'Saving…' : overdue ? 'Overdue' : 'Due Today'}
      </span>
    </div>
  )
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function PostnatalTracker() {
  const [dueToday, setDueToday] = useState<PostnatalContact[]>([])
  const [overdue,  setOverdue]  = useState<PostnatalContact[]>([])
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [todayRes, overdueRes] = await Promise.all([
        axios.get<{ contacts: PostnatalContact[] }>('/api/postnatal/due/today'),
        axios.get<{ contacts: PostnatalContact[] }>('/api/postnatal/overdue'),
      ])
      setDueToday(todayRes.data.contacts ?? [])
      setOverdue(overdueRes.data.contacts ?? [])
    } catch (err) {
      console.warn('[MAITRI] Postnatal fetch failed:', err)
      setError('Could not load postnatal contacts. Backend may be offline.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  /** Remove a contact from either list after it has been marked. */
  const handleMarked = (id: string) => {
    setDueToday(prev => prev.filter(c => c.id !== id))
    setOverdue(prev => prev.filter(c => c.id !== id))
  }

  const total = dueToday.length + overdue.length

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900">Postnatal Tracker</h2>
          <p className="text-sm text-gray-500">
            Scheduled contacts per GoI postnatal care protocol (Day 1/3/7/14/28/42)
          </p>
        </div>
        <button
          onClick={fetchData}
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
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="card animate-pulse h-20 bg-gray-100" />
          ))}
        </div>
      )}

      {/* ── Empty state ── */}
      {!loading && total === 0 && !error && (
        <div className="text-center py-16 text-gray-400">
          <p className="text-4xl mb-3">👶</p>
          <p className="font-medium">No postnatal contacts due</p>
          <p className="text-sm">Check back tomorrow or after new deliveries are recorded.</p>
        </div>
      )}

      {/* ── Due Today ── */}
      {!loading && dueToday.length > 0 && (
        <section className="space-y-3">
          <h3 className="text-base font-semibold text-gray-700 flex items-center gap-2">
            <span className="h-2.5 w-2.5 bg-green-500 rounded-full inline-block" />
            Due Today
            <span className="badge bg-green-100 text-green-700 ml-1">{dueToday.length}</span>
          </h3>
          {dueToday.map(c => (
            <ContactCard key={c.id} contact={c} overdue={false} onMarked={handleMarked} />
          ))}
        </section>
      )}

      {/* ── Overdue ── */}
      {!loading && overdue.length > 0 && (
        <section className="space-y-3">
          <h3 className="text-base font-semibold text-gray-700 flex items-center gap-2">
            <span className="h-2.5 w-2.5 bg-red-500 rounded-full inline-block" />
            Overdue
            <span className="badge bg-red-100 text-red-700 ml-1">{overdue.length}</span>
          </h3>
          {overdue.map(c => (
            <ContactCard key={c.id} contact={c} overdue={true} onMarked={handleMarked} />
          ))}
        </section>
      )}
    </div>
  )
}
