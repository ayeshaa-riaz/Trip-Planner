import type { PlaceSuggestion, TripPlan, TripRequest } from './types'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api'

const FIELD_NAMES: Record<string, string> = {
  current_location: 'Current location',
  pickup_location: 'Pickup location',
  dropoff_location: 'Dropoff location',
  cycle_used_hours: 'Current cycle used',
  start_time: 'Start time',
}

/** Turn a DRF error body into a single readable message. */
function errorMessage(body: unknown, status: number): string {
  if (body && typeof body === 'object') {
    const obj = body as Record<string, unknown>
    if (typeof obj.detail === 'string') return obj.detail
    const parts = Object.entries(obj).map(([field, msgs]) => {
      const text = Array.isArray(msgs) ? msgs.join(' ') : String(msgs)
      return `${FIELD_NAMES[field] ?? field}: ${text}`
    })
    if (parts.length) return parts.join('\n')
  }
  return `Request failed (${status}).`
}

export async function planTrip(
  request: TripRequest,
  signal?: AbortSignal,
): Promise<TripPlan> {
  let res: Response
  try {
    res = await fetch(`${API_URL}/plan/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
      signal,
    })
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err
    throw new Error(
      'Could not reach the server. Make sure the backend is running and try again.',
    )
  }
  const body = await res.json().catch(() => null)
  if (!res.ok) throw new Error(errorMessage(body, res.status))
  return body as TripPlan
}

/** Autocomplete suggestions. Resolves to [] on any failure (typing must never break). */
export async function searchPlaces(
  query: string,
  signal?: AbortSignal,
): Promise<PlaceSuggestion[]> {
  const res = await fetch(`${API_URL}/places/?q=${encodeURIComponent(query)}`, { signal })
  if (!res.ok) return []
  const body = (await res.json().catch(() => null)) as { results?: PlaceSuggestion[] } | null
  return body?.results ?? []
}
