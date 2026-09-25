/**
 * offline/db.ts
 * Dexie (IndexedDB wrapper) schema for MAITRI offline-first storage.
 *
 * Three tables:
 *  - pendingRegistrations : new woman registrations waiting for network sync
 *  - pendingVisits        : antenatal visit records waiting for network sync
 *  - cachedWomen          : server-fetched woman records cached locally for
 *                           offline reading
 */
import Dexie, { type Table } from 'dexie'

/** A woman registration that was created offline and is yet to be synced. */
export interface PendingRegistration {
  /** Client-generated UUID (used as the permanent ID once synced). */
  id: string
  /** Full form payload, keyed by field name. */
  data: Record<string, unknown>
  /** ISO-8601 timestamp of local creation. */
  createdAt: string
  /**
   * Dexie stores booleans as 0/1 for indexing — keep as boolean in TS,
   * Dexie handles the coercion when querying `.equals(0)`.
   */
  synced: boolean
}

/** An antenatal visit log created offline. */
export interface PendingVisit {
  id: string
  /** The woman this visit belongs to. */
  womanId: string
  data: Record<string, unknown>
  createdAt: string
  synced: boolean
}

/** A woman record fetched from the server and stored locally for offline access. */
export interface CachedWoman {
  id: string
  data: Record<string, unknown>
  updatedAt: string
}

/** Singleton Dexie database class for the MAITRI app. */
export class MaitriDatabase extends Dexie {
  pendingRegistrations!: Table<PendingRegistration>
  pendingVisits!: Table<PendingVisit>
  cachedWomen!: Table<CachedWoman>

  constructor() {
    super('MaitriDB')
    this.version(1).stores({
      // Primary key + indexed fields for efficient queries
      pendingRegistrations: 'id, synced, createdAt',
      pendingVisits:        'id, womanId, synced, createdAt',
      cachedWomen:          'id, updatedAt'
    })
  }
}

/** Exported singleton — import this everywhere instead of creating new instances. */
export const db = new MaitriDatabase()
