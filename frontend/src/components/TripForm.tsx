import { useState } from 'react'
import type { ChosenPlace, TripRequest } from '../types'
import PlaceInput from './PlaceInput'

interface Props {
  loading: boolean
  onSubmit: (req: TripRequest) => void
}

const EXAMPLE = {
  current: 'Houston, TX',
  pickup: 'Dallas, TX',
  dropoff: 'Seattle, WA',
  cycle: '15',
}

/** The paper log's header fields (see the FMCSA guide's sample log). */
const EMPTY_DETAILS = {
  startTime: '',
  driver: '',
  coDriver: '',
  carrier: '',
  office: '',
  homeTerminal: '',
  tractor: '',
  trailer: '',
  shipper: '',
  commodity: '',
  loadId: '',
}
type Details = typeof EMPTY_DETAILS

// A steel haul out of the Dallas pickup, run by a Houston-based carrier.
// Co-driver and home terminal stay blank on purpose: the sheet then shows
// "N/A" for the co-driver and falls back to the main office address.
const EXAMPLE_DETAILS: Details = {
  ...EMPTY_DETAILS,
  driver: 'Elena Marsh',
  carrier: 'Lone Star Freight Lines',
  office: 'Houston, TX',
  tractor: '4871',
  trailer: '53210',
  shipper: 'Trinity Steel Co.',
  commodity: 'Steel coils',
  loadId: 'BOL-284417',
}

const inputClass =
  'mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-slate-900 shadow-sm outline-none transition placeholder:text-slate-400 focus:border-sky-500 focus:ring-2 focus:ring-sky-200 disabled:bg-slate-100'

function Label({ text, hint, children }: { text: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block text-sm font-medium text-slate-700">
      {text}
      {hint && <span className="ml-1 font-normal text-slate-400">{hint}</span>}
      {children}
    </label>
  )
}

export default function TripForm({ loading, onSubmit }: Props) {
  const [current, setCurrent] = useState('')
  const [pickup, setPickup] = useState('')
  const [dropoff, setDropoff] = useState('')
  // Set when the user picks a suggestion from the dropdown (exact coordinates)
  const [currentPlace, setCurrentPlace] = useState<ChosenPlace | null>(null)
  const [pickupPlace, setPickupPlace] = useState<ChosenPlace | null>(null)
  const [dropoffPlace, setDropoffPlace] = useState<ChosenPlace | null>(null)
  const [cycle, setCycle] = useState('')
  const [details, setDetails] = useState<Details>(EMPTY_DETAILS)
  const [error, setError] = useState('')

  const detail = (key: keyof Details) => ({
    value: details[key],
    onChange: (e: React.ChangeEvent<HTMLInputElement>) =>
      setDetails((d) => ({ ...d, [key]: e.target.value })),
    disabled: loading,
    className: inputClass,
  })

  const fillExample = () => {
    setCurrent(EXAMPLE.current)
    setPickup(EXAMPLE.pickup)
    setDropoff(EXAMPLE.dropoff)
    setCurrentPlace(null)
    setPickupPlace(null)
    setDropoffPlace(null)
    setCycle(EXAMPLE.cycle)
    setDetails(EXAMPLE_DETAILS)
    setError('')
  }

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    const hours = Number(cycle)
    if (!current.trim() || !pickup.trim() || !dropoff.trim()) {
      setError('Please enter the current, pickup and dropoff locations.')
      return
    }
    if (cycle.trim() === '' || Number.isNaN(hours) || hours < 0 || hours > 70) {
      setError('Current cycle used must be a number between 0 and 70 hours.')
      return
    }
    setError('')
    onSubmit({
      current_location: current.trim(),
      pickup_location: pickup.trim(),
      dropoff_location: dropoff.trim(),
      cycle_used_hours: hours,
      ...(currentPlace ? { current_place: currentPlace } : {}),
      ...(pickupPlace ? { pickup_place: pickupPlace } : {}),
      ...(dropoffPlace ? { dropoff_place: dropoffPlace } : {}),
      ...(details.startTime ? { start_time: details.startTime } : {}),
      driver_name: details.driver.trim(),
      co_driver: details.coDriver.trim(),
      carrier_name: details.carrier.trim(),
      main_office: details.office.trim(),
      home_terminal: details.homeTerminal.trim(),
      truck_number: details.tractor.trim(),
      trailer_number: details.trailer.trim(),
      shipper: details.shipper.trim(),
      commodity: details.commodity.trim(),
      shipping_doc: details.loadId.trim(),
    })
  }

  return (
    <form
      onSubmit={submit}
      className="space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-lg"
      noValidate
    >
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-slate-900">Trip details</h2>
        <button
          type="button"
          onClick={fillExample}
          disabled={loading}
          className="text-sm font-medium text-sky-700 hover:underline disabled:opacity-50"
        >
          Try an example
        </button>
      </div>

      <p className="-mt-2 text-sm text-slate-500">Please enter the details.</p>

      <div className="grid gap-4 md:grid-cols-2">
        <PlaceInput
          label="Current location"
          value={current}
          place={currentPlace}
          onChange={(text, place) => {
            setCurrent(text)
            setCurrentPlace(place)
          }}
          placeholder="e.g. Houston, TX"
          disabled={loading}
        />
        <PlaceInput
          label="Pickup location"
          value={pickup}
          place={pickupPlace}
          onChange={(text, place) => {
            setPickup(text)
            setPickupPlace(place)
          }}
          placeholder="e.g. Dallas, TX"
          disabled={loading}
        />
        <PlaceInput
          label="Dropoff location"
          value={dropoff}
          place={dropoffPlace}
          onChange={(text, place) => {
            setDropoff(text)
            setDropoffPlace(place)
          }}
          placeholder="e.g. Seattle, WA"
          disabled={loading}
        />
        <Label text="Current cycle used" hint="(hours, 0–70)">
          <input className={inputClass} type="number" inputMode="decimal" min={0} max={70} step="0.25" value={cycle} onChange={(e) => setCycle(e.target.value)} placeholder="e.g. 15" disabled={loading} />
        </Label>
      </div>

      <fieldset className="space-y-3 rounded-xl bg-slate-50 p-4">
        <legend className="px-1 text-sm font-semibold text-slate-700">
          Log sheet details <span className="font-normal text-slate-400">(printed in the log header)</span>
        </legend>
        <div className="grid gap-4 md:grid-cols-2">
          <Label text="Trip start" hint="(home terminal time; default 8:00 AM today)">
            <input type="datetime-local" {...detail('startTime')} />
          </Label>
          <Label text="Driver name" hint="(signs the log)">
            <input placeholder="e.g. Elena Marsh" {...detail('driver')} />
          </Label>
          <Label text="Co-driver" hint="(blank = N/A)">
            <input placeholder="N/A" {...detail('coDriver')} />
          </Label>
          <Label text="Name of carrier">
            <input placeholder="e.g. Lone Star Freight Lines" {...detail('carrier')} />
          </Label>
          <Label text="Main office address">
            <input placeholder="e.g. Houston, TX" {...detail('office')} />
          </Label>
          <Label text="Home terminal address" hint="(blank = main office)">
            <input placeholder="Same as main office" {...detail('homeTerminal')} />
          </Label>
          <Label text="Tractor number">
            <input placeholder="e.g. 4871" {...detail('tractor')} />
          </Label>
          <Label text="Trailer number">
            <input placeholder="e.g. 53210" {...detail('trailer')} />
          </Label>
          <Label text="Shipper">
            <input placeholder="e.g. Trinity Steel Co." {...detail('shipper')} />
          </Label>
          <Label text="Commodity">
            <input placeholder="e.g. Steel coils" {...detail('commodity')} />
          </Label>
          <div className="md:col-span-2">
            <Label text="Load ID / shipping document number">
              <input placeholder="e.g. BOL-284417" {...detail('loadId')} />
            </Label>
          </div>
        </div>
      </fieldset>

      {error && (
        <p role="alert" className="whitespace-pre-line rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={loading}
        className="flex w-full items-center justify-center gap-2 rounded-xl bg-sky-700 px-5 py-3 font-semibold text-white shadow transition hover:bg-sky-800 disabled:cursor-wait disabled:opacity-80"
      >
        {loading && (
          <svg className="h-5 w-5 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden>
            <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" opacity="0.25" />
            <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
          </svg>
        )}
        {loading ? 'Planning route and logs…' : 'Plan trip'}
      </button>
    </form>
  )
}
