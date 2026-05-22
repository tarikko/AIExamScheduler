#!/usr/bin/env python3
"""
Test the CURRENT A* scheduler (schedule class on final2 branch) against all benchmarks.
Uses 30s timeout per benchmark to finish in reasonable time.
"""
import csv
import os
import sys
import signal
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from server.algorithms.astar import schedule

BENCHMARK_ROOT = Path(__file__).resolve().parent.parent / "server" / "benchmark" / "exam_benchmark_new_format"
TIMEOUT_SECONDS = 30


class BenchmarkTimeout(Exception):
    pass


def timeout_handler(signum, frame):
    raise BenchmarkTimeout()


def load_benchmark(folder: Path):
    """Load benchmark CSVs into the schedule class format."""
    # rooms
    with open(folder / "rooms.csv", encoding="utf-8-sig") as f:
        room_capacity = {}
        for row in csv.DictReader(f):
            name = row.get("room name", row.get("room_name", "")).strip()
            cap = int(float(row.get("capacity", row.get("room_capacity", "0")).strip()))
            if name:
                room_capacity[name] = cap

    # timeslots
    with open(folder / "timeslots.csv", encoding="utf-8-sig") as f:
        timeslots = [row.get("timeslot", row.get("date", "")).strip()
                     for row in csv.DictReader(f)]
        timeslots = [t for t in timeslots if t]

    days, hours, seen = [], [], set()
    for ts in timeslots:
        parts = ts.split(" ")
        day_str, time_str = parts[0], parts[1] if len(parts) > 1 else "09:00"
        if day_str not in seen:
            days.append(day_str)
            seen.add(day_str)
        h, m = map(int, time_str.split(":"))
        hours.append(h + m / 60.0)

    days.sort()
    days_str = ", ".join(days)
    from_time = f"{int(min(hours)):02d}:{int((min(hours) % 1) * 60):02d}"
    to_time = f"{min(int(max(hours)) + 4, 23):02d}:00"

    # exams
    with open(folder / "exams.csv", encoding="utf-8-sig") as f:
        exam_duration = {}
        for row in csv.DictReader(f):
            code = row.get("exam code", row.get("code", "")).strip()
            dur = int(float(row.get("duration in minutes", row.get("duration", "120")).strip()))
            if code:
                exam_duration[code] = dur / 60.0

    # enrollments
    with open(folder / "enrollements.csv", encoding="utf-8-sig") as f:
        exam_student = []
        students_set = set()
        for row in csv.DictReader(f):
            student = row.get("student code", row.get("student", row.get("student_id", ""))).strip()
            exam = row.get("exam code", row.get("exam", row.get("code", ""))).strip()
            if student and exam:
                exam_student.append((exam, student))
                students_set.add(student)
                if exam not in exam_duration:
                    exam_duration[exam] = 2.0

    return exam_student, room_capacity, from_time, to_time, days_str, exam_duration, {
        "n_exams": len(exam_duration), "n_rooms": len(room_capacity),
        "n_days": len(days), "n_students": len(students_set),
        "n_enrollments": len(exam_student),
    }


def run_one(name, folder):
    """Run A* on one benchmark with timeout."""
    exam_student, room_capacity, from_time, to_time, days_str, exam_duration, meta = load_benchmark(folder)

    my_scheduler = schedule(exam_student, room_capacity, from_time, to_time, days_str, exam_duration)
    n_modules = len(my_scheduler.studentAssignedToModule)
    n_slots = len(my_scheduler.slots)

    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(TIMEOUT_SECONDS)
    start = time.perf_counter()

    try:
        result = my_scheduler.AstarSearch(time_limit_sec=25.0)
        elapsed = time.perf_counter() - start
        signal.alarm(0)
        timed_out = False
    except BenchmarkTimeout:
        elapsed = time.perf_counter() - start
        signal.alarm(0)
        result = "TIMEOUT"
        timed_out = True
    except Exception as e:
        elapsed = time.perf_counter() - start
        signal.alarm(0)
        result = f"ERROR: {e}"
        timed_out = False

    assigned = len(my_scheduler.schedule)
    return {
        "name": name, "result": result, "assigned": assigned,
        "total": n_modules, "unassigned": n_modules - assigned,
        "elapsed": elapsed, "timed_out": timed_out,
        "meta": meta, "n_slots_per_day": n_slots, "n_days": len(my_scheduler.days),
        "schedule_entries": my_scheduler.schedule[:5],  # sample
    }


def main():
    folders = sorted(p for p in BENCHMARK_ROOT.iterdir() if p.is_dir())
    print(f"Testing A* (schedule class, final2 branch) on {len(folders)} benchmarks")
    print(f"Timeout: {TIMEOUT_SECONDS}s per benchmark\n")

    results = []
    for folder in folders:
        name = folder.name
        print(f"▶ {name}...", end=" ", flush=True)
        r = run_one(name, folder)
        results.append(r)

        icon = "✓" if r["result"] == "Success!" else ("⏱" if r["timed_out"] else "✗")
        print(f"{icon} {r['assigned']}/{r['total']} assigned in {r['elapsed']:.2f}s  [{r['result']}]")

        if r["assigned"] > 0 and r["schedule_entries"]:
            for e in r["schedule_entries"][:3]:
                sh = int(e['start']); sm = int(round((e['start']-sh)*60))
                eh = int(e['end']);   em = int(round((e['end']-eh)*60))
                print(f"    {e['exam']:<35} {e['day']:<12} {sh:02d}:{sm:02d}-{eh:02d}:{em:02d}  rooms: {', '.join(e['rooms'])}")

    # Summary table
    print(f"\n{'═'*110}")
    print(f"{'Benchmark':<30} {'Exams':>5} {'Rooms':>5} {'Days':>4} {'Students':>8} "
          f"{'Assigned':>8} {'Unasgn':>6} {'Time':>8} {'Result':<20}")
    print(f"{'─'*110}")
    for r in results:
        m = r["meta"]
        icon = "✓" if r["result"] == "Success!" else ("⏱" if r["timed_out"] else "✗")
        print(f"{icon} {r['name']:<28} {m['n_exams']:>5} {m['n_rooms']:>5} {m['n_days']:>4} "
              f"{m['n_students']:>8} {r['assigned']:>8} {r['unassigned']:>6} "
              f"{r['elapsed']:>7.1f}s {r['result']:<20}")

    solved = [r for r in results if r["result"] == "Success!"]
    timed = [r for r in results if r["timed_out"]]
    no_sol = [r for r in results if r["result"] == "No solution found"]
    errors = [r for r in results if "ERROR" in str(r["result"])]

    print(f"\n{'═'*110}")
    print(f"SUMMARY: {len(solved)} solved | {len(no_sol)} no solution | {len(timed)} timed out | {len(errors)} errors")
    print(f"Total time: {sum(r['elapsed'] for r in results):.1f}s")

    if solved:
        print(f"\n✓ Solved benchmarks:")
        for r in solved:
            print(f"    {r['name']}: {r['assigned']}/{r['total']} in {r['elapsed']:.2f}s")

    if no_sol:
        print(f"\n✗ No solution found:")
        for r in no_sol:
            print(f"    {r['name']}: {r['meta']['n_exams']} exams, {r['meta']['n_rooms']} rooms, {r['meta']['n_days']} days")


if __name__ == "__main__":
    main()
