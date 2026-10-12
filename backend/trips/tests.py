from django.test import SimpleTestCase

from . import hos
from .hos import (
    DRIVING, KIND_BREAK, KIND_FUEL, KIND_REST, KIND_RESTART, OFF_DUTY,
    ON_DUTY, SLEEPER, TripPlanner, build_day_logs, cycle_recaps,
)

EPS = 1e-4


def plan(leg1, leg2, cycle=0.0, start=8.0):
    p = TripPlanner(leg1, leg2, cycle, start)
    return p.plan()


def assert_compliant(test, segments, cycle_used=0.0):
    """Independent re-check of the schedule against the FMCSA rules."""
    # Contiguous timeline
    for a, b in zip(segments, segments[1:]):
        test.assertAlmostEqual(a.end, b.start, places=4)

    drive_today = 0.0
    since_break = 0.0
    window_start = None
    cycle = cycle_used
    for s in segments:
        if s.status in (DRIVING, ON_DUTY) and window_start is None:
            window_start = s.start
        if s.status == DRIVING:
            drive_today += s.duration
            since_break += s.duration
            cycle += s.duration
            test.assertLessEqual(drive_today, 11 + EPS, '11-hour driving limit')
            test.assertLessEqual(since_break, 8 + EPS, '30-minute break after 8h')
            test.assertLessEqual(s.end - window_start, 14 + EPS, '14-hour window')
            test.assertLessEqual(cycle, 70 + EPS, '70-hour limit')
        else:
            if s.status == ON_DUTY:
                cycle += s.duration
            if s.duration >= 0.5 - EPS:
                since_break = 0.0
            if s.status in (OFF_DUTY, SLEEPER):
                if s.duration >= 10 - EPS:
                    drive_today = 0.0
                    window_start = None
                if s.duration >= 34 - EPS:
                    cycle = 0.0


class ScheduleRulesTests(SimpleTestCase):
    def test_short_trip_has_no_rests(self):
        segs = plan(50, 100)
        kinds = [s.kind for s in segs]
        self.assertNotIn(KIND_REST, kinds)
        self.assertNotIn(KIND_BREAK, kinds)
        # drive, pickup, drive, dropoff
        self.assertEqual(kinds, ['drive', 'pickup', 'drive', 'dropoff'])
        assert_compliant(self, segs)

    def test_pickup_and_dropoff_take_one_hour(self):
        segs = plan(10, 10)
        by_kind = {s.kind: s for s in segs}
        self.assertAlmostEqual(by_kind['pickup'].duration, 1.0)
        self.assertAlmostEqual(by_kind['dropoff'].duration, 1.0)
        self.assertEqual(by_kind['pickup'].status, ON_DUTY)

    def test_total_miles_driven_matches_route(self):
        segs = plan(300, 1200)
        driven = sum(s.miles for s in segs)
        self.assertAlmostEqual(driven, 1500, places=3)

    def test_break_required_after_8_hours_driving(self):
        # 8h * 55 = 440 miles; 600 miles of driving needs a break
        segs = plan(0, 600)
        breaks = [s for s in segs if s.kind == KIND_BREAK]
        self.assertEqual(len(breaks), 1)
        self.assertAlmostEqual(breaks[0].duration, 0.5)
        assert_compliant(self, segs)

    def test_eleven_hour_limit_forces_ten_hour_rest(self):
        # 11h * 55 = 605 mi. 900 miles needs an overnight rest.
        segs = plan(0, 900)
        rests = [s for s in segs if s.kind == KIND_REST]
        self.assertGreaterEqual(len(rests), 1)
        self.assertAlmostEqual(rests[0].duration, 10.0)
        self.assertEqual(rests[0].status, SLEEPER)
        assert_compliant(self, segs)

    def test_guide_example_14_hour_window(self):
        # Guide: come to work 6:00 a.m. -> must not drive after 8:00 p.m.
        segs = plan(0, 2000, start=6.0)
        assert_compliant(self, segs)
        first_rest = next(s for s in segs if s.kind == KIND_REST)
        self.assertLessEqual(first_rest.start, 6.0 + 14 + EPS)

    def test_fuel_at_least_every_1000_miles(self):
        segs = plan(0, 2600)
        fuel_miles = [s.mile for s in segs if s.kind == KIND_FUEL]
        self.assertEqual(len(fuel_miles), 2)
        self.assertAlmostEqual(fuel_miles[0], 1000, places=2)
        self.assertAlmostEqual(fuel_miles[1], 2000, places=2)
        assert_compliant(self, segs)

    def test_cycle_limit_triggers_34_hour_restart(self):
        # Already used 65h of the 70h cycle: a long trip needs a restart.
        segs = plan(0, 1500, cycle=65.0)
        restarts = [s for s in segs if s.kind == KIND_RESTART]
        self.assertEqual(len(restarts), 1)
        self.assertAlmostEqual(restarts[0].duration, 34.0)
        assert_compliant(self, segs, cycle_used=65.0)

    def test_full_cycle_restarts_before_pickup(self):
        segs = plan(0, 100, cycle=70.0)
        self.assertEqual(segs[0].kind, KIND_RESTART)
        assert_compliant(self, segs, cycle_used=70.0)

    def test_cross_country_trip_is_compliant(self):
        segs = plan(480, 2940, cycle=20.0, start=7.5)
        assert_compliant(self, segs, cycle_used=20.0)

    def test_many_random_trips_are_compliant(self):
        import random
        rng = random.Random(7)
        for _ in range(300):
            l1, l2 = rng.uniform(0, 1500), rng.uniform(0, 3500)
            cycle = rng.uniform(0, 70)
            start = rng.uniform(0, 23)
            segs = plan(l1, l2, cycle, start)
            assert_compliant(self, segs, cycle)
            self.assertAlmostEqual(sum(s.miles for s in segs), l1 + l2, places=3)

    def test_invalid_cycle_rejected(self):
        with self.assertRaises(ValueError):
            TripPlanner(10, 10, 71, 8)
        with self.assertRaises(ValueError):
            TripPlanner(10, 10, -1, 8)


class DayLogTests(SimpleTestCase):
    def test_every_sheet_totals_24_hours(self):
        segs = plan(480, 2940, cycle=20.0, start=7.5)
        logs = build_day_logs(segs, 7.5)
        self.assertGreater(len(logs), 3)
        for log in logs:
            self.assertAlmostEqual(sum(log.totals.values()), 24.0, places=1)

    def test_first_day_is_off_duty_until_start(self):
        segs = plan(50, 50, start=8.0)
        logs = build_day_logs(segs, 8.0)
        first = logs[0].segments[0]
        self.assertEqual(first.status, OFF_DUTY)
        self.assertAlmostEqual(first.start, 0.0)
        self.assertAlmostEqual(first.end, 8.0)

    def test_segments_within_a_day_are_contiguous(self):
        segs = plan(300, 2000, cycle=10, start=6.0)
        for log in build_day_logs(segs, 6.0):
            self.assertAlmostEqual(log.segments[0].start, 0.0, places=4)
            self.assertAlmostEqual(log.segments[-1].end, 24.0, places=4)
            for a, b in zip(log.segments, log.segments[1:]):
                self.assertAlmostEqual(a.end, b.start, places=4)

    def test_daily_miles_add_up(self):
        segs = plan(300, 2000, start=6.0)
        logs = build_day_logs(segs, 6.0)
        self.assertAlmostEqual(sum(l.miles for l in logs), 2300, delta=0.5)

    def test_recap_math(self):
        segs = plan(300, 2000, cycle=10, start=6.0)
        logs = build_day_logs(segs, 6.0)
        recaps = cycle_recaps(logs, 10)
        first = recaps[0]
        self.assertAlmostEqual(first['a'], 10 + logs[0].on_duty_hours, places=1)
        self.assertAlmostEqual(first['b'], 70 - first['a'], places=1)
        for r in recaps:
            self.assertLessEqual(r['c'], 70.5)


# ------------------------------------------------------------------ API tests
from unittest import mock

from rest_framework.test import APIClient

from . import routing


def fake_geocode(query):
    table = {
        'a': {'label': 'Alpha, TX', 'lat': 32.0, 'lon': -97.0},
        'b': {'label': 'Bravo, TX', 'lat': 32.0, 'lon': -95.0},
        'c': {'label': 'Charlie, LA', 'lat': 32.0, 'lon': -90.0},
    }
    if query not in table:
        raise routing.LocationNotFound(f'Could not find a location matching "{query}".')
    return table[query]


def fake_route(points):
    # straight line through the points; legs of 150 and 400 miles
    return routing.Route(points, [150.0, 400.0], [
        {'leg': 0, 'instruction': 'Head east', 'road': 'I-20', 'miles': 150.0, 'mile': 0.0},
        {'leg': 1, 'instruction': 'Arrive at drop-off', 'road': '', 'miles': 0.0, 'mile': 550.0},
    ])


class PlanApiTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()
        self.body = {
            'current_location': 'a', 'pickup_location': 'b',
            'dropoff_location': 'c', 'cycle_used_hours': 10,
            'start_time': '2026-10-12T06:00:00', 'carrier_name': 'Demo Freight',
        }

    def post(self, body=None):
        with mock.patch('trips.routing.geocode', fake_geocode), \
             mock.patch('trips.routing.get_route', fake_route), \
             mock.patch('trips.routing.reverse_geocode_many',
                        lambda pts: [f'Town {i}, TX' for i, _ in enumerate(pts)]):
            return self.client.post('/api/plan/', body or self.body, format='json')

    def test_returns_plan(self):
        resp = self.post()
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(data['summary']['total_miles'], 550.0)
        self.assertEqual(data['summary']['start'], '2026-10-12T06:00:00')
        self.assertEqual({s['kind'] for s in data['stops']} >= {'pickup', 'dropoff'}, True)
        for log in data['logs']:
            self.assertAlmostEqual(sum(log['totals'].values()), 24.0, places=1)
            self.assertEqual(log['carrier'], 'Demo Freight')
        self.assertEqual(data['logs'][0]['date'], '2026-10-12')

    def test_cycle_used_validation(self):
        for bad in (-1, 71, 'abc'):
            resp = self.post({**self.body, 'cycle_used_hours': bad})
            self.assertEqual(resp.status_code, 400)
            self.assertIn('cycle_used_hours', resp.json())

    def test_missing_fields_rejected(self):
        resp = self.post({'cycle_used_hours': 5})
        self.assertEqual(resp.status_code, 400)
        for f in ('current_location', 'pickup_location', 'dropoff_location'):
            self.assertIn(f, resp.json())

    def test_unknown_location_gives_400_with_message(self):
        resp = self.post({**self.body, 'pickup_location': 'nowhere'})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('nowhere', resp.json()['detail'])

    def test_health(self):
        self.assertEqual(self.client.get('/api/health/').json(), {'status': 'ok'})


class GeocodeFallbackTests(SimpleTestCase):
    def setUp(self):
        routing.geocode.cache_clear()

    def tearDown(self):
        routing.geocode.cache_clear()

    def test_falls_back_to_photon_when_nominatim_fails(self):
        import requests
        photon = {'label': 'Los Angeles, CA', 'lat': 34.05, 'lon': -118.24}
        with mock.patch('trips.routing._nominatim_get', side_effect=requests.HTTPError('503')), \
             mock.patch('trips.routing._geocode_photon', return_value=photon):
            self.assertEqual(routing.geocode('Los Angeles, CA'), photon)

    def test_friendly_error_when_both_services_fail(self):
        import requests
        with mock.patch('trips.routing._nominatim_get', side_effect=requests.HTTPError('503')), \
             mock.patch('trips.routing._geocode_photon', side_effect=requests.ConnectionError()):
            with self.assertRaises(routing.RoutingError) as ctx:
                routing.geocode('Somewhere')
        self.assertEqual(ctx.exception.status, 502)
        self.assertIn('temporarily unavailable', str(ctx.exception))

    def test_not_found_is_400_not_502(self):
        with mock.patch('trips.routing._nominatim_get', return_value=[]):
            with self.assertRaises(routing.LocationNotFound) as ctx:
                routing.geocode('zzzzqqqq')
        self.assertEqual(ctx.exception.status, 400)

    def test_lat_lon_input_skips_geocoding(self):
        with mock.patch('trips.routing._nominatim_get') as nominatim:
            hit = routing.geocode('41.8781, -87.6298')
        nominatim.assert_not_called()
        self.assertAlmostEqual(hit['lat'], 41.8781)

    def test_photon_label_uses_state_abbreviation(self):
        payload = {'features': [{
            'geometry': {'coordinates': [-118.24, 34.05]},
            'properties': {'name': 'Los Angeles', 'state': 'California'},
        }]}
        with mock.patch('trips.routing.requests.get') as get:
            get.return_value.json.return_value = payload
            get.return_value.raise_for_status.return_value = None
            hit = routing._geocode_photon('Los Angeles, CA')
        self.assertEqual(hit['label'], 'Los Angeles, CA')


class PlaceNameTests(SimpleTestCase):
    def test_admin_prefixes_are_stripped(self):
        self.assertEqual(routing._clean_place('Township of Eureka'), 'Eureka')
        self.assertEqual(routing._clean_place('Unorganized Territory of West Lyman'), 'West Lyman')
        self.assertEqual(routing._clean_place('City of Industry'), 'Industry')
        self.assertEqual(routing._clean_place('Kansas City'), 'Kansas City')
        self.assertEqual(routing._clean_place('Township'), 'Township')

    def test_short_label_uses_state_code(self):
        addr = {'city': 'Saint Louis', 'ISO3166-2-lvl4': 'US-MO'}
        self.assertEqual(routing._short_label(addr, ''), 'Saint Louis, MO')


class InternationalPlaceTests(SimpleTestCase):
    def setUp(self):
        routing.geocode.cache_clear()

    def test_no_country_filter_is_sent_to_nominatim(self):
        with mock.patch('trips.routing._nominatim_get', return_value=[]) as get:
            with self.assertRaises(routing.LocationNotFound):
                routing.geocode('Sydney, Australia')
        params = get.call_args[0][1]
        self.assertNotIn('countrycodes', params)

    def test_non_us_label_includes_country(self):
        addr = {'city': 'Sydney', 'ISO3166-2-lvl4': 'AU-NSW',
                'country': 'Australia', 'country_code': 'au'}
        self.assertEqual(routing._short_label(addr, ''), 'Sydney, NSW, Australia')

    def test_us_label_has_no_country(self):
        addr = {'city': 'Chicago', 'ISO3166-2-lvl4': 'US-IL',
                'country': 'United States', 'country_code': 'us'}
        self.assertEqual(routing._short_label(addr, ''), 'Chicago, IL')


# ------------------------------------------------------- autocomplete tests
PHOTON_FEATURES = {'features': [
    {'geometry': {'coordinates': [151.2, -33.87]},
     'properties': {'name': 'Sydney', 'state': 'New South Wales', 'country': 'Australia',
                    'countrycode': 'AU', 'type': 'city'}},
    {'geometry': {'coordinates': [-60.19, 46.14]},
     'properties': {'name': 'Sydney', 'county': 'Cape Breton Regional Municipality',
                    'state': 'Nova Scotia', 'country': 'Canada', 'countrycode': 'CA',
                    'type': 'city'}},
    {'geometry': {'coordinates': [151.21, -33.86]},
     'properties': {'name': 'Sydney Opera House', 'housenumber': '2', 'street': 'Macquarie Street',
                    'city': 'Sydney', 'state': 'New South Wales', 'country': 'Australia',
                    'countrycode': 'AU', 'type': 'house'}},
    # duplicate of the first one - must be dropped
    {'geometry': {'coordinates': [151.2, -33.87]},
     'properties': {'name': 'Sydney', 'state': 'New South Wales', 'country': 'Australia',
                    'countrycode': 'AU', 'type': 'city'}},
]}


class SuggestTests(SimpleTestCase):
    def setUp(self):
        routing._suggest_cache.clear()

    def suggest(self, query='sydn', payload=PHOTON_FEATURES):
        with mock.patch('trips.routing.requests.get') as get:
            get.return_value.json.return_value = payload
            get.return_value.raise_for_status.return_value = None
            return routing.suggest_places(query)

    def test_both_sydneys_are_offered_with_countries(self):
        results = self.suggest()
        subtitles = [r['subtitle'] for r in results]
        self.assertIn('New South Wales, Australia', subtitles)
        # county is omitted when a state is known - it only adds noise
        self.assertIn('Nova Scotia, Canada', subtitles)

    def test_duplicates_removed(self):
        self.assertEqual(len(self.suggest()), 3)

    def test_labels_are_short(self):
        labels = {r['label'] for r in self.suggest()}
        self.assertEqual(labels, {'Sydney, Australia', 'Sydney, Canada'})

    def test_named_building_shows_street_address(self):
        opera = next(r for r in self.suggest() if r['title'] == 'Sydney Opera House')
        self.assertEqual(opera['subtitle'], '2 Macquarie Street, Sydney, New South Wales, Australia')
        self.assertEqual(opera['label'], 'Sydney, Australia')

    def test_us_label_uses_state_abbreviation(self):
        payload = {'features': [{
            'geometry': {'coordinates': [-90.2, 38.6]},
            'properties': {'name': 'Saint Louis', 'state': 'Missouri', 'country': 'United States',
                           'countrycode': 'US', 'type': 'city'}}]}
        self.assertEqual(self.suggest('saint', payload)[0]['label'], 'Saint Louis, MO')

    def test_cities_rank_before_buildings(self):
        payload = {'features': [
            {'geometry': {'coordinates': [1, 2]},
             'properties': {'name': 'St. Louis School', 'city': 'Toronto', 'country': 'Canada',
                            'countrycode': 'CA', 'type': 'house'}},
            {'geometry': {'coordinates': [-90.2, 38.6]},
             'properties': {'name': 'Saint Louis', 'state': 'Missouri', 'country': 'United States',
                            'countrycode': 'US', 'type': 'city'}}]}
        results = self.suggest('st lou', payload)
        self.assertEqual(results[0]['label'], 'Saint Louis, MO')
        self.assertNotIn('rank', results[0])

    def test_street_address_label_includes_city(self):
        payload = {'features': [{
            'geometry': {'coordinates': [-84.8, 33.9]},
            'properties': {'housenumber': '123', 'street': 'Main Street', 'city': 'Dallas',
                           'state': 'Georgia', 'country': 'United States',
                           'countrycode': 'US', 'type': 'house'}}]}
        item = self.suggest('123 main', payload)[0]
        self.assertEqual(item['label'], '123 Main Street, Dallas, GA')
        self.assertEqual(item['title'], '123 Main Street')

    def test_short_query_makes_no_request(self):
        with mock.patch('trips.routing.requests.get') as get:
            self.assertEqual(routing.suggest_places('s'), ())
        get.assert_not_called()

    def test_failure_returns_empty_and_is_not_cached(self):
        import requests
        with mock.patch('trips.routing.requests.get', side_effect=requests.ConnectionError()):
            self.assertEqual(routing.suggest_places('sydney'), ())
        self.assertEqual(len(self.suggest('sydney')), 3)  # retried successfully

    def test_endpoint(self):
        with mock.patch('trips.routing.suggest_places',
                        return_value=({'label': 'X', 'title': 'X', 'subtitle': '', 'lat': 1, 'lon': 2},)):
            resp = APIClient().get('/api/places/?q=xx')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['results'][0]['label'], 'X')


class ChosenPlaceTests(PlanApiTests):
    def test_chosen_places_skip_geocoding(self):
        body = {**self.body, 'current_location': 'anything', 'pickup_location': 'whatever',
                'dropoff_location': 'else',
                'current_place': {'label': 'Alpha, TX', 'lat': 32.0, 'lon': -97.0},
                'pickup_place': {'label': 'Bravo, TX', 'lat': 32.0, 'lon': -95.0},
                'dropoff_place': {'label': 'Charlie, LA', 'lat': 32.0, 'lon': -90.0}}
        with mock.patch('trips.routing.geocode', side_effect=AssertionError('must not geocode')), \
             mock.patch('trips.routing.get_route', fake_route), \
             mock.patch('trips.routing.reverse_geocode_many',
                        lambda pts: [f'Town {i}, TX' for i, _ in enumerate(pts)]):
            resp = APIClient().post('/api/plan/', body, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()['locations']['pickup']['label'], 'Bravo, TX')

    def test_mixed_chosen_and_typed(self):
        body = {**self.body, 'pickup_place': {'label': 'Bravo, TX', 'lat': 32.0, 'lon': -95.0}}
        resp = self.post(body)
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_invalid_chosen_coordinates_rejected(self):
        body = {**self.body, 'pickup_place': {'label': 'Bad', 'lat': 120, 'lon': 0}}
        self.assertEqual(self.post(body).status_code, 400)


# ------------------------------------------------------------ log header tests
from . import services


class LogHeaderTests(SimpleTestCase):
    def test_full_header_follows_paper_log_conventions(self):
        h = services.log_header({
            'driver': ' John E. Doe ', 'co_driver': '', 'carrier': "John Doe's Transportation",
            'office': 'Washington, D.C.', 'home_terminal': '', 'truck': '123', 'trailer': '20544',
            'shipper': "Don's Paper Company", 'commodity': 'Paper products', 'shipping': '101601',
        })
        self.assertEqual(h['driver'], 'John E. Doe')
        self.assertEqual(h['co_driver'], 'N/A')                      # none -> "N/A"
        self.assertEqual(h['home_terminal'], 'Washington, D.C.')     # defaults to main office
        self.assertEqual(h['truck'], 'Tractor 123 / Trailer 20544')
        self.assertEqual(h['shipping'], "101601 / Don's Paper Company - Paper products")

    def test_empty_details_do_not_crash_or_invent_data(self):
        h = services.log_header({})
        self.assertEqual(h['co_driver'], 'N/A')
        for key in ('driver', 'carrier', 'office', 'home_terminal', 'truck', 'shipping'):
            self.assertEqual(h[key], '')

    def test_explicit_home_terminal_and_co_driver_kept(self):
        h = services.log_header({'office': 'A', 'home_terminal': 'B', 'co_driver': 'Jane Roe'})
        self.assertEqual((h['home_terminal'], h['co_driver']), ('B', 'Jane Roe'))

    def test_only_tractor_given(self):
        self.assertEqual(services.log_header({'truck': '7'})['truck'], 'Tractor 7')


class SheetFieldsApiTests(PlanApiTests):
    def test_log_carries_header_and_remark_kinds(self):
        body = {**self.body, 'driver_name': 'John E. Doe', 'truck_number': '123',
                'trailer_number': '20544', 'shipper': "Don's Paper", 'commodity': 'Paper',
                'shipping_doc': '101601', 'main_office': 'Washington, D.C.'}
        data = self.post(body).json()
        log = data['logs'][0]
        self.assertEqual(log['driver'], 'John E. Doe')
        self.assertEqual(log['co_driver'], 'N/A')
        self.assertEqual(log['home_terminal'], 'Washington, D.C.')
        self.assertEqual(log['truck'], 'Tractor 123 / Trailer 20544')
        self.assertEqual(log['shipping'], "101601 / Don's Paper - Paper")
        kinds = {r['kind'] for r in log['remarks']}
        self.assertTrue({'drive', 'pickup'} <= kinds, kinds)


class RestartDayRemarkTests(PlanApiTests):
    def test_full_restart_day_is_explained_in_the_remarks(self):
        # Starting at 20:00 with a full cycle, the 34-hour restart swallows the
        # whole of the next calendar day, so that sheet has no status change.
        body = {**self.body, 'cycle_used_hours': 70, 'start_time': '2026-10-12T20:00:00'}
        logs = self.post(body).json()['logs']
        middle = logs[1]
        self.assertEqual([s['kind'] for s in middle['segments']], [KIND_RESTART])
        self.assertEqual(len(middle['remarks']), 1)
        remark = middle['remarks'][0]
        self.assertEqual(remark['kind'], KIND_RESTART)
        self.assertEqual(remark['hour'], 0.0)
        self.assertIn('continued', remark['text'])
        self.assertTrue(remark['location'])
        self.assertAlmostEqual(sum(middle['totals'].values()), 24.0, places=1)
