import { useEffect, useId, useRef, useState } from 'react'
import { searchPlaces } from '../api'
import type { ChosenPlace, PlaceSuggestion } from '../types'

interface Props {
  label: string
  value: string
  /** Set once the user picks a suggestion; cleared as soon as they edit the text. */
  place: ChosenPlace | null
  onChange: (text: string, place: ChosenPlace | null) => void
  placeholder?: string
  disabled?: boolean
}

type Status = 'idle' | 'loading' | 'done'

const MIN_CHARS = 2
const DEBOUNCE_MS = 250

const inputClass =
  'mt-1 w-full rounded-lg border bg-white py-2.5 pl-3 pr-9 text-slate-900 shadow-sm outline-none transition placeholder:text-slate-400 focus:ring-2 disabled:bg-slate-100'

export default function PlaceInput({ label, value, place, onChange, placeholder, disabled }: Props) {
  const id = useId()
  const listId = `${id}-list`
  const [focused, setFocused] = useState(false)
  const [results, setResults] = useState<PlaceSuggestion[]>([])
  const [status, setStatus] = useState<Status>('idle')
  const [active, setActive] = useState(-1)
  const blurTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  // Closing on blur is delayed a moment so a click on an option can still land
  useEffect(() => () => clearTimeout(blurTimer.current), [])

  const query = value.trim()
  const searching = focused && !place && !disabled && query.length >= MIN_CHARS

  useEffect(() => {
    if (!searching) return
    const controller = new AbortController()
    const timer = setTimeout(async () => {
      setStatus('loading')
      try {
        const found = await searchPlaces(query, controller.signal)
        if (controller.signal.aborted) return
        setResults(found)
        setActive(-1)
        setStatus('done')
      } catch {
        // aborted by a newer keystroke, or the network failed: just show nothing
        if (!controller.signal.aborted) {
          setResults([])
          setStatus('done')
        }
      }
    }, DEBOUNCE_MS)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [query, searching])

  const open = searching && status !== 'idle'
  const showResults = open && results.length > 0

  const choose = (s: PlaceSuggestion) => {
    onChange(s.label, { label: s.label, lat: s.lat, lon: s.lon })
    setResults([])
    setStatus('idle')
    setActive(-1)
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') {
      setStatus('idle')
      return
    }
    if (!showResults) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((i) => (i + 1) % results.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((i) => (i <= 0 ? results.length - 1 : i - 1))
    } else if (e.key === 'Enter' && active >= 0) {
      e.preventDefault() // pick the suggestion instead of submitting the form
      choose(results[active])
    }
  }

  return (
    <div className="relative">
      <label htmlFor={id} className="block text-sm font-medium text-slate-700">
        {label}
      </label>
      <div className="relative">
        <input
          id={id}
          className={`${inputClass} ${
            place
              ? 'border-emerald-400 focus:border-emerald-500 focus:ring-emerald-100'
              : 'border-slate-300 focus:border-sky-500 focus:ring-sky-200'
          }`}
          value={value}
          placeholder={placeholder}
          disabled={disabled}
          autoComplete="off"
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={active >= 0 ? `${id}-opt-${active}` : undefined}
          onChange={(e) => {
            setStatus('idle')
            onChange(e.target.value, null)
          }}
          onFocus={() => {
            clearTimeout(blurTimer.current)
            setFocused(true)
          }}
          onBlur={() => {
            blurTimer.current = setTimeout(() => setFocused(false), 150)
          }}
          onKeyDown={onKeyDown}
        />
        {place && (
          <span
            className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-emerald-600"
            title="Exact place selected"
            aria-label="Exact place selected"
          >
            ✓
          </span>
        )}
        {open && status === 'loading' && !place && (
          <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2" aria-hidden>
            <svg className="h-4 w-4 animate-spin text-slate-400" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" opacity="0.25" />
              <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
            </svg>
          </span>
        )}
      </div>

      {open && (
        <ul
          id={listId}
          role="listbox"
          aria-label={`${label} suggestions`}
          className="absolute z-30 mt-1 max-h-72 w-full overflow-auto rounded-xl border border-slate-200 bg-white py-1 shadow-xl"
        >
          {showResults ? (
            results.map((s, i) => (
              <li
                key={`${s.lat},${s.lon},${s.title}`}
                id={`${id}-opt-${i}`}
                role="option"
                aria-selected={i === active}
                // keep focus in the input while pressing; the pick happens on click
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => choose(s)}
                onMouseEnter={() => setActive(i)}
                className={`cursor-pointer px-3 py-2 ${i === active ? 'bg-sky-50' : ''}`}
              >
                <p className="truncate text-sm font-medium text-slate-900">{s.title}</p>
                {s.subtitle && <p className="truncate text-xs text-slate-500">{s.subtitle}</p>}
              </li>
            ))
          ) : (
            <li className="px-3 py-2 text-sm text-slate-500" role="option" aria-selected={false}>
              {status === 'loading'
                ? 'Searching…'
                : 'No matches. Try adding the country, e.g. “Sydney, Australia”.'}
            </li>
          )}
        </ul>
      )}
    </div>
  )
}
