"""
Baseline benchmark: simulates the UNOPTIMIZED greedy algorithm
to compare performance before/after optimizations.
Uses the original calculate_g-per-candidate approach.
"""
import time, sys, copy
sys.path.insert(0, ".")

from server.data_loader import load_dataset_folder
from server.models import Room, Timeslot, ScheduleRequest
from server.algorithms.greedy import schedule as ScheduleClass, GreedyScheduler, format_greedy_result
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

def _request_from_dataset(data):
    return ScheduleRequest(
        courses=data["courses"], students=data["students"],
        rooms=data["rooms"], timeslots=[{"date": v} for v in data["timeslots"]],
    )

# Monkey-patch to simulate the UNOPTIMIZED code paths
def unoptimized_greedySearch(self, strategy='largest_enrollment', progress_callback=None):
    if strategy == 'degree_heuristic':
        ordered_exams = self.order_by_degree_heuristic()
    else:
        ordered_exams = self.order_by_largest_enrollment()
    current_schedule = []
    for exam in ordered_exams:
        student_set = self.studentAssignedToModule[exam]
        # UNOPTIMIZED: full schedule scan (no schedule_by_day)
        valid_placements = self.find_valid_placements(exam, student_set, current_schedule)
        if not valid_placements:
            return "No solution found"
        best_placement = unoptimized_pick_best(self, valid_placements, current_schedule)
        current_schedule.append(best_placement)
    self.schedule = current_schedule
    return "Success!"

def unoptimized_pick_best(self, valid_placements, current_schedule):
    # UNOPTIMIZED: calls calculate_g(current_schedule) ONCE PER CANDIDATE
    def placement_score(placement):
        trial_schedule = current_schedule + [placement]
        penalty_after = self.calculate_g(trial_schedule)
        penalty_before = self.calculate_g(current_schedule)
        incremental_penalty = penalty_after - penalty_before
        day_index = self.days.index(placement['day']) if placement['day'] in self.days else 999
        start_time = placement['start']
        return (incremental_penalty, day_index, start_time)
    return min(valid_placements, key=placement_score)

def run_baseline(name):
    data = load_dataset_folder(BENCHMARK_ROOT / name)
    request = _request_from_dataset(data)
    rooms = [Room(r.name, r.capacity) for r in request.rooms]
    timeslots = [Timeslot(t.date) for t in request.timeslots]
    room_timeslot = [(room, slot) for room in rooms for slot in timeslots]
    scheduler = GreedyScheduler(request.courses, request.students, rooms, timeslots, room_timeslot)

    # Build the schedule object manually (same as run() does)
    exam_student_pairs = scheduler._exam_student_pairs
    room_capacity_dict = scheduler._build_room_capacity()
    from_time, to_time = scheduler._derive_time_range()
    days_str = scheduler._derive_days_string()
    exam_duration_dict = scheduler._build_exam_duration()
    sched = ScheduleClass(exam_student_pairs, room_capacity_dict, from_time, to_time, days_str, exam_duration_dict)

    start = time.perf_counter()
    result_str = unoptimized_greedySearch(sched)
    elapsed = time.perf_counter() - start
    return elapsed, result_str

if __name__ == "__main__":
    print(f"{'Benchmark':<30} {'Baseline(s)':>12}")
    print("-" * 45)
    for name in BENCHMARKS:
        try:
            elapsed, status = run_baseline(name)
            print(f"{name:<30} {elapsed:>12.3f}  {status}")
        except Exception as e:
            import traceback; traceback.print_exc()
            print(f"{name:<30} ERROR: {str(e)[:50]}")
