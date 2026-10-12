import { fmtDateTime, fmtDuration, fmtMiles } from '../format'
import type { TripPlan } from '../types'

export default function Summary({ plan }: { plan: TripPlan }) {
  const s = plan.summary
  const cards = [
    { label: 'Total distance', value: `${fmtMiles(s.total_miles)} mi`, sub: `${fmtMiles(s.miles_to_pickup)} to pickup · ${fmtMiles(s.miles_to_dropoff)} to drop-off` },
    { label: 'Driving time', value: fmtDuration(s.driving_hours), sub: `${fmtDuration(s.on_duty_hours)} on duty` },
    { label: 'Trip length', value: fmtDuration(s.trip_hours), sub: `${s.days} daily log sheet${s.days === 1 ? '' : 's'}` },
    { label: 'Stops', value: String(s.fuel_stops + s.rests + s.breaks + s.restarts), sub: `${s.fuel_stops} fuel · ${s.rests} rest · ${s.breaks} break${s.restarts ? ` · ${s.restarts} restart` : ''}` },
    { label: 'Arrival', value: fmtDateTime(s.end), sub: `Cycle used: ${Number(s.cycle_used_start.toFixed(1))}h → ${Number(s.cycle_used_end.toFixed(1))}h of 70h` },
  ]

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
      {cards.map((c) => (
        <div key={c.label} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{c.label}</p>
          <p className="mt-1 text-2xl font-bold text-slate-900">{c.value}</p>
          <p className="mt-1 text-xs text-slate-500">{c.sub}</p>
        </div>
      ))}
    </div>
  )
}
