from flask import Flask, render_template, request
from itertools import permutations
from datetime import datetime, timedelta
import webbrowser
app = Flask(__name__)


# =========================================================
# CHARGING STATIONS
# =========================================================

STATIONS = [
    {
        "name": "Station 1",
        "type": "Fast",
        "power": 60,
        "status": "Available"
    },
    {
        "name": "Station 2",
        "type": "Normal",
        "power": 30,
        "status": "Available"
    },
    {
        "name": "Station 3",
        "type": "Fast",
        "power": 50,
        "status": "Available"
    }
]


# =========================================================
# TIME FUNCTIONS
# =========================================================

def time_to_minutes(time_string):
    h, m = map(int, time_string.split(":"))
    return h * 60 + m


def minutes_to_time(minutes):
    minutes = minutes % (24 * 60)
    h = minutes // 60
    m = minutes % 60

    suffix = "AM"

    if h >= 12:
        suffix = "PM"

    display_h = h % 12

    if display_h == 0:
        display_h = 12

    return f"{display_h:02d}:{m:02d} {suffix}"


# =========================================================
# CHARGING TIME
# =========================================================

def calculate_charging_time(ev, station):
    """
    Simple charging-time calculation.

    Battery energy required:
    (target - current) percentage of 60 kWh battery.

    Charging time depends on station power.
    """

    battery_capacity = 60

    energy_needed = (
        (ev["target"] - ev["battery"]) / 100
    ) * battery_capacity

    if energy_needed <= 0:
        return 0

    # Time in hours
    hours = energy_needed / station["power"]

    # Convert to minutes
    minutes = int(hours * 60)

    # Minimum 30 minutes
    return max(minutes, 30)


# =========================================================
# CSP CONSTRAINT CHECKING
# =========================================================

def is_compatible(ev, station):
    """
    Constraint:
    EV requiring fast charging must use a Fast charger.
    """

    if ev["charger"] == "Fast":
        return station["type"] == "Fast"

    return True


def overlaps(start1, end1, start2, end2):
    """
    Checks whether two charging sessions overlap.
    """

    return start1 < end2 and start2 < end1


def check_constraints(ev, station, start_time, end_time, allocation):
    """
    CSP constraint checker.
    """

    # Constraint 1:
    # Charger compatibility
    if not is_compatible(ev, station):
        return False

    # Constraint 2:
    # Charging must finish before departure
    departure = time_to_minutes(ev["departure"])

    if end_time > departure:
        return False

    # Constraint 3:
    # Station cannot charge two EVs at the same time
    for existing in allocation:

        if existing["station"] == station["name"]:

            if overlaps(
                start_time,
                end_time,
                existing["start"],
                existing["end"]
            ):
                return False

    return True


# =========================================================
# BACKTRACKING
# =========================================================

def backtracking(evs, index, allocation, solutions):

    if index == len(evs):
        solutions.append(allocation.copy())
        return

    ev = evs[index]

    arrival = time_to_minutes(ev["arrival"])

    # Try every station
    for station in STATIONS:

        if not is_compatible(ev, station):
            continue

        charging_time = calculate_charging_time(ev, station)

        # Try starting at arrival time
        start_time = arrival

        # If station is busy, try after the latest
        # existing session
        station_allocations = [
            item for item in allocation
            if item["station"] == station["name"]
        ]

        if station_allocations:
            latest_end = max(
                item["end"] for item in station_allocations
            )

            start_time = max(start_time, latest_end)

        end_time = start_time + charging_time

        # CSP constraint checking
        if check_constraints(
            ev,
            station,
            start_time,
            end_time,
            allocation
        ):

            allocation.append({
                "ev": ev["name"],
                "station": station["name"],
                "start": start_time,
                "end": end_time,
                "charging_time": charging_time
            })

            backtracking(
                evs,
                index + 1,
                allocation,
                solutions
            )

            allocation.pop()


# =========================================================
# OPTIMIZATION
# =========================================================

def calculate_score(solution, evs):

    total_waiting = 0
    total_cost = 0

    ev_dictionary = {
        ev["name"]: ev
        for ev in evs
    }

    for item in solution:

        ev = ev_dictionary[item["ev"]]

        arrival = time_to_minutes(ev["arrival"])

        waiting = item["start"] - arrival

        total_waiting += waiting

        # Simple charging cost
        station = next(
            s for s in STATIONS
            if s["name"] == item["station"]
        )

        cost = item["charging_time"] * (
            1.5 if station["type"] == "Fast" else 1
        )

        total_cost += cost

    # Lower score is better
    score = total_waiting + total_cost

    return score, total_waiting, total_cost


# =========================================================
# GREEDY SEARCH
# =========================================================

def greedy_sort(evs):

    """
    Greedy strategy:
    EVs with earlier departure are handled first.
    If same departure, lower battery is prioritized.
    """

    return sorted(
        evs,
        key=lambda ev: (
            time_to_minutes(ev["departure"]),
            ev["battery"]
        )
    )


# =========================================================
# MAIN AI ALGORITHM
# =========================================================

def run_ai(evs):

    # -------------------------------
    # GREEDY SEARCH
    # -------------------------------

    evs = greedy_sort(evs)

    # -------------------------------
    # CSP + BACKTRACKING
    # -------------------------------

    solutions = []

    backtracking(
        evs,
        0,
        [],
        solutions
    )

    # No valid solution
    if not solutions:
        return None

    # -------------------------------
    # OPTIMIZATION
    # -------------------------------

    best_solution = None
    best_score = float("inf")

    best_waiting = 0
    best_cost = 0

    for solution in solutions:

        score, waiting, cost = calculate_score(
            solution,
            evs
        )

        if score < best_score:

            best_score = score
            best_solution = solution
            best_waiting = waiting
            best_cost = cost

    return {
        "allocation": best_solution,
        "waiting": best_waiting,
        "cost": best_cost,
        "score": best_score
    }


# =========================================================
# HOME PAGE
# =========================================================

@app.route("/", methods=["GET", "POST"])
def home():

    result = None
    error = None

    if request.method == "POST":

        evs = []

        # Read 3 EVs
        for i in range(1, 4):

            try:

                ev = {
                    "name": f"EV {i}",

                    "battery": int(
                        request.form[f"battery{i}"]
                    ),

                    "target": int(
                        request.form[f"target{i}"]
                    ),

                    "arrival": request.form[
                        f"arrival{i}"
                    ],

                    "departure": request.form[
                        f"departure{i}"
                    ],

                    "charger": request.form[
                        f"charger{i}"
                    ]
                }

                # Basic validation
                if ev["target"] <= ev["battery"]:
                    raise ValueError(
                        f"EV {i}: Target must be greater than battery."
                    )

                if ev["target"] > 100:
                    raise ValueError(
                        f"EV {i}: Target cannot exceed 100%."
                    )

                evs.append(ev)

            except Exception as e:
                error = str(e)

        if error is None:

            result = run_ai(evs)

            if result is None:

                error = (
                    "No valid allocation found. "
                    "Try changing the EV requirements."
                )

    return render_template(
        "index.html",
        stations=STATIONS,
        result=result,
        error=error
    )


if __name__ == "__main__":
    app.run(
        debug=True,
        port=5000
    )
if __name__=="__main__":
    webbrowser.open("http://127.0.0.1:5000")
    app.run(debug=True)