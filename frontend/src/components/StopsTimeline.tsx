import { fmtDateTime, fmtDuration, fmtMiles, STOP_META } from '../format'
import type { TripPlan } from '../types'

export default function StopsTimeline({ plan }: { plan: TripPlan }) {
  const { summary, locations, stops } = plan
  const items = [
    {
      key: 'start',
      color: '#16a34a',
      icon: 'S',
      title: 'Start',
      place: locations.current.label,
      time: fmtDateTime(summary.start),
      detail: 'Begin trip',
    },
    ...stops.map((s, i) => {
      const meta = STOP_META[s.kind]
      return {
        key: `${s.kind}-${i}`,
        color: meta.color,
        icon: meta.icon,
        title: meta.label,
        place: s.location,
        time: fmtDateTime(s.start),
        detail: `${fmtDuration(s.duration_hours)} · mile ${fmtMiles(s.mile)}`,
      }
    }),
  ]

  return (
    <ol className="relative max-h-[480px] space-y-0 overflow-y-auto pr-2">
      {items.map((item, i) => (
        <li key={item.key} className="relative flex gap-3 pb-4">
          {i < items.length - 1 && (
            <span className="absolute left-[15px] top-8 h-[calc(100%-1.5rem)] w-px bg-slate-200" />
          )}
          <span
            className="z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-bold text-white shadow"
            style={{ background: item.color }}
          >
            {item.icon}
          </span>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-slate-900">
              {item.title} <span className="font-normal text-slate-500">· {item.place}</span>
            </p>
            <p className="text-xs text-slate-500">
              {item.time} · {item.detail}
            </p>
          </div>
        </li>
      ))}
    </ol>
  )
}
