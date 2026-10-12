# Trip Planner & ELD Daily Logs

A Django + React app for property-carrying truck drivers. You give it a trip, and it plans the
route against the FMCSA hours-of-service rules and draws the Driver's Daily Log sheets you would
otherwise fill in by hand.

Live demo: _add your Vercel URL_
Walkthrough: _add your Loom link_

## What it does

Inputs, and only these four are required:

- Current location
- Pickup location
- Dropoff location
- Current cycle used (hours, 0-70)

Outputs:

- A map of the route, with a marker for every pickup, drop-off, fuel stop, 30-minute break,
  10-hour rest and 34-hour restart. Each marker gives its time, duration and route mile.
- Turn-by-turn route instructions, split into the two legs (current to pickup, pickup to
  drop-off).
- Driver's Daily Log sheets, one per calendar day, drawn on the FMCSA 24-hour graph grid with
  remarks, row totals and the 70-hour/8-day recap. A long trip produces several sheets, and each
  one downloads as a PNG.
- A summary strip with distance, driving time, trip length, stop counts and arrival time.

Nothing past those four inputs is required. The "Log sheet details" fieldset (driver, carrier,
office, tractor and trailer, shipper, commodity, load ID, trip start) only fills in the log
header, so you can leave it blank and the sheets still render with those fields empty. The
"Try an example" link fills in a Houston, TX to Dallas, TX to Seattle, WA haul with 15 cycle
hours used, which is long enough to show four sheets, two fuel stops, three rests and a
30-minute break.

The three location fields autocomplete from two characters. Each suggestion shows its full
description, so Sydney in New South Wales and Sydney in Nova Scotia are easy to tell apart, and
picking one sends its exact coordinates instead of geocoding the text again. Text you type but
never pick from the list is geocoded as it stands, and any country works.

## Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.12+, Django 6, Django REST Framework, django-cors-headers |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS 4, Leaflet |
| Maps (all free, no API keys) | OpenStreetMap tiles, OSRM (routing), Photon (autocomplete), Nominatim (geocoding), BigDataCloud + Nominatim (reverse geocoding) |

The planner is stateless. There are no models and no trip data is kept; the SQLite file holds
only Django's own built-in tables, which is why `migrate` is in the setup steps below.

## Run locally

```bash
# Backend  (http://localhost:8000)
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver

# Frontend (http://localhost:5173)
cd frontend
npm install
npm run dev
```

The frontend talks to `http://localhost:8000/api` by default. Override it with `VITE_API_URL`
(see `frontend/.env.example`).

## Project layout

```
backend/
  config/            Django project: settings, urls, wsgi
  trips/
    hos.py           the HOS scheduler. Pure Python, no Django, no network
    routing.py       geocoding, autocomplete, OSRM routing, reverse geocoding
    services.py      orchestration: geocode -> route -> schedule -> day logs
    views.py         request validation and the three endpoints
    tests.py         66 tests
frontend/src/
  components/
    TripForm.tsx     the four inputs plus the optional log-header fields
    PlaceInput.tsx   autocomplete combobox, keyboard navigable
    RouteMap.tsx     Leaflet map with the route and stop markers
    StopsTimeline.tsx, Directions.tsx, Summary.tsx
    LogSheet.tsx     the daily log sheet, drawn as SVG
  api.ts, format.ts, types.ts
```

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/health/` | `{"status": "ok"}` |
| `GET /api/places/?q=hous` | Up to 5 autocomplete suggestions as `{label, title, subtitle, lat, lon}`. It never errors; if the service is unavailable you get an empty list. |
| `POST /api/plan/` | Plans the trip. |

A plan request needs only the four inputs:

```json
{
  "current_location": "Houston, TX",
  "pickup_location": "Dallas, TX",
  "dropoff_location": "Seattle, WA",
  "cycle_used_hours": 15
}
```

Everything else is optional: `current_place`, `pickup_place` and `dropoff_place` (each
`{label, lat, lon}` straight from the autocomplete, which skips geocoding), `start_time`, and the
log-header fields `driver_name`, `co_driver`, `carrier_name`, `main_office`, `home_terminal`,
`truck_number`, `trailer_number`, `shipper`, `commodity`, `shipping_doc`.

The response has five keys. `summary` holds distances, hours, stop counts, start and end times
and the cycle used. `locations` is the three resolved places. `route` has `coordinates` for the
map and `steps` for the directions. `stops` lists every stop with its time, duration and mile.
`logs` has one object per calendar day, with that day's segments, remarks, totals, miles and
recap.

A location that cannot be found comes back as a 400 with a readable message, and a map service
that is down as a 502. Validation errors name the field that failed.

## How the log sheets are filled out

Each sheet follows the paper log in the FMCSA guide, pages 15 to 19.

- Header: date, From and To, total miles driving today, carrier, main office, home terminal
  (which defaults to the main office), tractor and trailer numbers, and shipping documents
  written as *manifest no. / shipper - commodity*. Co-driver prints "N/A" when it is blank.
- Graph: one continuous line through Off Duty, Sleeper Berth, Driving and On Duty (not driving),
  with quarter-hour tick marks. On-duty time spent standing still, such as a pickup, drop-off or
  fuel stop, gets a bracket under the line, since the truck did not move.
- Remarks: a 45-degree flag at every change of duty status, giving the city and state and what
  the driver was doing. A day spent entirely inside one status, like the middle day of a 34-hour
  restart, has no status change at all, so it gets a single "continued" remark rather than a
  blank box.
- Totals: each row in hours and minutes, adding up to exactly 24:00. It is the boundaries that
  are rounded rather than the durations, so the four rows always reconcile.
- Recap: driving plus on-duty hours as a circled decimal, then A, B and C for the 70-hour/8-day
  rule.
- Signature: the driver's name over the "I certify that these entries are true and correct" line.

Underneath the sheet is a plain table of every duty-status change with its time, place and
activity.

## Hours-of-Service rules implemented

These come from the FMCSA *Interstate Truck Driver's Guide to Hours of Service*, for a
property-carrying driver on 70 hr / 8 day. The scheduler is
[`backend/trips/hos.py`](backend/trips/hos.py). It is pure Python, so it can be unit tested
without touching the network.

| Rule | How it is applied |
|---|---|
| 11-hour driving limit | No more than 11 h driving after 10 consecutive hours off duty. |
| 14-hour window | Driving stops 14 h after coming on duty, and off-duty time does not pause the window. On-duty work past the 14th hour is still allowed, as the guide points out. |
| 30-minute break | Required after 8 cumulative driving hours without an interruption of at least 30 minutes. On-duty-not-driving time, such as fueling or a pickup, counts as that interruption. |
| 10-hour rest | Logged as sleeper berth, and resets the 11 h and 14 h clocks. |
| 70 hr / 8 day | "Current cycle used" counts toward the 70 h. Once it is reached, a 34-hour restart is scheduled as off duty. |

The brief's assumptions are built in: no adverse driving conditions, fuel at least every 1,000
miles (30 minutes, on duty), and 1 hour each for pickup and drop-off, both on duty and not
driving.

### Choices the brief left open

- Average truck speed is 55 mph. OSRM's car-profile durations are too optimistic for a loaded
  truck, so distance comes from OSRM and time is worked out from this speed.
- The trip starts at 8:00 AM today unless a start time is given. Time before the start and after
  arrival is logged as off duty, so every sheet totals exactly 24 hours.
- Hours already used in the cycle are carried until a 34-hour restart rather than aging out day
  by day. That is the conservative reading of the 8-day rolling window.
- Breaks are logged as off duty and the 10-hour rest as sleeper berth. The split-sleeper
  provision is not used.
- Each sheet's "Total Mileage Today" repeats the miles driven that day.
- All times use the home terminal's clock, as the guide requires.

## Tests

```bash
cd backend && python manage.py test trips
```

There are 66 of them. They cover each HOS rule on its own, then re-check whole schedules against
a second, independent implementation of the rules, including a batch of randomly generated
trips. They also assert that every sheet totals 24 hours and that its segments are contiguous,
check the recap arithmetic, and exercise the API: validation, the geocoder fallback, error
statuses, autocomplete and the log header.

## Deploying

Frontend on Vercel: root `frontend`, build `npm run build`, output `dist`, and set
`VITE_API_URL=https://<backend-host>/api`.

Backend on Render, Railway or Fly: root `backend`, build
`pip install -r requirements.txt && python manage.py migrate`, start `gunicorn config.wsgi`.
Set `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=false`, `DJANGO_ALLOWED_HOSTS=<backend-host>` and
`CORS_ALLOWED_ORIGINS=https://<your-vercel-app>.vercel.app`. `STATIC_ROOT` is configured, so
`collectstatic` will work if your build step runs it.

One thing worth knowing: the free public map services are rate-limited and do fail now and
again. The backend respects Nominatim's one-request-per-second policy, retries with a back-off,
falls back to a second geocoder, and shows a clear message if everything is down.
