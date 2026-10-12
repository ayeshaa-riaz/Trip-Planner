"""
Hours-of-Service (HOS) trip planner for a property-carrying CMV driver.

Implements the rules from FMCSA's "Interstate Truck Driver's Guide to Hours of
Service" (49 CFR Part 395) that matter for planning a single trip:

* 14-hour driving window  - 14 consecutive hours after coming on duty, during
  which up to 11 hours may be driven. Off-duty time does not pause the window.
* 11-hour driving limit   - max 11 hours of driving after 10 consecutive hours
  off duty.
* 30-minute break         - required once 8 cumulative hours of driving have
  passed without an interruption of at least 30 consecutive minutes (on duty
  not driving, off duty, or sleeper berth all qualify).
* 70-hour / 8-day limit   - may not drive after 70 on-duty hours in 8 days.
* 34-hour restart         - 34 consecutive hours off duty resets the cycle.
* 10 consecutive hours off duty (we use the sleeper berth) resets the 11-hour
  and 14-hour clocks.

Trip assumptions (from the assignment brief):

* Property-carrying driver on the 70 hr / 8 day schedule, no adverse driving
  conditions.
* Fuel at least once every 1,000 miles.
* 1 hour for pickup and 1 hour for drop-off (on duty, not driving).

The module is pure Python (no Django, no network) so it can be unit tested.
All times are "hours since midnight of the trip's first day" in the home
terminal's time zone.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional

# Duty statuses (the four rows of the driver's daily log grid)
OFF_DUTY = 'off_duty'
SLEEPER = 'sleeper'
DRIVING = 'driving'
ON_DUTY = 'on_duty'
STATUSES = (OFF_DUTY, SLEEPER, DRIVING, ON_DUTY)

# Segment kinds (why a segment exists) - used for map stops and log remarks
KIND_DRIVE = 'drive'
KIND_PICKUP = 'pickup'
KIND_DROPOFF = 'dropoff'
KIND_FUEL = 'fuel'
KIND_BREAK = 'break'
KIND_REST = 'rest'
KIND_RESTART = 'restart'
KIND_OFF = 'off'

# Regulatory limits (hours)
MAX_DRIVING_HOURS = 11.0
MAX_WINDOW_HOURS = 14.0
DRIVING_BEFORE_BREAK_HOURS = 8.0
BREAK_HOURS = 0.5
REST_HOURS = 10.0
RESTART_HOURS = 34.0
CYCLE_LIMIT_HOURS = 70.0

# Assignment assumptions / planning constants
FUEL_INTERVAL_MILES = 1000.0
FUEL_STOP_HOURS = 0.5
PICKUP_HOURS = 1.0
DROPOFF_HOURS = 1.0
AVERAGE_SPEED_MPH = 55.0

EPS = 1e-6


@dataclass
class Segment:
    status: str
    start: float          # hours since midnight of day 0
    end: float
    kind: str
    label: str
    mile: float           # route mile at the start of the segment
    miles: float = 0.0    # miles driven during the segment

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_dict(self) -> dict:
        return asdict(self)


class TripPlanner:
    """Simulates a trip hour by hour and emits duty-status segments."""

    def __init__(
        self,
        leg1_miles: float,
        leg2_miles: float,
        cycle_used: float,
        start_hour: float,
        speed_mph: float = AVERAGE_SPEED_MPH,
    ):
        if not 0 <= cycle_used <= CYCLE_LIMIT_HOURS:
            raise ValueError('cycle_used must be between 0 and 70 hours')
        if leg1_miles < 0 or leg2_miles < 0:
            raise ValueError('leg distances must be non-negative')

        self.leg1_miles = leg1_miles
        self.leg2_miles = leg2_miles
        self.speed = speed_mph

        self.t = start_hour
        self.mile = 0.0
        self.segments: list[Segment] = []

        # HOS clocks
        self.cycle = cycle_used          # on-duty hours counted toward 70
        self.drive_today = 0.0           # driving since last 10h reset
        self.window_start: Optional[float] = None
        self.since_break = 0.0           # driving since last >=30 min break
        self.next_fuel_mile = FUEL_INTERVAL_MILES

    # ------------------------------------------------------------------ clocks
    def _window_left(self) -> float:
        if self.window_start is None:
            return MAX_WINDOW_HOURS
        return MAX_WINDOW_HOURS - (self.t - self.window_start)

    def _add(self, status, duration, kind, label, miles=0.0):
        if duration <= EPS:
            return
        if status in (DRIVING, ON_DUTY):
            if self.window_start is None:
                self.window_start = self.t
            self.cycle += duration
        if status == DRIVING:
            self.drive_today += duration
            self.since_break += duration
        # Any >=30 min break from driving (on duty not driving counts too)
        if status != DRIVING and duration >= BREAK_HOURS - EPS:
            self.since_break = 0.0
        if status in (OFF_DUTY, SLEEPER):
            if duration >= REST_HOURS - EPS:
                self.drive_today = 0.0
                self.window_start = None
            if duration >= RESTART_HOURS - EPS:
                self.cycle = 0.0

        self.segments.append(
            Segment(status, self.t, self.t + duration, kind, label, self.mile, miles)
        )
        self.t += duration
        self.mile += miles

    # ----------------------------------------------------------------- actions
    def _rest(self):
        self._add(SLEEPER, REST_HOURS, KIND_REST, '10-hour rest (sleeper berth)')

    def _restart(self):
        self._add(OFF_DUTY, RESTART_HOURS, KIND_RESTART, '34-hour restart (off duty)')

    def _break(self):
        self._add(OFF_DUTY, BREAK_HOURS, KIND_BREAK, '30-minute rest break')

    def _fuel(self):
        self._add(ON_DUTY, FUEL_STOP_HOURS, KIND_FUEL, 'Fueling')
        self.next_fuel_mile += FUEL_INTERVAL_MILES

    def _work(self, hours, kind, label):
        """On-duty, not-driving task (pickup / drop-off)."""
        if self.cycle >= CYCLE_LIMIT_HOURS - EPS:
            self._restart()
        if self._window_left() <= EPS:
            self._rest()
        self._add(ON_DUTY, hours, kind, label)

    def _drive(self, miles_to_go: float, label: str):
        while miles_to_go > EPS:
            if self.cycle >= CYCLE_LIMIT_HOURS - EPS:
                self._restart()
            elif self.drive_today >= MAX_DRIVING_HOURS - EPS or self._window_left() <= EPS:
                self._rest()
            elif self.mile >= self.next_fuel_mile - EPS:
                self._fuel()
            elif self.since_break >= DRIVING_BEFORE_BREAK_HOURS - EPS:
                self._break()
            else:
                hours = min(
                    MAX_DRIVING_HOURS - self.drive_today,
                    self._window_left(),
                    DRIVING_BEFORE_BREAK_HOURS - self.since_break,
                    CYCLE_LIMIT_HOURS - self.cycle,
                    miles_to_go / self.speed,
                    (self.next_fuel_mile - self.mile) / self.speed,
                )
                miles = hours * self.speed
                self._add(DRIVING, hours, KIND_DRIVE, label, miles)
                miles_to_go -= miles

    # -------------------------------------------------------------------- plan
    def plan(self) -> list[Segment]:
        self._drive(self.leg1_miles, 'Driving to pickup')
        self._work(PICKUP_HOURS, KIND_PICKUP, 'Pickup (loading)')
        self._drive(self.leg2_miles, 'Driving to drop-off')
        self._work(DROPOFF_HOURS, KIND_DROPOFF, 'Drop-off (unloading)')
        return self.segments


# --------------------------------------------------------------------- logging
@dataclass
class DayLog:
    day: int                      # 0-based day index from trip start
    segments: list                # list[Segment] clipped to [0, 24] of that day
    totals: dict
    miles: float
    on_duty_hours: float          # driving + on duty (lines 3 & 4)
    restart_end: Optional[float] = None  # hour of this day a 34h restart ended


def _clip(seg: Segment, lo: float, hi: float) -> Optional[Segment]:
    s, e = max(seg.start, lo), min(seg.end, hi)
    if e - s <= EPS:
        return None
    frac_start = (s - seg.start) / seg.duration if seg.duration else 0
    miles = seg.miles * (e - s) / seg.duration if seg.duration else 0
    return Segment(
        seg.status, s - lo, e - lo, seg.kind, seg.label,
        seg.mile + seg.miles * frac_start, miles,
    )


def build_day_logs(segments: list[Segment], start_hour: float) -> list[DayLog]:
    """Split the trip into 24-hour calendar-day logs.

    Time before the trip starts and after it ends is logged as off duty so that
    every sheet totals exactly 24 hours (guide: "the total of the entries must
    equal 24 hours").
    """
    end = segments[-1].end if segments else start_hour
    days = max(1, int(-(-end // 24)))  # ceil
    first_mile = segments[0].mile if segments else 0.0
    last_mile = segments[-1].mile + segments[-1].miles if segments else 0.0

    full = list(segments)
    if start_hour > EPS:
        full.insert(0, Segment(OFF_DUTY, 0.0, start_hour, KIND_OFF, 'Off duty', first_mile))
    if end < days * 24 - EPS:
        full.append(Segment(OFF_DUTY, end, days * 24.0, KIND_OFF, 'Off duty', last_mile))

    logs = []
    for d in range(days):
        lo, hi = d * 24.0, (d + 1) * 24.0
        clipped = [c for c in (_clip(s, lo, hi) for s in full) if c]
        restart_end = next(
            (s.end - lo for s in full
             if s.kind == KIND_RESTART and lo - EPS < s.end <= hi + EPS),
            None,
        )
        totals = {s: 0.0 for s in STATUSES}
        miles = 0.0
        for c in clipped:
            totals[c.status] += c.duration
            miles += c.miles
        logs.append(DayLog(
            day=d,
            segments=clipped,
            totals={k: round(v, 2) for k, v in totals.items()},
            miles=round(miles, 1),
            on_duty_hours=round(totals[DRIVING] + totals[ON_DUTY], 2),
            restart_end=restart_end,
        ))
    return logs


def cycle_recaps(logs: list[DayLog], cycle_used: float) -> list[dict]:
    """Compute the 70-hour / 8-day recap block of each daily log.

    A = total hours on duty last 7 days including today
    B = hours available tomorrow (70 minus A)
    C = total hours on duty last 8 days including today

    ``cycle_used`` (hours already on duty in the current cycle before the trip)
    is carried until a 34-hour restart, matching how the planner counts it.
    A restart wipes the count, so only hours after it are included.
    """
    recaps = []
    baseline = cycle_used
    history: list[float] = []  # on-duty hours of trip days since last restart
    for log in logs:
        counted = log.on_duty_hours
        if log.restart_end is not None:
            baseline, history = 0.0, []
            counted = sum(
                c.duration for c in log.segments
                if c.status in (DRIVING, ON_DUTY) and c.start >= log.restart_end - EPS
            )
        history.append(counted)
        a = baseline + sum(history[-7:])
        c = baseline + sum(history[-8:])
        recaps.append({
            'on_duty_today': round(log.on_duty_hours, 2),
            'a': round(a, 2),
            'b': round(max(0.0, CYCLE_LIMIT_HOURS - a), 2),
            'c': round(c, 2),
        })
    return recaps
