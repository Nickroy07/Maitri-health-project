/**
 * pages/WomanDetail.tsx
 * Detail view for a single registered woman.
 *
 * Features:
 *  - Fetches woman record from /api/prioritise/queue and filters by :id
 *    (falls back gracefully if no dedicated GET /woman/:id endpoint exists yet)
 *  - Risk trend chart via recharts LineChart using /api/visits/:id/visits
 *  - Log New Visit inline form → POST /api/visits/:id
 *  - Raise Referral button → POST /api/referral/:id/raise
 *  - Displays escalation flags as pill tags
 */
import { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import axios from 'axios'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine
} from 'recharts'

// ── Types ────────────────────────────────────────────────────────────────────

interface Woman {
  id:             string
  full_name:      string
  age?:           number
  village?:       string
  district?:      string
  phone?:         string
  risk_band:      string
  priority_score: number
  flags?:         string[]
  abha_id?:       string
  gestational_age_weeks_at_registration?: number
  travel_time_to_frtu_minutes?: number
  haemoglobin_g_dl?: number
  systolic_bp?: number
  diastolic_bp?: number
}

interface Visit {
  id:                  string
  visit_date:          string
  updated_risk_score:  number
  haemoglobin_g_dl?:   number
  systolic_bp?:        number
  diastolic_bp?:       number
  weight_kg?:          number
  fundal_height_cm?:   number
  danger_sign?:        boolean
  reason_codes?:       string[]
}

interface VisitForm {
  haemoglobin_g_dl: string
  systolic_bp:      string
  diastolic_bp:     string
  weight_kg:        string
  fundal_height_cm: string
  danger_sign:      boolean
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function riskBadgeClass(band: string): string {
  if (band === 'high')   return 'badge risk-high text-sm px-3 py-1'
  if (band === 'medium') return 'badge risk-medium text-sm px-3 py-1'
  return 'badge risk-low text-sm px-3 py-1'
}

function formatDate(isoString: string): string {
  return new Date(isoString).toLocaleDateString('en-IN', {
    day: 'numeric', month: 'short', year: 'numeric'
  })
}

const VISIT_FORM_DEFAULT: VisitForm = {
  haemoglobin_g_dl: '',
  systolic_bp:      '',
  diastolic_bp:     '',
  weight_kg:        '',
  fundal_height_cm: '',
  danger_sign:      false,
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function WomanDetail() {
  const { id }    = useParams<{ id: string }>()
  const navigate  = useNavigate()

  const [woman,        setWoman]        = useState<Woman | null>(null)
  const [visits,       setVisits]       = useState<Visit[]>([])
  const [loading,      setLoading]      = useState(true)
  const [error,        setError]        = useState<string | null>(null)
  const [visitForm,    setVisitForm]    = useState<VisitForm>(VISIT_FORM_DEFAULT)
  const [visitLoading, setVisitLoading] = useState(false)
  const [visitSuccess, setVisitSuccess] = useState(false)
  const [referralMsg,  setReferralMsg]  = useState<string | null>(null)

  // ── Fetch data ────────────────────────────────────────────────────────────

  const fetchData = useCallback(async () => {
    if (!id) return
    setLoading(true)
    setError(null)
    try {
      // Fetch woman from the queue endpoint (no dedicated get-by-id yet)
      const [queueRes, visitsRes] = await Promise.all([
        axios.get<{ queue: Woman[] }>('/api/prioritise/queue', { params: { capacity: 500 } }),
        axios.get<{ visits: Visit[] }>(`/api/visits/${id}/visits`),
      ])

      const found = (queueRes.data.queue ?? []).find(w => w.id === id)
      if (!found) {
        setError('Patient not found in queue.')
      } else {
        setWoman(found)
      }
      setVisits(visitsRes.data.visits ?? [])
    } catch (err) {
      console.warn('[MAITRI] WomanDetail fetch error:', err)
      setError('Could not load patient data. Backend may be offline.')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { fetchData() }, [fetchData])

  // ── Log new visit ─────────────────────────────────────────────────────────

  const handleVisitSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!id) return
    setVisitLoading(true)
    setVisitSuccess(false)
    try {
      await axios.post(`/api/visits/${id}`, {
        haemoglobin_g_dl:  visitForm.haemoglobin_g_dl  ? Number(visitForm.haemoglobin_g_dl)  : null,
        systolic_bp:       visitForm.systolic_bp        ? Number(visitForm.systolic_bp)        : null,
        diastolic_bp:      visitForm.diastolic_bp       ? Number(visitForm.diastolic_bp)       : null,
        weight_kg:         visitForm.weight_kg          ? Number(visitForm.weight_kg)          : null,
        fundal_height_cm:  visitForm.fundal_height_cm   ? Number(visitForm.fundal_height_cm)   : null,
        danger_sign:       visitForm.danger_sign,
      })
      setVisitSuccess(true)
      setVisitForm(VISIT_FORM_DEFAULT)
      fetchData() // refresh chart + woman data
    } catch (err) {
      console.error('[MAITRI] Visit submit failed:', err)
      alert('Failed to save visit. Please try again.')
    } finally {
      setVisitLoading(false)
    }
  }

  // ── Raise referral ────────────────────────────────────────────────────────

  const handleRaiseReferral = async () => {
    if (!id) return
    setReferralMsg(null)
    try {
      await axios.post(`/api/referral/${id}/raise`)
      setReferralMsg('✓ Referral raised successfully. Track it in the Referrals tab.')
    } catch (err) {
      console.error('[MAITRI] Raise referral failed:', err)
      setReferralMsg('⚠ Could not raise referral. Check connectivity.')
    }
  }

  // ── Chart data ────────────────────────────────────────────────────────────

  const chartData = visits
    .slice()
    .sort((a, b) => new Date(a.visit_date).getTime() - new Date(b.visit_date).getTime())
    .map(v => ({
      date:  formatDate(v.visit_date),
      score: parseFloat(v.updated_risk_score.toFixed(3)),
    }))

  const latestVisit = visits.length > 0
    ? visits.slice().sort((a, b) => new Date(b.visit_date).getTime() - new Date(a.visit_date).getTime())[0]
    : null

  // ── Render ────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="space-y-4 animate-pulse">
        <div className="h-8 bg-gray-200 rounded w-1/2" />
        <div className="card h-40 bg-gray-100" />
        <div className="card h-60 bg-gray-100" />
      </div>
    )
  }

  if (error || !woman) {
    return (
      <div className="text-center py-16 text-gray-500">
        <p className="text-2xl mb-2">⚠️</p>
        <p>{error ?? 'Patient not found.'}</p>
        <button className="btn-secondary mt-4" onClick={() => navigate(-1)}>
          ← Go Back
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-2xl mx-auto">

      {/* ── Back button ── */}
      <button className="text-sm text-maitri-600 hover:underline flex items-center gap-1" onClick={() => navigate(-1)}>
        ← Back to Dashboard
      </button>

      {/* ── Patient header card ── */}
      <div className="card">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold text-gray-900">{woman.full_name}</h2>
            <p className="text-sm text-gray-500 mt-0.5">
              ABHA: {woman.abha_id ?? 'MOCK-' + woman.id.slice(0, 8).toUpperCase()}
            </p>
          </div>
          <span className={riskBadgeClass(woman.risk_band)}>
            {woman.risk_band.toUpperCase()}
          </span>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
          {woman.age     && <Info label="Age"      value={`${woman.age} yrs`} />}
          {woman.village && <Info label="Village"  value={woman.village} />}
          {woman.district && <Info label="District" value={woman.district} />}
          {woman.phone   && <Info label="Phone"    value={woman.phone} />}
          {woman.gestational_age_weeks_at_registration !== undefined && (
            <Info label="GA at Registration" value={`${woman.gestational_age_weeks_at_registration} wks`} />
          )}
          {woman.travel_time_to_frtu_minutes !== undefined && (
            <Info label="Travel to FRU" value={`${woman.travel_time_to_frtu_minutes} min`} />
          )}
        </div>

        {/* Escalation flags */}
        {woman.flags && woman.flags.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {woman.flags.map(flag => (
              <span key={flag} className="badge bg-red-100 text-red-700">
                {flag}
              </span>
            ))}
          </div>
        )}

        {/* Raise referral */}
        <div className="mt-4">
          <button className="btn-primary text-sm" onClick={handleRaiseReferral}>
            🚑 Raise Referral
          </button>
          {referralMsg && (
            <p className="text-sm mt-2 text-gray-700">{referralMsg}</p>
          )}
        </div>
      </div>

      {/* ── Risk trend chart ── */}
      <div className="card">
        <h3 className="font-semibold text-gray-800 mb-4">Risk Score Trend</h3>
        {chartData.length === 0 ? (
          <p className="text-gray-400 text-sm text-center py-8">
            No visit data yet — log a visit below to start tracking.
          </p>
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={chartData} margin={{ top: 4, right: 16, left: -16, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis domain={[0, 1]} tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v: number) => v.toFixed(3)} />
              {/* Risk threshold reference line at 0.5 */}
              <ReferenceLine y={0.5} stroke="#ef4444" strokeDasharray="4 4" label={{ value: 'High threshold', fontSize: 10, fill: '#ef4444' }} />
              <Line
                type="monotone"
                dataKey="score"
                stroke="#7c3aed"
                strokeWidth={2}
                dot={{ r: 4, fill: '#7c3aed' }}
                activeDot={{ r: 6 }}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* ── Latest visit reason codes ── */}
      {latestVisit?.reason_codes && latestVisit.reason_codes.length > 0 && (
        <div className="card">
          <h3 className="font-semibold text-gray-800 mb-3">Top Risk Reason Codes (Latest Visit)</h3>
          <ul className="space-y-1">
            {latestVisit.reason_codes.map(code => (
              <li key={code} className="text-sm text-gray-700 flex items-center gap-2">
                <span className="h-1.5 w-1.5 bg-maitri-500 rounded-full inline-block" />
                {code}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ── Log New Visit ── */}
      <div className="card">
        <h3 className="font-semibold text-gray-800 mb-4">Log New Visit</h3>

        {visitSuccess && (
          <div className="mb-4 bg-green-50 border border-green-200 text-green-700 px-4 py-2 rounded-lg text-sm">
            ✓ Visit logged successfully
          </div>
        )}

        <form onSubmit={handleVisitSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <VisitInput
              label="Haemoglobin (g/dL)"
              name="haemoglobin_g_dl"
              value={visitForm.haemoglobin_g_dl}
              onChange={val => setVisitForm(p => ({ ...p, haemoglobin_g_dl: val }))}
            />
            <VisitInput
              label="Weight (kg)"
              name="weight_kg"
              value={visitForm.weight_kg}
              onChange={val => setVisitForm(p => ({ ...p, weight_kg: val }))}
            />
            <VisitInput
              label="Systolic BP (mmHg)"
              name="systolic_bp"
              value={visitForm.systolic_bp}
              onChange={val => setVisitForm(p => ({ ...p, systolic_bp: val }))}
            />
            <VisitInput
              label="Diastolic BP (mmHg)"
              name="diastolic_bp"
              value={visitForm.diastolic_bp}
              onChange={val => setVisitForm(p => ({ ...p, diastolic_bp: val }))}
            />
            <VisitInput
              label="Fundal Height (cm)"
              name="fundal_height_cm"
              value={visitForm.fundal_height_cm}
              onChange={val => setVisitForm(p => ({ ...p, fundal_height_cm: val }))}
            />
          </div>

          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={visitForm.danger_sign}
              onChange={e => setVisitForm(p => ({ ...p, danger_sign: e.target.checked }))}
              className="h-5 w-5 rounded border-gray-300 text-red-500 focus:ring-red-400"
            />
            <span className="text-sm font-medium text-red-700">Danger sign observed at this visit</span>
          </label>

          <button
            type="submit"
            disabled={visitLoading}
            className="btn-primary text-sm"
          >
            {visitLoading ? 'Saving…' : 'Save Visit'}
          </button>
        </form>
      </div>

    </div>
  )
}

// ── Mini helpers ─────────────────────────────────────────────────────────────

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-gray-400 text-xs">{label}</span>
      <p className="font-medium text-gray-800">{value}</p>
    </div>
  )
}

function VisitInput({
  label, name, value, onChange
}: {
  label: string
  name: string
  value: string
  onChange: (val: string) => void
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-gray-600 mb-1">{label}</label>
      <input
        type="number"
        name={name}
        value={value}
        onChange={e => onChange(e.target.value)}
        className="input-field"
        step="0.1"
      />
    </div>
  )
}
