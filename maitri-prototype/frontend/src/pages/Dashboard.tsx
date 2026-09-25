/**
 * pages/Dashboard.tsx
 * Priority queue dashboard for MAITRI field health workers.
 *
 * - Loads summary stats from GET /api/dashboard/summary
 * - Loads the prioritised queue from GET /api/prioritise/queue?capacity=50
 * - Renders 4 summary cards + a sortable risk table
 * - Handles loading skeletons and offline/error fallback states
 */
import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'

// ── Types ────────────────────────────────────────────────────────────────────

interface DashboardSummary {
  total_registered: number
  high_risk_count:  number
  open_referrals:   number
  postnatal_due_today: number
}

interface QueueEntry {
  id:             string
  full_name:      string
  village:        string
  district:       string
  risk_band:      'high' | 'medium' | 'low'
  priority_score: number
  last_contact:   string | null
  travel_time_to_frtu_minutes: number
  rank:           number
}

type SortKey = 'rank' | 'risk_band' | 'priority_score' | 'full_name'

// ── Helpers ──────────────────────────────────────────────────────────────────

const RISK_BAND_RANK: Record<string, number> = { high: 0, medium: 1, low: 2 }

/** Formats a date string as a human-readable relative time. */
function relativeTime(isoString: string | null): string {
  if (!isoString) return 'Never'
  const diff = Date.now() - new Date(isoString).getTime()
  const days = Math.floor(diff / 86_400_000)
  if (days === 0) return 'Today'
  if (days === 1) return '1 day ago'
  return `${days} days ago`
}

/** Returns Tailwind class names for the coloured risk badge. */
function riskBadgeClass(band: string): string {
  if (band === 'high')   return 'badge risk-high'
  if (band === 'medium') return 'badge risk-medium'
  return 'badge risk-low'
}

// ── Sub-components ────────────────────────────────────────────────────────────

function SkeletonCard() {
  return (
    <div className="card animate-pulse">
      <div className="h-4 bg-gray-200 rounded w-3/4 mb-2" />
      <div className="h-8 bg-gray-200 rounded w-1/2" />
    </div>
  )
}

function SkeletonRow() {
  return (
    <tr>
      {Array.from({ length: 7 }).map((_, i) => (
        <td key={i} className="px-4 py-3">
          <div className="h-4 bg-gray-200 rounded animate-pulse" />
        </td>
      ))}
    </tr>
  )
}

interface SummaryCardProps {
  label: string
  value: number | string
  colour: string
  icon: string
}

function SummaryCard({ label, value, colour, icon }: SummaryCardProps) {
  return (
    <div className={`card flex items-center gap-4 border-l-4 ${colour}`}>
      <span className="text-3xl">{icon}</span>
      <div>
        <p className="text-2xl font-bold text-gray-900">{value}</p>
        <p className="text-sm text-gray-500">{label}</p>
      </div>
    </div>
  )
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function Dashboard() {
  const navigate = useNavigate()

  const [summary,    setSummary]    = useState<DashboardSummary | null>(null)
  const [queue,      setQueue]      = useState<QueueEntry[]>([])
  const [loading,    setLoading]    = useState(true)
  const [error,      setError]      = useState<string | null>(null)
  const [sortKey,    setSortKey]    = useState<SortKey>('rank')
  const [sortAsc,    setSortAsc]    = useState(true)

  // ── Data fetching ────────────────────────────────────────────────────────

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [summaryRes, queueRes] = await Promise.all([
        axios.get<DashboardSummary>('/api/dashboard/summary'),
        axios.get<{ queue: QueueEntry[] }>('/api/prioritise/queue', {
          params: { capacity: 50 }
        }),
      ])
      setSummary(summaryRes.data)
      setQueue(queueRes.data.queue ?? [])
    } catch (err) {
      console.warn('[MAITRI] Dashboard fetch failed:', err)
      setError('Backend offline — showing cached data')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  // ── Sorting ──────────────────────────────────────────────────────────────

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortAsc(prev => !prev)
    } else {
      setSortKey(key)
      setSortAsc(true)
    }
  }

  const sortedQueue = [...queue].sort((a, b) => {
    let cmp = 0
    if (sortKey === 'rank')           cmp = a.rank - b.rank
    else if (sortKey === 'risk_band') cmp = RISK_BAND_RANK[a.risk_band] - RISK_BAND_RANK[b.risk_band]
    else if (sortKey === 'priority_score') cmp = b.priority_score - a.priority_score
    else if (sortKey === 'full_name') cmp = a.full_name.localeCompare(b.full_name)
    return sortAsc ? cmp : -cmp
  })

  const SortHeader = ({ label, col }: { label: string; col: SortKey }) => (
    <th
      className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide cursor-pointer hover:text-gray-800 select-none"
      onClick={() => handleSort(col)}
    >
      {label}
      {sortKey === col && (sortAsc ? ' ↑' : ' ↓')}
    </th>
  )

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-gray-900">Dashboard</h2>
        <button
          onClick={fetchData}
          disabled={loading}
          className="btn-secondary text-sm flex items-center gap-1"
        >
          {loading ? '⟳ Loading…' : '⟳ Refresh'}
        </button>
      </div>

      {/* ── Error banner ── */}
      {error && (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 px-4 py-3 rounded-lg text-sm flex items-center gap-2">
          ⚠️ {error}
        </div>
      )}

      {/* ── Summary cards ── */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {loading ? (
          Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)
        ) : summary ? (
          <>
            <SummaryCard label="Registered"       value={summary.total_registered}  colour="border-maitri-500" icon="👩‍🍼" />
            <SummaryCard label="High Risk"         value={summary.high_risk_count}   colour="border-red-400"    icon="🔴" />
            <SummaryCard label="Open Referrals"    value={summary.open_referrals}    colour="border-blue-400"   icon="🚑" />
            <SummaryCard label="Postnatal Due Today" value={summary.postnatal_due_today} colour="border-green-400" icon="👶" />
          </>
        ) : null}
      </div>

      {/* ── Priority queue table ── */}
      <div className="card overflow-hidden p-0">
        <div className="px-4 pt-4 pb-3 border-b border-gray-100">
          <h3 className="font-semibold text-gray-800">Priority Queue</h3>
          <p className="text-xs text-gray-500">Sorted by model-assigned risk priority</p>
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-100">
              <tr>
                <SortHeader label="#"          col="rank" />
                <SortHeader label="Name"       col="full_name" />
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  Village / District
                </th>
                <SortHeader label="Risk Band"  col="risk_band" />
                <SortHeader label="Score"      col="priority_score" />
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  Last Contact
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  FRU (min)
                </th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {loading ? (
                Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} />)
              ) : sortedQueue.length === 0 ? (
                <tr>
                  <td colSpan={8} className="text-center text-gray-400 py-10">
                    No women in queue
                  </td>
                </tr>
              ) : (
                sortedQueue.map(w => (
                  <tr
                    key={w.id}
                    className="hover:bg-gray-50 transition-colors cursor-pointer"
                    onClick={() => navigate(`/woman/${w.id}`)}
                  >
                    <td className="px-4 py-3 text-gray-400 font-mono">{w.rank}</td>
                    <td className="px-4 py-3 font-medium text-gray-900">{w.full_name}</td>
                    <td className="px-4 py-3 text-gray-500">
                      {w.village}<span className="text-gray-300 mx-1">/</span>{w.district}
                    </td>
                    <td className="px-4 py-3">
                      <span className={riskBadgeClass(w.risk_band)}>
                        {w.risk_band.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-700 font-mono">
                      {w.priority_score.toFixed(3)}
                    </td>
                    <td className="px-4 py-3 text-gray-500">{relativeTime(w.last_contact)}</td>
                    <td className="px-4 py-3 text-gray-500">{w.travel_time_to_frtu_minutes}</td>
                    <td className="px-4 py-3">
                      <button
                        className="btn-secondary text-xs py-1 px-3"
                        onClick={e => {
                          e.stopPropagation()
                          navigate(`/woman/${w.id}`)
                        }}
                      >
                        View
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
