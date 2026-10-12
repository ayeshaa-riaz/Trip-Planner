import { useState } from 'react'
import { fmtMiles } from '../format'
import type { TripPlan } from '../types'

const LEGS = ['Current location → Pickup', 'Pickup → Drop-off']

export default function Directions({ plan }: { plan: TripPlan }) {
  const [open, setOpen] = useState(false)
  const { steps } = plan.route

  return (
    <section className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center justify-between px-5 py-4 text-left"
      >
        <span>
          <span className="block text-lg font-semibold text-slate-900">Route instructions</span>
          <span className="text-sm text-slate-500">{steps.length} steps · turn-by-turn directions</span>
        </span>
        <span className="text-slate-400">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="space-y-6 border-t border-slate-100 px-5 py-4">
          {LEGS.map((title, leg) => {
            const legSteps = steps.filter((s) => s.leg === leg)
            return (
              <div key={title}>
                <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
                  {title}
                </h3>
                <ol className="divide-y divide-slate-100">
                  {legSteps.map((s, i) => (
                    <li key={i} className="flex items-baseline justify-between gap-4 py-2 text-sm">
                      <span className="flex gap-3">
                        <span className="w-6 shrink-0 text-right text-slate-400">{i + 1}.</span>
                        <span className="text-slate-800">{s.instruction}</span>
                      </span>
                      <span className="shrink-0 tabular-nums text-slate-500">
                        {s.miles >= 0.1 ? `${s.miles.toFixed(1)} mi` : `${Math.round(s.miles * 5280)} ft`}
                      </span>
                    </li>
                  ))}
                </ol>
                <p className="mt-2 text-right text-xs text-slate-400">
                  Leg total: {fmtMiles(leg === 0 ? plan.summary.miles_to_pickup : plan.summary.miles_to_dropoff)} mi
                </p>
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}
