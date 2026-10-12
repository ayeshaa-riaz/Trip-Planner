import type { DutyStatus, StopKind } from './types'

export const STATUS_LABEL: Record<DutyStatus, string> = {
  off_duty: 'Off duty',
  sleeper: 'Sleeper berth',
  driving: 'Driving',
  on_duty: 'On duty (not driving)',
}

export const STATUS_COLOR: Record<DutyStatus, string> = {
  off_duty: '#94a3b8',
  sleeper: '#6366f1',
  driving: '#0ea5e9',
  on_duty: '#f59e0b',
}

export const STOP_META: Record<
  StopKind,
  { label: string; color: string; icon: string }
> = {
  pickup: { label: 'Pickup', color: '#2563eb', icon: 'P' },
  dropoff: { label: 'Drop-off', color: '#dc2626', icon: 'D' },
  fuel: { label: 'Fuel stop', color: '#ea580c', icon: '⛽' },
  break: { label: '30-min break', color: '#ca8a04', icon: '☕' },
  rest: { label: '10-hr rest', color: '#7c3aed', icon: '🌙' },
  restart: { label: '34-hr restart', color: '#0d9488', icon: '↻' },
}

/** 7.5 -> "7:30 AM". 24 is shown as midnight. */
export function fmtHour(hour: number): string {
  const total = Math.round(hour * 60) % (24 * 60)
  const h = Math.floor(total / 60)
  const m = total % 60
  const suffix = h >= 12 ? 'PM' : 'AM'
  const h12 = h % 12 === 0 ? 12 : h % 12
  return `${h12}:${String(m).padStart(2, '0')} ${suffix}`
}

/** Hours as "h:mm" for durations, e.g. 10.5 -> "10h 30m". */
export function fmtDuration(hours: number): string {
  const total = Math.round(hours * 60)
  const h = Math.floor(total / 60)
  const m = total % 60
  if (h === 0) return `${m}m`
  return m === 0 ? `${h}h` : `${h}h ${m}m`
}

/** Hours rounded for log totals: 7.5 -> "7.5", 11 -> "11". */
export function fmtHours(hours: number): string {
  return String(Math.round(hours * 100) / 100)
}

function parseLocal(iso: string): Date {
  const [d, t] = iso.split('T')
  const [y, mo, da] = d.split('-').map(Number)
  const [h, mi] = t.split(':').map(Number)
  return new Date(y, mo - 1, da, h, mi)
}

/** "2026-10-12T07:30:00" -> "Mon, Oct 12 · 7:30 AM" */
export function fmtDateTime(iso: string): string {
  const date = parseLocal(iso)
  const day = date.toLocaleDateString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  })
  return `${day} · ${fmtHour(date.getHours() + date.getMinutes() / 60)}`
}

export function fmtMiles(miles: number): string {
  return Math.round(miles).toLocaleString('en-US')
}

/** "2026-10-12" -> { month: "10", day: "12", year: "2026" } */
export function splitDate(date: string) {
  const [year, month, day] = date.split('-')
  return { year, month, day }
}

export function fmtDayLabel(date: string): string {
  const [y, m, d] = date.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  })
}
