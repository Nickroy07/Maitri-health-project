/**
 * pages/Register.tsx
 * Antenatal registration form for MAITRI field health workers.
 *
 * Behaviour:
 *  1. Validates all required fields inline.
 *  2. Saves the record to Dexie (IndexedDB) immediately so it survives offline.
 *  3. If the device is online, also POSTs to /api/register and marks synced=true.
 *  4. Displays a success banner with the server's risk score (online) or an
 *     offline-saved confirmation.
 *  5. Calls onPendingChange so the header badge updates.
 *
 * Sections:
 *  A. Personal Info
 *  B. Clinical Measurements
 *  C. Risk Indicators
 */
import { useState } from 'react'
import axios from 'axios'
import { db } from '../offline/db'
import { getPendingCount } from '../offline/sync'

// ── Types ────────────────────────────────────────────────────────────────────

interface RegisterProps {
  /** Callback to update the pending-sync badge count in the parent App. */
  onPendingChange: (count: number) => void
}

/** All form fields as a flat typed record. */
interface FormFields {
  full_name: string
  age: string
  district: string
  village: string
  phone: string
  parity: string
  gravida: string
  height_cm: string
  weight_kg: string
  haemoglobin_g_dl: string
  systolic_bp: string
  diastolic_bp: string
  obstetric_history_flag: boolean
  interpregnancy_interval_months: string
  travel_time_to_frtu_minutes: string
  gestational_age_weeks_at_registration: string
  danger_sign_reported: boolean
}

/** Shape of the /api/register success response. */
interface RegisterResponse {
  id: string
  risk_band: string
  risk_score: number
  flags: string[]
}

// ── Helpers ──────────────────────────────────────────────────────────────────

/** Generate a UUID v4 string in-browser (no external dependency). */
function uuidv4(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
  })
}

const DISTRICTS = ['Nandurbar', 'Palghar', 'Gadchiroli', 'Nashik', 'Amravati']

const INITIAL_FORM: FormFields = {
  full_name: '',
  age: '',
  district: '',
  village: '',
  phone: '',
  parity: '',
  gravida: '',
  height_cm: '',
  weight_kg: '',
  haemoglobin_g_dl: '',
  systolic_bp: '',
  diastolic_bp: '',
  obstetric_history_flag: false,
  interpregnancy_interval_months: '',
  travel_time_to_frtu_minutes: '',
  gestational_age_weeks_at_registration: '',
  danger_sign_reported: false,
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function Register({ onPendingChange }: RegisterProps) {
  const [form,    setForm]    = useState<FormFields>(INITIAL_FORM)
  const [errors,  setErrors]  = useState<Partial<Record<keyof FormFields, string>>>({})
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState<{ online: boolean; data?: RegisterResponse } | null>(null)

  // ── Field change handler ──────────────────────────────────────────────────

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>
  ) => {
    const { name, value, type } = e.target
    const checked = type === 'checkbox' ? (e.target as HTMLInputElement).checked : undefined
    setForm(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value,
    }))
    // Clear the inline error for this field when the user edits it
    if (errors[name as keyof FormFields]) {
      setErrors(prev => ({ ...prev, [name]: undefined }))
    }
  }

  // ── Validation ────────────────────────────────────────────────────────────

  const validate = (): boolean => {
    const e: Partial<Record<keyof FormFields, string>> = {}

    if (!form.full_name.trim())   e.full_name  = 'Full name is required'
    if (!form.age || Number(form.age) < 10 || Number(form.age) > 60)
      e.age = 'Enter a valid age (10–60)'
    if (!form.district)           e.district   = 'Select a district'
    if (!form.village.trim())     e.village    = 'Village is required'
    if (!form.parity || Number(form.parity) < 0)
      e.parity  = 'Enter parity (≥ 0)'
    if (!form.gravida || Number(form.gravida) < 1)
      e.gravida = 'Enter gravida (≥ 1)'
    if (!form.height_cm || Number(form.height_cm) < 100 || Number(form.height_cm) > 220)
      e.height_cm = 'Enter height in cm (100–220)'
    if (!form.weight_kg || Number(form.weight_kg) < 20 || Number(form.weight_kg) > 200)
      e.weight_kg = 'Enter weight in kg (20–200)'
    if (!form.haemoglobin_g_dl || Number(form.haemoglobin_g_dl) < 3 || Number(form.haemoglobin_g_dl) > 20)
      e.haemoglobin_g_dl = 'Enter Hb in g/dL (3–20)'
    if (!form.systolic_bp || Number(form.systolic_bp) < 60 || Number(form.systolic_bp) > 250)
      e.systolic_bp = 'Enter systolic BP (60–250 mmHg)'
    if (!form.diastolic_bp || Number(form.diastolic_bp) < 40 || Number(form.diastolic_bp) > 150)
      e.diastolic_bp = 'Enter diastolic BP (40–150 mmHg)'
    if (!form.travel_time_to_frtu_minutes || Number(form.travel_time_to_frtu_minutes) < 0)
      e.travel_time_to_frtu_minutes = 'Enter travel time in minutes'
    if (!form.gestational_age_weeks_at_registration ||
        Number(form.gestational_age_weeks_at_registration) < 1 ||
        Number(form.gestational_age_weeks_at_registration) > 42)
      e.gestational_age_weeks_at_registration = 'Gestational age must be 1–42 weeks'

    // Interpregnancy interval only required when parity > 0
    if (Number(form.parity) > 0 && !form.interpregnancy_interval_months)
      e.interpregnancy_interval_months = 'Required when parity > 0'

    setErrors(e)
    return Object.keys(e).length === 0
  }

  // ── Submit ────────────────────────────────────────────────────────────────

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!validate()) return
    setLoading(true)
    setSuccess(null)

    const clientId  = uuidv4()
    const createdAt = new Date().toISOString()

    // Coerce numeric strings and booleans for storage / API payload
    const payload = {
      ...form,
      age:                                    Number(form.age),
      parity:                                 Number(form.parity),
      gravida:                                Number(form.gravida),
      height_cm:                              Number(form.height_cm),
      weight_kg:                              Number(form.weight_kg),
      haemoglobin_g_dl:                       Number(form.haemoglobin_g_dl),
      systolic_bp:                            Number(form.systolic_bp),
      diastolic_bp:                           Number(form.diastolic_bp),
      travel_time_to_frtu_minutes:            Number(form.travel_time_to_frtu_minutes),
      gestational_age_weeks_at_registration:  Number(form.gestational_age_weeks_at_registration),
      interpregnancy_interval_months:         Number(form.parity) > 0
        ? Number(form.interpregnancy_interval_months)
        : null,
    }

    // ── 1. Always save to Dexie first (offline-safe) ──────────────────────
    await db.pendingRegistrations.add({
      id: clientId,
      data: payload,
      createdAt,
      synced: false,
    })

    // ── 2. Try to sync immediately if online ─────────────────────────────
    if (navigator.onLine) {
      try {
        const response = await axios.post<RegisterResponse>('/api/register', {
          ...payload,
          id: clientId,
        })
        // Mark the local record as synced
        await db.pendingRegistrations.update(clientId, { synced: true })
        setSuccess({ online: true, data: response.data })
      } catch (err) {
        console.warn('[MAITRI] Registration API failed, saved offline:', err)
        setSuccess({ online: false })
      }
    } else {
      setSuccess({ online: false })
    }

    // ── 3. Update the header badge ────────────────────────────────────────
    const newCount = await getPendingCount()
    onPendingChange(newCount)

    setForm(INITIAL_FORM)
    setLoading(false)
  }

  // ── Risk band colour helper ───────────────────────────────────────────────
  const riskClass = (band?: string) => {
    if (band === 'high')   return 'risk-high badge'
    if (band === 'medium') return 'risk-medium badge'
    return 'risk-low badge'
  }

  // ── Render helpers ────────────────────────────────────────────────────────

  /** Renders a labelled text / number input with inline error. */
  const Field = ({
    label, name, type = 'text', placeholder = '', required = true
  }: {
    label: string
    name: keyof FormFields
    type?: string
    placeholder?: string
    required?: boolean
  }) => (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">
        {label}{required && <span className="text-red-500 ml-0.5">*</span>}
      </label>
      <input
        type={type}
        name={name}
        value={form[name] as string}
        onChange={handleChange}
        placeholder={placeholder}
        className={`input-field ${errors[name] ? 'border-red-400 focus:ring-red-400' : ''}`}
      />
      {errors[name] && (
        <p className="text-xs text-red-600 mt-1">{errors[name]}</p>
      )}
    </div>
  )

  // ── JSX ───────────────────────────────────────────────────────────────────

  return (
    <div className="max-w-2xl mx-auto">
      <div className="mb-6">
        <h2 className="text-xl font-bold text-gray-900">Register New Patient</h2>
        <p className="text-sm text-gray-500 mt-1">
          All fields marked <span className="text-red-500">*</span> are required.
          Records are saved locally and synced when connected.
        </p>
      </div>

      {/* ── Success banner ── */}
      {success && (
        <div
          className={`mb-6 p-4 rounded-xl border ${
            success.online
              ? 'bg-green-50 border-green-200 text-green-800'
              : 'bg-yellow-50 border-yellow-200 text-yellow-800'
          }`}
        >
          {success.online ? (
            <>
              <p className="font-semibold">✓ Registration submitted successfully</p>
              {success.data && (
                <div className="mt-2 flex items-center gap-3">
                  <span>Risk band:</span>
                  <span className={riskClass(success.data.risk_band)}>
                    {success.data.risk_band.toUpperCase()}
                  </span>
                  <span className="text-sm text-gray-600">
                    Score: {success.data.risk_score.toFixed(3)}
                  </span>
                </div>
              )}
            </>
          ) : (
            <p className="font-semibold">
              📥 Saved offline — will sync automatically when connected
            </p>
          )}
        </div>
      )}

      <form onSubmit={handleSubmit} noValidate className="space-y-8">

        {/* ── Section A: Personal Info ── */}
        <section className="card space-y-4">
          <h3 className="text-base font-semibold text-maitri-700 border-b border-gray-100 pb-2">
            A. Personal Information
          </h3>

          <Field label="Full Name" name="full_name" placeholder="e.g. Savita Devi" />

          <div className="grid grid-cols-2 gap-4">
            <Field label="Age (years)" name="age" type="number" placeholder="25" />
            <Field label="Phone" name="phone" type="tel" placeholder="9876543210" required={false} />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              District <span className="text-red-500">*</span>
            </label>
            <select
              name="district"
              value={form.district}
              onChange={handleChange}
              className={`input-field ${errors.district ? 'border-red-400' : ''}`}
            >
              <option value="">— Select district —</option>
              {DISTRICTS.map(d => (
                <option key={d} value={d}>{d}</option>
              ))}
            </select>
            {errors.district && (
              <p className="text-xs text-red-600 mt-1">{errors.district}</p>
            )}
          </div>

          <Field label="Village / Hamlet" name="village" placeholder="e.g. Toranmal" />
        </section>

        {/* ── Section B: Clinical Measurements ── */}
        <section className="card space-y-4">
          <h3 className="text-base font-semibold text-maitri-700 border-b border-gray-100 pb-2">
            B. Clinical Measurements
          </h3>

          <div className="grid grid-cols-2 gap-4">
            <Field label="Parity (previous births)" name="parity" type="number" placeholder="0" />
            <Field label="Gravida (incl. current)" name="gravida" type="number" placeholder="1" />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <Field label="Height (cm)" name="height_cm" type="number" placeholder="155" />
            <Field label="Weight (kg)" name="weight_kg" type="number" placeholder="52" />
          </div>

          <Field
            label="Haemoglobin (g/dL)"
            name="haemoglobin_g_dl"
            type="number"
            placeholder="11.5"
          />

          <div className="grid grid-cols-2 gap-4">
            <Field label="Systolic BP (mmHg)" name="systolic_bp" type="number" placeholder="120" />
            <Field label="Diastolic BP (mmHg)" name="diastolic_bp" type="number" placeholder="80" />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <Field
              label="Gestational Age (weeks)"
              name="gestational_age_weeks_at_registration"
              type="number"
              placeholder="12"
            />
            <Field
              label="Travel Time to FRU (min)"
              name="travel_time_to_frtu_minutes"
              type="number"
              placeholder="60"
            />
          </div>

          {/* Interpregnancy interval — only relevant when parity > 0 */}
          {Number(form.parity) > 0 && (
            <Field
              label="Interpregnancy Interval (months)"
              name="interpregnancy_interval_months"
              type="number"
              placeholder="24"
            />
          )}
        </section>

        {/* ── Section C: Risk Indicators ── */}
        <section className="card space-y-4">
          <h3 className="text-base font-semibold text-maitri-700 border-b border-gray-100 pb-2">
            C. Risk Indicators
          </h3>

          <label className="flex items-start gap-3 cursor-pointer">
            <input
              type="checkbox"
              name="obstetric_history_flag"
              checked={form.obstetric_history_flag}
              onChange={handleChange}
              className="mt-1 h-5 w-5 rounded border-gray-300 text-maitri-600 focus:ring-maitri-500"
            />
            <span className="text-sm text-gray-700">
              <span className="font-medium">Previous obstetric complication</span>
              <br />
              <span className="text-gray-500">
                (e.g. PPH, pre-eclampsia, stillbirth, caesarean section)
              </span>
            </span>
          </label>

          <label className="flex items-start gap-3 cursor-pointer">
            <input
              type="checkbox"
              name="danger_sign_reported"
              checked={form.danger_sign_reported}
              onChange={handleChange}
              className="mt-1 h-5 w-5 rounded border-gray-300 text-red-500 focus:ring-red-400"
            />
            <span className="text-sm text-gray-700">
              <span className="font-medium text-red-700">Danger sign reported today</span>
              <br />
              <span className="text-gray-500">
                (e.g. severe headache, visual disturbance, bleeding, reduced fetal movement)
              </span>
            </span>
          </label>
        </section>

        {/* ── Submit ── */}
        <button
          type="submit"
          disabled={loading}
          className="btn-primary w-full py-3 text-base"
        >
          {loading ? 'Saving…' : 'Submit Registration'}
        </button>

      </form>
    </div>
  )
}
