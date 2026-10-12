import { useRef, useState } from 'react'
import { planTrip } from './api'
import Directions from './components/Directions'
import LogSheet from './components/LogSheet'
import RouteMap from './components/RouteMap'
import StopsTimeline from './components/StopsTimeline'
import Summary from './components/Summary'
import TripForm from './components/TripForm'
import { fmtDayLabel } from './format'
import type { TripPlan, TripRequest } from './types'

function Card({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
      {subtitle && <p className="mb-3 text-sm text-slate-500">{subtitle}</p>}
      <div className={subtitle ? '' : 'mt-3'}>{children}</div>
    </section>
  )
}

export default function App() {
  const [plan, setPlan] = useState<TripPlan | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [activeDay, setActiveDay] = useState(0)
  const abortRef = useRef<AbortController | null>(null)
  const resultsRef = useRef<HTMLDivElement>(null)

  const handleSubmit = async (req: TripRequest) => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setLoading(true)
    setError('')
    try {
      const result = await planTrip(req, controller.signal)
      setPlan(result)
      setActiveDay(0)
      requestAnimationFrame(() =>
        resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }),
      )
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      setPlan(null)
      setError(err instanceof Error ? err.message : 'Something went wrong.')
    } finally {
      if (abortRef.current === controller) setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-gradient-to-br from-slate-900 via-sky-950 to-sky-800 pb-24 pt-10 text-white">
        <div className="mx-auto max-w-6xl px-5">
          <p className="text-sm font-semibold uppercase tracking-widest text-sky-300">
            Hours of Service planner
          </p>
          <h1 className="mt-2 text-3xl font-bold sm:text-4xl">Trip planner &amp; ELD daily logs</h1>
          <p className="mt-3 max-w-2xl text-sky-100">
            Enter a trip and get the route, every fuel stop and rest, and fully drawn Driver&rsquo;s
            Daily Log sheets that follow the FMCSA 70-hour / 8-day property-carrying rules.
          </p>
        </div>
      </header>

      <main className="mx-auto -mt-16 max-w-6xl space-y-6 px-5 pb-16">
        <TripForm loading={loading} onSubmit={handleSubmit} />

        {error && (
          <div role="alert" className="whitespace-pre-line rounded-2xl border border-red-200 bg-red-50 p-4 text-red-800">
            <p className="font-semibold">We couldn&rsquo;t plan that trip</p>
            <p className="mt-1 text-sm">{error}</p>
          </div>
        )}

        {loading && !plan && (
          <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center text-slate-500 shadow-sm">
            Finding the route and building your log sheets — this can take up to 20 seconds.
          </div>
        )}

        {plan && (
          <div ref={resultsRef} className={`scroll-mt-6 space-y-6 transition-opacity ${loading ? 'opacity-50' : ''}`}>
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm shadow-sm">
              <span className="font-medium text-slate-500">Matched places:</span>
              {(
                [
                  ['Start', plan.locations.current.label],
                  ['Pickup', plan.locations.pickup.label],
                  ['Drop-off', plan.locations.dropoff.label],
                ] as const
              ).map(([role, label], i) => (
                <span key={role} className="flex items-center gap-2">
                  {i > 0 && <span className="text-slate-300">→</span>}
                  <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-800">
                    <span className="text-slate-500">{role}:</span> <strong>{label}</strong>
                  </span>
                </span>
              ))}
              <span className="ml-auto text-xs text-slate-400">
                Wrong place? Add the country, e.g. &ldquo;Sydney, Australia&rdquo;.
              </span>
            </div>

            <Summary plan={plan} />

            <div className="grid gap-6 lg:grid-cols-3">
              <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white p-2 shadow-sm lg:col-span-2">
                <RouteMap plan={plan} />
              </div>
              <Card title="Stops & rests" subtitle="In order, with times">
                <StopsTimeline plan={plan} />
              </Card>
            </div>

            <Directions plan={plan} />

            <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="text-lg font-semibold text-slate-900">Daily log sheets</h2>
              <p className="mb-4 text-sm text-slate-500">
                One sheet per calendar day · each totals 24 hours.
              </p>
              <div role="tablist" className="mb-5 flex flex-wrap gap-2">
                {plan.logs.map((log, i) => (
                  <button
                    key={log.date}
                    role="tab"
                    aria-selected={i === activeDay}
                    type="button"
                    onClick={() => setActiveDay(i)}
                    className={`rounded-full px-4 py-1.5 text-sm font-medium transition ${
                      i === activeDay
                        ? 'bg-sky-700 text-white shadow'
                        : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                    }`}
                  >
                    Day {log.day} · {fmtDayLabel(log.date)}
                  </button>
                ))}
              </div>
              <LogSheet log={plan.logs[activeDay]} />
            </section>
          </div>
        )}
      </main>

      <footer className="pb-8 text-center text-xs text-slate-400">
        Map data &copy; OpenStreetMap contributors · Routing by OSRM · Rules: FMCSA 49 CFR Part 395
      </footer>
    </div>
  )
}
