/**
 * offline/sync.ts
 * Background sync utilities for MAITRI.
 *
 * When the device is offline, records are stored in IndexedDB (via Dexie).
 * When connectivity returns the `online` event fires, `flushPendingRecords`
 * POSTs everything to the FastAPI /sync endpoint in a single batch.
 */
import { db } from './db'
import axios from 'axios'

const API_BASE = '/api'

export interface SyncResult {
  registrations: number
  visits: number
}

/**
 * Push all un-synced registrations and visits to the server in one request.
 * Marks them as synced on success; silently swallows errors so the caller
 * can proceed without breaking the UI.
 */
export async function flushPendingRecords(): Promise<SyncResult> {
  // Dexie indexes booleans as 0/1 — query with the numeric equivalent
  const unsyncedRegs   = await db.pendingRegistrations.where('synced').equals(0).toArray()
  const unsyncedVisits = await db.pendingVisits.where('synced').equals(0).toArray()

  if (unsyncedRegs.length === 0 && unsyncedVisits.length === 0) {
    return { registrations: 0, visits: 0 }
  }

  try {
    const response = await axios.post<SyncResult>(`${API_BASE}/sync`, {
      registrations: unsyncedRegs.map(r => ({ ...r.data, id: r.id })),
      visits: unsyncedVisits.map(v => ({
        ...v.data,
        id: v.id,
        woman_id: v.womanId
      }))
    })

    // Mark all as synced after a successful response
    await db.pendingRegistrations.where('synced').equals(0).modify({ synced: true })
    await db.pendingVisits.where('synced').equals(0).modify({ synced: true })

    return response.data
  } catch (err) {
    console.warn('[MAITRI] Sync failed — will retry when online:', err)
    return { registrations: 0, visits: 0 }
  }
}

/**
 * Register a window `online` listener that triggers a flush automatically.
 * @param onSync — callback invoked with the sync result after a successful flush
 */
export function setupOnlineListener(
  onSync: (result: SyncResult) => void
): void {
  window.addEventListener('online', async () => {
    console.log('[MAITRI] Back online — flushing pending records')
    const result = await flushPendingRecords()
    onSync(result)
  })
}

/**
 * Returns the total count of records not yet synced to the server.
 * Used to display the pending-sync badge in the header.
 */
export async function getPendingCount(): Promise<number> {
  const regs   = await db.pendingRegistrations.where('synced').equals(0).count()
  const visits = await db.pendingVisits.where('synced').equals(0).count()
  return regs + visits
}
