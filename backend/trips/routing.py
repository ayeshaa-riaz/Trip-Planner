"""
Free map services used by the planner (no API keys required):

* Nominatim (OpenStreetMap) - geocoding of the typed locations
* OSRM public demo server  - driving route, geometry and turn-by-turn steps
* BigDataCloud / Nominatim - reverse geocoding ("City, ST") for log remarks
"""

from __future__ import annotations

import bisect
import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

import requests

USER_AGENT = 'eld-trip-planner/1.0 (full-stack assessment demo)'
METERS_PER_MILE = 1609.344
TIMEOUT = 25

NOMINATIM = 'https://nominatim.openstreetmap.org'
OSRM = 'https://router.project-osrm.org/route/v1/driving'
BIGDATACLOUD = 'https://api.bigdatacloud.net/data/reverse-geocode-client'
PHOTON = 'https://photon.komoot.io/api/'


class RoutingError(Exception):
    """A map service failed. ``status`` is the HTTP status to report."""

    status = 502


class LocationNotFound(RoutingError):
    status = 400


# ------------------------------------------------------------------ geocoding
_nominatim_lock = threading.Lock()
_last_nominatim_call = 0.0


RETRY_STATUSES = {429, 500, 502, 503, 504}


def _nominatim_get(path: str, params: dict, attempts: int = 3):
    """GET from Nominatim, honouring its 1 request/second usage policy.

    The public server sometimes answers 429/503 under load, so transient
    failures are retried with a short back-off.
    """
    global _last_nominatim_call
    last_exc: Exception | None = None
    for attempt in range(attempts):
        if attempt:
            time.sleep(1.5 * attempt)
        with _nominatim_lock:
            wait = 1.05 - (time.monotonic() - _last_nominatim_call)
            if wait > 0:
                time.sleep(wait)
            try:
                resp = requests.get(
                    f'{NOMINATIM}/{path}',
                    params={**params, 'format': 'jsonv2', 'addressdetails': 1},
                    headers={'User-Agent': USER_AGENT},
                    timeout=TIMEOUT,
                )
            except requests.RequestException as exc:
                last_exc = exc
                continue
            finally:
                _last_nominatim_call = time.monotonic()
        if resp.status_code in RETRY_STATUSES:
            last_exc = requests.HTTPError(f'{resp.status_code} from Nominatim', response=resp)
            continue
        resp.raise_for_status()
        return resp.json()
    raise last_exc or requests.RequestException('Nominatim unavailable')


US_STATES = {
    'Alabama': 'AL', 'Alaska': 'AK', 'Arizona': 'AZ', 'Arkansas': 'AR', 'California': 'CA',
    'Colorado': 'CO', 'Connecticut': 'CT', 'Delaware': 'DE', 'District of Columbia': 'DC',
    'Florida': 'FL', 'Georgia': 'GA', 'Hawaii': 'HI', 'Idaho': 'ID', 'Illinois': 'IL',
    'Indiana': 'IN', 'Iowa': 'IA', 'Kansas': 'KS', 'Kentucky': 'KY', 'Louisiana': 'LA',
    'Maine': 'ME', 'Maryland': 'MD', 'Massachusetts': 'MA', 'Michigan': 'MI', 'Minnesota': 'MN',
    'Mississippi': 'MS', 'Missouri': 'MO', 'Montana': 'MT', 'Nebraska': 'NE', 'Nevada': 'NV',
    'New Hampshire': 'NH', 'New Jersey': 'NJ', 'New Mexico': 'NM', 'New York': 'NY',
    'North Carolina': 'NC', 'North Dakota': 'ND', 'Ohio': 'OH', 'Oklahoma': 'OK', 'Oregon': 'OR',
    'Pennsylvania': 'PA', 'Rhode Island': 'RI', 'South Carolina': 'SC', 'South Dakota': 'SD',
    'Tennessee': 'TN', 'Texas': 'TX', 'Utah': 'UT', 'Vermont': 'VT', 'Virginia': 'VA',
    'Washington': 'WA', 'West Virginia': 'WV', 'Wisconsin': 'WI', 'Wyoming': 'WY',
}


def _geocode_photon(query: str):
    """Fallback geocoder (Komoot Photon, OSM data, no key) used if Nominatim is down."""
    resp = requests.get(
        PHOTON,
        params={'q': query, 'limit': 1, 'lang': 'en'},
        headers={'User-Agent': USER_AGENT},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    features = resp.json().get('features') or []
    if not features:
        return None
    feat = features[0]
    lon, lat = feat['geometry']['coordinates']
    props = feat.get('properties', {})
    place = props.get('city') or props.get('name') or query.split(',')[0]
    state = US_STATES.get(props.get('state', ''), props.get('state', ''))
    parts = [p for p in (place, state) if p]
    if props.get('country') and props.get('countrycode', '').upper() != 'US':
        parts.append(props['country'])
    return {'label': ', '.join(parts), 'lat': lat, 'lon': lon}


def _state_code(address: dict) -> str:
    iso = address.get('ISO3166-2-lvl4') or address.get('ISO3166-2-lvl6') or ''
    if '-' in iso:
        return iso.split('-', 1)[1]
    return address.get('state') or address.get('country_code', '').upper()


_ADMIN_PREFIX = re.compile(
    r'^(?:unorganized territory|township|town|city|village|borough|municipality|'
    r'charter township|civil township)\s+of\s+',
    re.IGNORECASE,
)


def _clean_place(name: str) -> str:
    """"Township of Eureka" -> "Eureka" (admin prefixes read badly on a log)."""
    return _ADMIN_PREFIX.sub('', name.strip()) or name.strip()


def _short_label(address: dict, fallback: str) -> str:
    place = _clean_place(
        address.get('city') or address.get('town') or address.get('village')
        or address.get('hamlet') or address.get('municipality')
        or address.get('county') or ''
    )
    state = _state_code(address)
    parts = [p for p in (place, state) if p]
    # Name the country outside the US so "Sydney, NSW, Australia" is unambiguous
    country = address.get('country', '')
    if parts and country and address.get('country_code', '').lower() != 'us':
        parts.append(country)
    return ', '.join(parts) or fallback.split(',')[0]


def _dedupe(parts):
    """Drop empty and repeated (case-insensitive) strings, keep order."""
    seen, out = set(), []
    for part in parts:
        text = (part or '').strip()
        if text and text.lower() not in seen:
            seen.add(text.lower())
            out.append(text)
    return out


# Cities first, then neighbourhoods, then streets, then individual buildings
_TYPE_RANK = {'city': 0, 'locality': 1, 'district': 1, 'street': 2, 'house': 3}


def _suggestion(props: dict, coords) -> dict | None:
    """Turn a Photon feature into a dropdown suggestion.

    ``title`` / ``subtitle`` are shown in the dropdown; ``label`` is the short
    name used on the map and log sheets ("Chicago, IL" / "Sydney, Australia").
    """
    lon, lat = coords
    name = props.get('name') or ''
    street = ' '.join(p for p in (props.get('housenumber'), props.get('street')) if p)
    title = name or street or props.get('city') or ''
    if not title:
        return None

    is_us = props.get('countrycode', '').upper() == 'US'
    state_full = props.get('state', '')
    detail = _dedupe([
        street if name else '',          # street address of a named building
        props.get('city', ''),
        props.get('county', '') if not state_full else '',
        state_full,
        props.get('country', ''),
    ])
    subtitle = ', '.join(d for d in detail if d.lower() != title.lower())

    tail = US_STATES.get(state_full, state_full) if is_us else props.get('country', '')
    city = props.get('city', '')
    is_area = props.get('type') in ('city', 'locality', 'district')
    if is_area:
        base = [title]                      # "Chicago"
    elif name:
        base = [city or title]              # airports, museums... -> their city
    else:
        base = [title, city]                # street address: "123 Main Street, Dallas"
    return {
        'label': ', '.join(_dedupe([*base, tail])),
        'title': title,
        'subtitle': subtitle,
        'lat': lat,
        'lon': lon,
        'rank': _TYPE_RANK.get(props.get('type'), 3),
    }


_suggest_cache: dict[str, tuple] = {}


def suggest_places(query: str) -> tuple:
    """Up to 5 place suggestions for the autocomplete dropdown.

    Never raises: if the service is unavailable the dropdown is simply empty
    (and the failure is not cached, so the next keystroke retries).
    """
    query = query.strip()
    if len(query) < 2:
        return ()
    key = query.lower()
    if key in _suggest_cache:
        return _suggest_cache[key]
    try:
        resp = requests.get(
            PHOTON,
            params=[
                ('q', query), ('limit', 10), ('lang', 'en'),
                ('layer', 'city'), ('layer', 'locality'), ('layer', 'district'),
                ('layer', 'street'), ('layer', 'house'),
            ],
            headers={'User-Agent': USER_AGENT},
            timeout=8,
        )
        resp.raise_for_status()
        features = resp.json().get('features') or []
    except (requests.RequestException, ValueError):
        return ()

    items = [
        item for feat in features
        if (item := _suggestion(feat.get('properties', {}), feat['geometry']['coordinates']))
    ]
    items.sort(key=lambda i: i['rank'])   # stable: keeps Photon's relevance order within a rank

    results, seen = [], set()
    for item in items:
        dedupe_key = (item['title'].lower(), item['subtitle'].lower())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        item.pop('rank')
        results.append(item)
        if len(results) == 5:
            break

    if len(_suggest_cache) > 1000:
        _suggest_cache.clear()
    _suggest_cache[key] = tuple(results)
    return _suggest_cache[key]


_LATLON = re.compile(r'^\s*(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*$')


@lru_cache(maxsize=256)
def geocode(query: str) -> dict:
    """Return ``{label, lat, lon}`` for a free-text place (or "lat, lon")."""
    query = query.strip()
    m = _LATLON.match(query)
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        if abs(lat) <= 90 and abs(lon) <= 180:
            return {'label': f'{lat:.4f}, {lon:.4f}', 'lat': lat, 'lon': lon}

    try:
        # No country filter: users can disambiguate with "Sydney, Australia".
        results = _nominatim_get('search', {'q': query, 'limit': 1})
    except requests.RequestException:
        # Nominatim is down or throttling us - try the fallback geocoder.
        try:
            hit = _geocode_photon(query)
        except (requests.RequestException, ValueError, KeyError) as exc:
            raise RoutingError(
                'The location search service is temporarily unavailable. '
                'Please try again in a moment.'
            ) from exc
        if not hit:
            raise LocationNotFound(f'Could not find a location matching "{query}".')
        return hit

    if not results:
        raise LocationNotFound(f'Could not find a location matching "{query}".')
    hit = results[0]
    return {
        'label': _short_label(hit.get('address', {}), hit.get('display_name', query)),
        'lat': float(hit['lat']),
        'lon': float(hit['lon']),
    }


def _reverse_bigdatacloud(lat: float, lon: float):
    resp = requests.get(
        BIGDATACLOUD,
        params={'latitude': lat, 'longitude': lon, 'localityLanguage': 'en'},
        headers={'User-Agent': USER_AGENT},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    place = _clean_place(data.get('city') or data.get('locality') or '')
    code = data.get('principalSubdivisionCode', '')
    state = code.split('-', 1)[1] if '-' in code else data.get('principalSubdivision', '')
    parts = [p for p in (place, state) if p]
    if parts and data.get('countryCode', 'US') != 'US' and data.get('countryName'):
        parts.append(data['countryName'])
    return ', '.join(parts) or None


def _reverse_nominatim(lat: float, lon: float):
    data = _nominatim_get('reverse', {'lat': lat, 'lon': lon, 'zoom': 10})
    address = data.get('address')
    return _short_label(address, '') if address else None


@lru_cache(maxsize=2048)
def _reverse_cached(lat: float, lon: float) -> str:
    for fn in (_reverse_bigdatacloud, _reverse_nominatim):
        try:
            label = fn(lat, lon)
            if label:
                return label
        except (requests.RequestException, ValueError, KeyError):
            continue
    return f'{lat:.2f}, {lon:.2f}'


def reverse_geocode_many(points: list[tuple[float, float]]) -> list[str]:
    """Reverse geocode ``(lat, lon)`` pairs concurrently. Order is preserved."""
    rounded = [(round(lat, 2), round(lon, 2)) for lat, lon in points]
    unique = list(dict.fromkeys(rounded))
    with ThreadPoolExecutor(max_workers=6) as pool:
        labels = dict(zip(unique, pool.map(lambda p: _reverse_cached(*p), unique)))
    return [labels[p] for p in rounded]


# -------------------------------------------------------------------- routing
_COMPASS = ['north', 'northeast', 'east', 'southeast', 'south', 'southwest', 'west', 'northwest']


def _compass(bearing: float) -> str:
    return _COMPASS[int(((bearing % 360) + 22.5) // 45) % 8]


def _road(step: dict) -> str:
    name, ref = step.get('name') or '', step.get('ref') or ''
    if name and ref and ref not in name:
        return f'{name} ({ref})'
    return name or ref


def describe_step(step: dict) -> str:
    man = step['maneuver']
    kind, mod = man['type'], man.get('modifier', '')
    road = _road(step)
    onto = f' onto {road}' if road else ''
    on = f' on {road}' if road else ''

    if kind == 'depart':
        return f'Head {_compass(man.get("bearing_after", 0))}{on}'
    if kind == 'arrive':
        return 'Arrive at destination'
    if kind in ('turn', 'end of road'):
        if mod == 'straight':
            text = f'Continue straight{onto}'
        elif mod == 'uturn':
            text = f'Make a U-turn{onto}'
        else:
            text = f'Turn {mod}{onto}'.replace('Turn  ', 'Turn ')
        if kind == 'end of road':
            return f'At the end of the road, {text[0].lower()}{text[1:]}'
        return text
    if kind == 'merge':
        return f'Merge{" " + mod if mod else ""}{onto}'
    if kind == 'on ramp':
        return f'Take the ramp{onto}'
    if kind == 'off ramp':
        return f'Take the exit{onto}'
    if kind == 'fork':
        side = mod if mod in ('left', 'right') else 'straight'
        return f'Keep {side} at the fork{onto}'
    if kind in ('roundabout', 'rotary', 'roundabout turn'):
        n = man.get('exit')
        return f'Enter the roundabout and take exit {n}{onto}' if n else f'Enter the roundabout{onto}'
    if kind in ('exit roundabout', 'exit rotary'):
        return f'Exit the roundabout{onto}'
    return f'Continue{onto or on}'


def _haversine_miles(a, b) -> float:
    (lat1, lon1), (lat2, lon2) = a, b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dlmb = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * 3958.7613 * math.asin(math.sqrt(h))


class Route:
    """A driving route through current -> pickup -> drop-off."""

    def __init__(self, coords, leg_miles, steps):
        self.coords = coords            # [(lat, lon), ...] full resolution
        self.leg_miles = leg_miles      # [current->pickup, pickup->dropoff]
        self.total_miles = sum(leg_miles)
        self.steps = steps

        # Cumulative miles along the geometry, scaled to OSRM's reported total
        cum = [0.0]
        for a, b in zip(coords, coords[1:]):
            cum.append(cum[-1] + _haversine_miles(a, b))
        scale = self.total_miles / cum[-1] if cum[-1] else 1.0
        self._cum = [c * scale for c in cum]

    def point_at(self, mile: float) -> tuple[float, float]:
        """Interpolated ``(lat, lon)`` at ``mile`` miles along the route."""
        mile = max(0.0, min(mile, self.total_miles))
        i = bisect.bisect_right(self._cum, mile)
        if i >= len(self.coords):
            return self.coords[-1]
        if i == 0:
            return self.coords[0]
        lo, hi = self._cum[i - 1], self._cum[i]
        f = (mile - lo) / (hi - lo) if hi > lo else 0.0
        (la1, lo1), (la2, lo2) = self.coords[i - 1], self.coords[i]
        return la1 + (la2 - la1) * f, lo1 + (lo2 - lo1) * f

    def simplified(self, max_points: int = 1500) -> list[list[float]]:
        """Decimated geometry for the browser (keeps first and last points)."""
        n = len(self.coords)
        if n <= max_points:
            return [[round(a, 5), round(b, 5)] for a, b in self.coords]
        stride = n / max_points
        idx = sorted({int(i * stride) for i in range(max_points)} | {n - 1})
        return [[round(self.coords[i][0], 5), round(self.coords[i][1], 5)] for i in idx]


def get_route(points: list[tuple[float, float]]) -> Route:
    """Route through ``points`` (lat, lon) in order using the OSRM demo server."""
    path = ';'.join(f'{lon},{lat}' for lat, lon in points)
    resp, data, last_exc = None, {}, None
    for attempt in range(3):
        if attempt:
            time.sleep(1.5 * attempt)
        try:
            resp = requests.get(
                f'{OSRM}/{path}',
                params={'overview': 'full', 'geometries': 'geojson', 'steps': 'true'},
                headers={'User-Agent': USER_AGENT},
                timeout=60,
            )
            if resp.status_code in RETRY_STATUSES:
                last_exc = RoutingError(f'Routing server returned {resp.status_code}')
                continue
            data = resp.json()
            last_exc = None
            break
        except (requests.RequestException, ValueError) as exc:
            last_exc = exc
    if last_exc is not None or resp is None:
        raise RoutingError(
            'The routing service is temporarily unavailable. Please try again in a moment.'
        ) from last_exc

    if data.get('code') == 'NoRoute':
        raise LocationNotFound('No drivable route exists between those locations.')
    if resp.status_code != 200 or data.get('code') != 'Ok' or not data.get('routes'):
        raise RoutingError(f'Routing failed: {data.get("message") or data.get("code") or resp.status_code}')

    route = data['routes'][0]
    coords = [(lat, lon) for lon, lat in route['geometry']['coordinates']]
    leg_miles = [leg['distance'] / METERS_PER_MILE for leg in route['legs']]

    steps, mile = [], 0.0
    for leg_idx, leg in enumerate(route['legs']):
        for step in leg['steps']:
            miles = step['distance'] / METERS_PER_MILE
            kind = step['maneuver']['type']
            if miles < 0.005 and kind not in ('depart', 'arrive'):
                continue
            text = describe_step(step)
            if kind == 'arrive':
                text = 'Arrive at pickup' if leg_idx == 0 else 'Arrive at drop-off'
            steps.append({
                'leg': leg_idx,
                'instruction': text,
                'road': _road(step),
                'miles': round(miles, 2),
                'mile': round(mile, 2),
            })
            mile += miles
    return Route(coords, leg_miles, steps)
