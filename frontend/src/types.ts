export type DutyStatus = 'off_duty' | 'sleeper' | 'driving' | 'on_duty'

export type StopKind =
  | 'pickup'
  | 'dropoff'
  | 'fuel'
  | 'break'
  | 'rest'
  | 'restart'

/** A place suggestion returned by the autocomplete endpoint. */
export interface PlaceSuggestion {
  label: string
  title: string
  subtitle: string
  lat: number
  lon: number
}

/** A place the user explicitly picked from the dropdown. */
export interface ChosenPlace {
  label: string
  lat: number
  lon: number
}

export interface TripRequest {
  current_location: string
  pickup_location: string
  dropoff_location: string
  current_place?: ChosenPlace
  pickup_place?: ChosenPlace
  dropoff_place?: ChosenPlace
  cycle_used_hours: number
  start_time?: string
  driver_name?: string
  co_driver?: string
  carrier_name?: string
  main_office?: string
  home_terminal?: string
  truck_number?: string
  trailer_number?: string
  shipper?: string
  commodity?: string
  shipping_doc?: string
}

export interface Place {
  label: string
  lat: number
  lon: number
}

export interface Summary {
  total_miles: number
  miles_to_pickup: number
  miles_to_dropoff: number
  driving_hours: number
  on_duty_hours: number
  trip_hours: number
  days: number
  fuel_stops: number
  rests: number
  breaks: number
  restarts: number
  start: string
  end: string
  cycle_used_start: number
  cycle_used_end: number
}

export interface RouteStep {
  leg: number
  instruction: string
  road: string
  miles: number
  mile: number
}

export interface Stop {
  kind: StopKind
  label: string
  location: string
  lat: number
  lon: number
  mile: number
  start: string
  end: string
  duration_hours: number
}

export interface LogSegment {
  status: DutyStatus
  start: number
  end: number
  kind: string
  label: string
}

export interface Remark {
  hour: number
  location: string
  text: string
  /** drive | pickup | dropoff | fuel | break | rest | restart | off */
  kind: string
}

export interface DailyLog {
  day: number
  date: string
  from: string
  to: string
  segments: LogSegment[]
  remarks: Remark[]
  totals: Record<DutyStatus, number>
  miles: number
  recap: { on_duty_today: number; a: number; b: number; c: number }
  driver: string
  co_driver: string
  carrier: string
  office: string
  home_terminal: string
  truck: string
  shipping: string
}

export interface TripPlan {
  summary: Summary
  locations: { current: Place; pickup: Place; dropoff: Place }
  route: { coordinates: [number, number][]; steps: RouteStep[] }
  stops: Stop[]
  logs: DailyLog[]
}
