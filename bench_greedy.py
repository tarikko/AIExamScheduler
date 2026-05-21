"""
Benchmark script: runs the Greedy algorithm on multiple benchmarks
and reports runtime + correctness (hard violations == 0).
Uses the same data pipeline as main.py to avoid type mismatches.
"""
import time
import sys
sys.path.insert(0, ".")

from server.data_loader import load_dataset_folder
from server.models import Room, Timeslot, ScheduleRequest
from server.algorithms.greedy import GreedyScheduler, format_greedy_result
from pathlib import Path

BENCHMARK_ROOT = Path("server/benchmark/exam_benchmark_new_format")

BENCHMARKS = [
    "ENSIA_S1",
    "ENSIA_S2",
    "random_sp_06_synthetic",
    "random_sp_11_synthetic",
    "random_sp_16_synthetic",
    "random_sp_26_synthetic",
    "random_sp_46_synthetic",
    "toronto_hec92",
    "toronto_sta83",
    "toronto_ear83",
    "toronto_yor83",
]


def _request_from_dataset(data: dict) -> ScheduleRequest:
    return ScheduleRequest(
        courses=data["courses"],
        students=data["students"],
        rooms=data["rooms"],
        timeslots=[{"date": value} for value in data["timeslots"]],
    )


def run_benchmark(name):
    data = load_dataset_folder(BENCHMARK_ROOT / name)
    request = _request_from_dataset(data)

    rooms = [Room(r.name, r.capacity) for r in request.rooms]
    timeslots = [Timeslot(t.date) for t in request.timeslots]
    room_timeslot = [(room, slot) for room in rooms for slot in timeslots]

    scheduler = GreedyScheduler(
        request.courses, request.students, rooms, timeslots, room_timeslot
    )

    start = time.perf_counter()
    greedy_schedule, penalty, status, room_cap_map = scheduler.run()
    elapsed = time.perf_counter() - start

    if status == "Success!":
        result = format_greedy_result(
            greedy_schedule, penalty, status,
            request.courses, request.students,
            elapsed, "Greedy",
            room_capacity_map=room_cap_map,
        )
        hv = result["metrics"]["hard_violations"]
    else:
        hv = "N/A"

    return elapsed, status, penalty, hv


if __name__ == "__main__":
    print(f"{'Benchmark':<30} {'Time(s)':>8} {'Status':<20} {'Penalty':>8} {'HardViol':>8}")
    print("-" * 80)
    for name in BENCHMARKS:
        try:
            elapsed, status, penalty, hv = run_benchmark(name)
            print(f"{name:<30} {elapsed:>8.3f} {status:<20} {penalty:>8} {str(hv):>8}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"{name:<30} ERROR: {str(e)[:50]}")
