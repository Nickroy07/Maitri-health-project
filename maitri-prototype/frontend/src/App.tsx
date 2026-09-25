/**
 * App.tsx
 * Root component: sets up BrowserRouter, top nav, online/offline indicator,
 * and the pending-sync badge. All page routes are declared here.
 */
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { useEffect, useState } from 'react'
import Register from './pages/Register'
import Dashboard from './pages/Dashboard'
import WomanDetail from './pages/WomanDetail'
import ReferralTracker from './pages/ReferralTracker'
import PostnatalTracker from './pages/PostnatalTracker'
import Assistant from './pages/Assistant'
import { setupOnlineListener, getPendingCount } from './offline/sync'

function App() {
  const [pendingCount, setPendingCount] = useState<number>(0)
  const [isOnline, setIsOnline]         = useState<boolean>(navigator.onLine)

  useEffect(() => {
    // Hydrate the pending-sync badge on first render
    getPendingCount().then(setPendingCount)

    // Auto-flush and reset badge when connectivity returns
    setupOnlineListener((result) => {
      console.log('[MAITRI] Sync complete:', result)
      setPendingCount(0)
    })

    const goOnline  = () => setIsOnline(true)
    const goOffline = () => setIsOnline(false)
    window.addEventListener('online',  goOnline)
    window.addEventListener('offline', goOffline)

    return () => {
      window.removeEventListener('online',  goOnline)
      window.removeEventListener('offline', goOffline)
    }
  }, [])

  /** Returns the Tailwind class string for a nav link based on active state. */
  const navClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${
      isActive
        ? 'bg-maitri-600 text-white'
        : 'text-gray-600 hover:bg-gray-100'
    }`

  return (
    <BrowserRouter>
      <div className="min-h-screen flex flex-col">

        {/* ── Header ── */}
        <header className="bg-maitri-700 text-white px-4 py-3 flex items-center justify-between shadow-md">
          <div>
            <h1 className="text-lg font-bold tracking-tight">🌸 MAITRI</h1>
            <p className="text-xs text-purple-300">Maternal Health Tracker</p>
          </div>

          <div className="flex items-center gap-3">
            {/* Pending sync badge — shown only when there are unsynced records */}
            {pendingCount > 0 && (
              <span className="bg-yellow-400 text-yellow-900 text-xs font-bold px-2 py-1 rounded-full">
                {pendingCount} pending sync
              </span>
            )}

            {/* Online / offline pill */}
            <span
              className={`text-xs px-2 py-1 rounded-full ${
                isOnline
                  ? 'bg-green-500/20 text-green-200'
                  : 'bg-red-500/20 text-red-200'
              }`}
            >
              {isOnline ? '● Online' : '○ Offline'}
            </span>
          </div>
        </header>

        {/* ── Navigation ── */}
        <nav className="bg-white border-b border-gray-200 px-4 py-2 flex gap-2 overflow-x-auto">
          <NavLink to="/"          end className={navClass}>📋 Register</NavLink>
          <NavLink to="/dashboard"     className={navClass}>📊 Dashboard</NavLink>
          <NavLink to="/referrals"     className={navClass}>🚑 Referrals</NavLink>
          <NavLink to="/postnatal"     className={navClass}>👶 Postnatal</NavLink>
          <NavLink to="/assistant"     className={navClass}>💬 Assistant</NavLink>
        </nav>

        {/* ── Page Content ── */}
        <main className="flex-1 p-4 max-w-4xl mx-auto w-full">
          <Routes>
            <Route path="/"           element={<Register onPendingChange={setPendingCount} />} />
            <Route path="/dashboard"  element={<Dashboard />} />
            <Route path="/woman/:id"  element={<WomanDetail />} />
            <Route path="/referrals"  element={<ReferralTracker />} />
            <Route path="/postnatal"  element={<PostnatalTracker />} />
            <Route path="/assistant"  element={<Assistant />} />
          </Routes>
        </main>

      </div>
    </BrowserRouter>
  )
}

export default App
