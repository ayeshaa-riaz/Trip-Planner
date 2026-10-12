"""Orchestrates geocoding -> routing -> HOS planning -> daily log sheets."""

from __future__ import annotations

from datetime import datetime, timedelta

from . import hos, routing

DEFAULT_START_HOUR = 8


def _iso(day0: datetime, hours: float) -> str:
    return (day0 + timedelta(hours=hours)).strftime('%Y-%m-%dT%H:%M:%S')


def _clean(value) -> str:
    return (value or '').strip()


def log_header(details: dict) -> dict:
    """Header fields of the paper log, following FMCSA/Schneider practice.

    * Co-driver: write "N/A" when there is none.
    * Home terminal defaults to the main office.
    * Tractor and trailer numbers share the "Truck/Tractor and Trailer" box.
    * "Shipping documents": load/manifest number, then shipper and commodity.
    """
    office = _clean(details.get('office'))
    truck = ' / '.join(
        part for part in (
            f"Tractor {_clean(details.get('truck'))}" if _clean(details.get('truck')) else '',
            f"Trailer {_clean(details.get('trailer'))}" if _clean(details.get('trailer')) else '',
        ) if part
    )
    shipper_commodity = ' - '.join(
        p for p in (_clean(details.get('shipper')), _clean(details.get('commodity'))) if p
    )
    shipping = ' / '.join(p for p in (_clean(details.get('shipping')), shipper_commodity) if p)
    return {
        'driver': _clean(details.get('driver')),
        'co_driver': _clean(details.get('co_driver')) or 'N/A',
        'carrier': _clean(details.get('carrier')),
        'office': office,
        'home_terminal': _clean(details.get('home_terminal')) or office,
        'truck': truck,
        'shipping': shipping,
    }


def plan_trip(
    current: str,
    pickup: str,
    dropoff: str,
    cycle_used: float,
    start: datetime | None = None,
    details: dict | None = None,
    chosen: dict | None = None,
) -> dict:
    details = details or {}
    chosen = chosen or {}
    header = log_header(details)

    # 1. Resolve the three locations. A place picked from the autocomplete
    #    dropdown already has exact coordinates, so only typed text is geocoded.
    def resolve(key: str, text: str) -> dict:
        place = chosen.get(key)
        if place:
            return {'label': place['label'], 'lat': place['lat'], 'lon': place['lon']}
        return routing.geocode(text)

    places = {
        'current': resolve('current', current),
        'pickup': resolve('pickup', pickup),
        'dropoff': resolve('dropoff', dropoff),
    }

    # 2. Route current -> pickup -> drop-off
    route = routing.get_route([
        (p['lat'], p['lon']) for p in (places['current'], places['pickup'], places['dropoff'])
    ])

    # 3. Plan the trip against the HOS rules
    if start is None:
        start = datetime.now().replace(hour=DEFAULT_START_HOUR, minute=0, second=0, microsecond=0)
    day0 = start.replace(hour=0, minute=0, second=0, microsecond=0)
    start_hour = start.hour + start.minute / 60

    planner = hos.TripPlanner(route.leg_miles[0], route.leg_miles[1], cycle_used, start_hour)
    segments = planner.plan()
    day_logs = hos.build_day_logs(segments, start_hour)
    recaps = hos.cycle_recaps(day_logs, cycle_used)

    # 4. Resolve place names for every duty-status change (log "Remarks")
    def point_for(seg_mile):
        return route.point_at(seg_mile)

    wanted: list[tuple[float, float]] = []
    for log in day_logs:
        for seg in log.segments:
            wanted.append(point_for(seg.mile))
        last = log.segments[-1]
        wanted.append(point_for(last.mile + last.miles))
    labels = iter(routing.reverse_geocode_many(wanted))

    # The typed origin/pickup/drop-off give nicer names than reverse geocoding
    def named(label, mile):
        for key, m in (
            ('current', 0.0),
            ('pickup', route.leg_miles[0]),
            ('dropoff', route.total_miles),
        ):
            if abs(mile - m) < 0.5:
                return places[key]['label']
        return label

    logs_out = []
    prev_status = prev_kind = None
    for log, recap in zip(day_logs, recaps):
        segs_out, remarks = [], []
        first_place = None
        for seg in log.segments:
            place = named(next(labels), seg.mile)
            if first_place is None:
                first_place = place
            segs_out.append({
                'status': seg.status,
                'start': round(seg.start, 4),
                'end': round(seg.end, 4),
                'kind': seg.kind,
                'label': seg.label,
            })
            if seg.status != prev_status or seg.kind != prev_kind:
                remarks.append({
                    'hour': round(seg.start, 4), 'location': place,
                    'text': seg.label, 'kind': seg.kind,
                })
            prev_status, prev_kind = seg.status, seg.kind
        if not remarks:
            # A day spent entirely inside one segment (e.g. the middle day of a
            # 34-hour restart) has no change of duty status. The guide still
            # wants the combined off-duty day explained in the remarks.
            seg = log.segments[0]
            remarks.append({
                'hour': 0.0, 'location': first_place,
                'text': f'{seg.label} - continued', 'kind': seg.kind,
            })
        end_place = named(next(labels), log.segments[-1].mile + log.segments[-1].miles)
        date = day0 + timedelta(days=log.day)
        logs_out.append({
            'day': log.day + 1,
            'date': date.strftime('%Y-%m-%d'),
            'from': remarks[0]['location'] if remarks else end_place,
            'to': end_place,
            'segments': segs_out,
            'remarks': remarks,
            'totals': log.totals,
            'miles': log.miles,
            'recap': recap,
            **header,
        })

    # 5. Stops for the map / timeline
    stops = []
    stop_kinds = {hos.KIND_PICKUP, hos.KIND_DROPOFF, hos.KIND_FUEL, hos.KIND_BREAK,
                  hos.KIND_REST, hos.KIND_RESTART}
    stop_segments = [s for s in segments if s.kind in stop_kinds]
    stop_points = []
    for s in stop_segments:
        if s.kind == hos.KIND_PICKUP:
            stop_points.append((places['pickup']['lat'], places['pickup']['lon']))
        elif s.kind == hos.KIND_DROPOFF:
            stop_points.append((places['dropoff']['lat'], places['dropoff']['lon']))
        else:
            stop_points.append(route.point_at(s.mile))
    stop_labels = routing.reverse_geocode_many(stop_points)
    for s, (lat, lon), place in zip(stop_segments, stop_points, stop_labels):
        stops.append({
            'kind': s.kind,
            'label': s.label,
            'location': named(place, s.mile),
            'lat': lat,
            'lon': lon,
            'mile': round(s.mile, 1),
            'start': _iso(day0, s.start),
            'end': _iso(day0, s.end),
            'duration_hours': round(s.duration, 2),
        })

    end_time = segments[-1].end
    driving = sum(s.duration for s in segments if s.status == hos.DRIVING)
    on_duty = sum(s.duration for s in segments if s.status == hos.ON_DUTY)
    summary = {
        'total_miles': round(route.total_miles, 1),
        'miles_to_pickup': round(route.leg_miles[0], 1),
        'miles_to_dropoff': round(route.leg_miles[1], 1),
        'driving_hours': round(driving, 2),
        'on_duty_hours': round(driving + on_duty, 2),
        'trip_hours': round(end_time - start_hour, 2),
        'days': len(logs_out),
        'fuel_stops': sum(1 for s in segments if s.kind == hos.KIND_FUEL),
        'rests': sum(1 for s in segments if s.kind == hos.KIND_REST),
        'breaks': sum(1 for s in segments if s.kind == hos.KIND_BREAK),
        'restarts': sum(1 for s in segments if s.kind == hos.KIND_RESTART),
        'start': _iso(day0, start_hour),
        'end': _iso(day0, end_time),
        'cycle_used_start': cycle_used,
        'cycle_used_end': round(planner.cycle, 2),
    }

    return {
        'summary': summary,
        'locations': places,
        'route': {'coordinates': route.simplified(), 'steps': route.steps},
        'stops': stops,
        'logs': logs_out,
    }
