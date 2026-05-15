"""
FastAPI backend for the Intelligent University Exam Scheduling System.
Provides SSE-streamed algorithm execution and CSV upload endpoints.
"""
import threading
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from server.data_loader import list_benchmark_folders, load_dataset_folder, load_uploaded_dataset
from server.models import ScheduleRequest, Room, Timeslot, Exam, AlgorithmSettings
from server.progress import ProgressTracker
from server.algorithms.genetic import GeneticAlgorithm
from server.algorithms.csp import CSP
from server.algorithms.greedy import GreedyScheduler
from server.algorithms.astar import AStarScheduler

# ─── App setup ────────────────────────────────────────────────────────────────

app = FastAPI(title="Exam Scheduler API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static frontend files
BASE_DIR = Path(__file__).resolve().parent.parent
BENCHMARK_ROOT = BASE_DIR / "server" / "benchmark" / "exam_benchmark_new_format"
app.mount("/css", StaticFiles(directory=str(BASE_DIR / "css")), name="css")
app.mount("/js", StaticFiles(directory=str(BASE_DIR / "js")), name="js")


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """Serve the main frontend page."""
    index_path = BASE_DIR / "index.html"
    return HTMLResponse(content=index_path.read_text(encoding="utf-8"))


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _build_domain(request: ScheduleRequest):
    """Build internal Room/Timeslot objects and the cartesian product domain."""
    rooms = [Room(r.name, r.capacity) for r in request.rooms]
    timeslots = [Timeslot(t.date) for t in request.timeslots]
    room_timeslot = [(room, slot) for room in rooms for slot in timeslots]

    # Build exam_students as a list of sets of student IDs
    course_codes = [c.code for c in request.courses]
    exam_students = []
    for code in course_codes:
        enrolled = set()
        for s in request.students:
            if code in s.courses:
                enrolled.add(s.id)
        exam_students.append(enrolled)

    return rooms, timeslots, room_timeslot, course_codes, exam_students


def _request_from_dataset(data: dict) -> ScheduleRequest:
    """Convert a loaded four-file dataset into a scheduling request."""
    return ScheduleRequest(
        courses=data["courses"],
        students=data["students"],
        rooms=data["rooms"],
        timeslots=[{"date": value} for value in data["timeslots"]],
    )


def _apply_algorithm_settings(request: ScheduleRequest, settings: AlgorithmSettings | None) -> ScheduleRequest:
    if not settings:
        return request
    if settings.generations is not None:
        request.generations = settings.generations
    if settings.population_size is not None:
        request.population_size = settings.population_size
    if settings.mutation_probability is not None:
        request.mutation_probability = settings.mutation_probability
    if settings.time_limit_sec is not None:
        request.time_limit_sec = settings.time_limit_sec
    if settings.first_find is not None:
        request.first_find = settings.first_find
    return request


def _compute_metrics(assignment, courses, students, room_timeslot, fitness, elapsed):
    """Compute hard/soft violation and load metrics for a schedule."""
    assignment = assignment or []
    timeslot_order = {}
    for _, slot in room_timeslot:
        if slot.date not in timeslot_order:
            timeslot_order[slot.date] = len(timeslot_order)

    assigned_by_course = {}
    room_slot_map = {}
    room_daily_load = {}
    capacity_violations = 0
    unassigned = []

    for exam_idx, course in enumerate(courses):
        gene = assignment[exam_idx] if exam_idx < len(assignment) else None
        if gene is None or not isinstance(gene, int) or gene < 0 or gene >= len(room_timeslot):
            unassigned.append(course.code)
            continue
        room, slot = room_timeslot[gene]
        assigned_by_course[course.code] = {"exam_idx": exam_idx, "room": room, "slot": slot}
        if room.capacity < course.enrollment:
            capacity_violations += 1
        room_slot_map.setdefault((room.name, slot.date), []).append(course.code)
        room_daily_load[(room.name, slot.day)] = room_daily_load.get((room.name, slot.day), 0) + 1

    room_conflicts = sum(max(0, len(codes) - 1) for codes in room_slot_map.values())
    student_conflicts = 0
    consecutive_exam_stress = 0
    student_day_load = {}

    for student in students:
        assigned_exams = []
        for code in student.courses:
            item = assigned_by_course.get(code)
            if item:
                assigned_exams.append((timeslot_order.get(item["slot"].date, 0), code, item["slot"]))

        slot_courses = {}
        for _, code, slot in assigned_exams:
            slot_courses.setdefault(slot.date, []).append(code)
        student_conflicts += sum(max(0, len(codes) - 1) for codes in slot_courses.values())

        by_day = {}
        for slot_index, code, slot in sorted(assigned_exams):
            by_day.setdefault(slot.day, []).append((slot_index, code))
        for day, exams in by_day.items():
            student_day_load[(student.id, day)] = len(exams)
            for left, right in zip(exams, exams[1:]):
                if right[0] == left[0] + 1:
                    consecutive_exam_stress += 1

    hard_violations = capacity_violations + room_conflicts + student_conflicts + len(unassigned)
    penalty = hard_violations * 100 + consecutive_exam_stress * 3
    room_daily_load_rows = [
        {"room": room, "day": day, "exam_count": count}
        for (room, day), count in sorted(room_daily_load.items())
    ]

    return {
        "elapsed_seconds": round(elapsed, 3),
        "fitness": round(fitness, 6) if fitness else 0,
        "penalty": penalty,
        "assigned_count": len(assigned_by_course),
        "unassigned_count": len(unassigned),
        "unassigned_courses": unassigned,
        "hard_violations": hard_violations,
        "capacity_violations": capacity_violations,
        "student_conflict_count": student_conflicts,
        "room_conflict_count": room_conflicts,
        "consecutive_exam_stress": consecutive_exam_stress,
        "room_daily_load": room_daily_load_rows,
        "max_room_daily_exams": max((row["exam_count"] for row in room_daily_load_rows), default=0),
    }


def _format_result(assignment, course_codes, courses, students, room_timeslot, fitness, elapsed, algorithm):
    """Convert algorithm output into JSON-serializable result dict."""
    assignments = []
    if assignment is not None:
        for exam_idx, gene in enumerate(assignment):
            if gene is not None and isinstance(gene, int):
                room, slot = room_timeslot[gene]
                course = courses[exam_idx]
                assignments.append({
                    "exam_index": exam_idx,
                    "course_code": course.code,
                    "course_name": course.name,
                    "enrollment": course.enrollment,
                    "duration_minutes": course.duration_minutes,
                    "room_name": room.name,
                    "room_capacity": room.capacity,
                    "timeslot_date": slot.date,
                    "is_late": slot.is_late,
                })
    metrics = _compute_metrics(assignment, courses, students, room_timeslot, fitness, elapsed)

    return {
        "assignments": assignments,
        "fitness": round(fitness, 6) if fitness else 0,
        "elapsed_seconds": round(elapsed, 3),
        "algorithm": algorithm,
        "metrics": metrics,
    }


def _attach_dataset(result: dict, data: dict) -> dict:
    """Include render-only dataset resources in a scheduling response."""
    result["dataset"] = {
        "courses": data["courses"],
        "students": data["students"],
        "rooms": data["rooms"],
        "timeslots": data["timeslots"],
        "metadata": data.get("metadata", {}),
    }
    return result


def _run_algorithm_by_key(key: str, request: ScheduleRequest, tracker: ProgressTracker, dataset: dict | None = None):
    rooms, timeslots, room_timeslot, course_codes, exam_students = _build_domain(request)

    def finish(result: dict):
        tracker.finish(_attach_dataset(result, dataset) if dataset else result)

    try:
        import time
        if key == "ga":
            start = time.perf_counter()
            population_size, generations, time_limit = _ga_runtime_config(request)
            exams = [
                Exam(
                    exam_code=course.code,
                    exam_name=course.name,
                    students=exam_students[index],
                    exam_duration=course.duration_minutes,
                )
                for index, course in enumerate(request.courses)
            ]
            ga = GeneticAlgorithm(exams, room_timeslot, population_size=population_size)
            if time_limit is None:
                best = ga.run(
                    max_generations=generations,
                    progress_callback=tracker.report_progress,
                )
            else:
                best = ga.run(
                    max_generations=generations,
                    time_limit=time_limit,
                    progress_callback=tracker.report_progress,
                )
            elapsed = time.perf_counter() - start
            result = _format_result(
                best.dna, course_codes, request.courses, request.students,
                room_timeslot, ga.fitness(best), elapsed, "Genetic Algorithm"
            )
            finish(result)
            return

        if key == "csp":
            exams = [
                Exam(
                    exam_code=course.code,
                    exam_name=course.name,
                    students=exam_students[index],
                    exam_duration=course.duration_minutes,
                )
                for index, course in enumerate(request.courses)
            ]
            csp = CSP(exams, room_timeslot)
            assignment, fitness, nodes, elapsed = csp.run(
                time_limit_sec=_resolve_time_limit(request.time_limit_sec),
                first_find=request.first_find,
                progress_callback=tracker.report_progress,
            )
            result = _format_result(
                assignment, course_codes, request.courses, request.students,
                room_timeslot, fitness, elapsed, "CSP (MRV + Forward Checking)"
            )
            finish(result)
            return

        if key == "greedy":
            start = time.perf_counter()
            scheduler = GreedyScheduler(exam_students, room_timeslot, [c.enrollment for c in request.courses])
            assignment, fitness = scheduler.run(progress_callback=tracker.report_progress)
            elapsed = time.perf_counter() - start
            result = _format_result(
                assignment, course_codes, request.courses, request.students,
                room_timeslot, fitness, elapsed, "Greedy (Degree + Enrollment)"
            )
            finish(result)
            return

        if key == "a_star":
            scheduler = AStarScheduler(exam_students, room_timeslot, [c.enrollment for c in request.courses])
            assignment, fitness, nodes, elapsed = scheduler.run(
                time_limit_sec=_resolve_time_limit(request.time_limit_sec),
                progress_callback=tracker.report_progress,
            )
            result = _format_result(
                assignment, course_codes, request.courses, request.students,
                room_timeslot, fitness, elapsed, "A* Search (Notebook Port)"
            )
            finish(result)
            return

        tracker.fail(f"Unknown algorithm: {key}")
    except Exception as exc:
        tracker.fail(str(exc))


def _sse_response(tracker: ProgressTracker) -> StreamingResponse:
    return StreamingResponse(
        tracker.stream_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _ga_runtime_config(request: ScheduleRequest) -> tuple[int, int, float | None]:
    """Use GA settings from the request without dataset-size caps."""
    population = max(2, int(request.population_size))
    generations = max(1, int(request.generations))
    time_limit = None
    if request.time_limit_sec is not None:
        time_limit = max(1.0, float(request.time_limit_sec))
    return population, generations, time_limit


def _resolve_time_limit(value: float | None, default: float = 5.0) -> float:
    if value is None:
        return default
    return max(1.0, float(value))


# ─── Scheduling endpoints ────────────────────────────────────────────────────

@app.post("/api/schedule/ga")
async def run_genetic_algorithm(request: ScheduleRequest):
    """Run the genetic algorithm and stream progress via SSE."""
    tracker = ProgressTracker()
    rooms, timeslots, room_timeslot, course_codes, exam_students = _build_domain(request)

    def run_ga():
        try:
            import time
            start = time.perf_counter()

            population_size, generations, time_limit = _ga_runtime_config(request)
            exams = [
                Exam(
                    exam_code=course.code,
                    exam_name=course.name,
                    students=exam_students[index],
                    exam_duration=course.duration_minutes,
                )
                for index, course in enumerate(request.courses)
            ]

            ga = GeneticAlgorithm(exams, room_timeslot, population_size=population_size)
            if time_limit is None:
                best = ga.run(
                    max_generations=generations,
                    progress_callback=tracker.report_progress,
                )
            else:
                best = ga.run(
                    max_generations=generations,
                    time_limit=time_limit,
                    progress_callback=tracker.report_progress,
                )

            elapsed = time.perf_counter() - start
            fitness = ga.fitness(best)

            result = _format_result(
                best.dna, course_codes, request.courses, request.students,
                room_timeslot, fitness, elapsed, "Genetic Algorithm"
            )
            tracker.finish(result)
        except Exception as e:
            tracker.fail(str(e))

    thread = threading.Thread(target=run_ga, daemon=True)
    thread.start()

    return StreamingResponse(
        tracker.stream_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/schedule/csp")
async def run_csp_algorithm(request: ScheduleRequest):
    """Run the CSP solver and stream progress via SSE."""
    tracker = ProgressTracker()
    rooms, timeslots, room_timeslot, course_codes, exam_students = _build_domain(request)

    def run_csp():
        try:
            import time
            start = time.perf_counter()
            exams = [
                Exam(
                    exam_code=course.code,
                    exam_name=course.name,
                    students=exam_students[index],
                    exam_duration=course.duration_minutes,
                )
                for index, course in enumerate(request.courses)
            ]
            csp = CSP(exams, room_timeslot)
            assignment, fitness, nodes, elapsed = csp.run(
                time_limit_sec=_resolve_time_limit(request.time_limit_sec),
                first_find=request.first_find,
                progress_callback=tracker.report_progress,
            )

            result = _format_result(
                assignment, course_codes, request.courses, request.students,
                room_timeslot, fitness, elapsed, "CSP (MRV + Forward Checking)"
            )
            tracker.finish(result)
        except Exception as e:
            tracker.fail(str(e))

    thread = threading.Thread(target=run_csp, daemon=True)
    thread.start()

    return StreamingResponse(
        tracker.stream_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/schedule/greedy")
async def run_greedy_algorithm(request: ScheduleRequest):
    """Run the greedy scheduler and stream progress via SSE."""
    tracker = ProgressTracker()
    rooms, timeslots, room_timeslot, course_codes, exam_students = _build_domain(request)

    def run_greedy():
        try:
            import time
            start = time.perf_counter()

            enrollments = [c.enrollment for c in request.courses]
            scheduler = GreedyScheduler(exam_students, room_timeslot, enrollments)
            assignment, fitness = scheduler.run(
                progress_callback=tracker.report_progress,
            )

            elapsed = time.perf_counter() - start

            result = _format_result(
                assignment, course_codes, request.courses, request.students,
                room_timeslot, fitness, elapsed, "Greedy (Degree + Enrollment)"
            )
            tracker.finish(result)
        except Exception as e:
            tracker.fail(str(e))

    thread = threading.Thread(target=run_greedy, daemon=True)
    thread.start()

    return StreamingResponse(
        tracker.stream_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/schedule/a_star")
async def run_astar_algorithm(request: ScheduleRequest):
    """Run the A* search and stream progress via SSE."""
    tracker = ProgressTracker()
    rooms, timeslots, room_timeslot, course_codes, exam_students = _build_domain(request)

    def run_astar():
        try:
            enrollments = [c.enrollment for c in request.courses]
            scheduler = AStarScheduler(exam_students, room_timeslot, enrollments)
            assignment, fitness, nodes, elapsed = scheduler.run(
                time_limit_sec=_resolve_time_limit(request.time_limit_sec),
                progress_callback=tracker.report_progress,
            )

            result = _format_result(
                assignment, course_codes, request.courses, request.students,
                room_timeslot, fitness, elapsed, "A* Search (Notebook Port)"
            )
            tracker.finish(result)
        except Exception as e:
            tracker.fail(str(e))

    thread = threading.Thread(target=run_astar, daemon=True)
    thread.start()

    return StreamingResponse(
        tracker.stream_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/schedule-benchmark/{algorithm}/{benchmark_name}")
async def run_benchmark_algorithm(
    algorithm: str,
    benchmark_name: str,
    settings: AlgorithmSettings | None = None,
):
    """Run an algorithm against a server-side benchmark by name."""
    safe_name = Path(benchmark_name).name
    if safe_name != benchmark_name:
        raise HTTPException(status_code=400, detail="Invalid benchmark name.")
    if algorithm not in {"greedy", "csp", "ga", "a_star"}:
        raise HTTPException(status_code=400, detail=f"Unknown algorithm: {algorithm}")

    data = load_dataset_folder(BENCHMARK_ROOT / safe_name)
    request = _apply_algorithm_settings(_request_from_dataset(data), settings)
    tracker = ProgressTracker()
    thread = threading.Thread(
        target=_run_algorithm_by_key,
        args=(algorithm, request, tracker, data),
        daemon=True,
    )
    thread.start()
    return _sse_response(tracker)


# ─── CSV Upload endpoint ─────────────────────────────────────────────────────

@app.post("/api/upload-dataset")
async def upload_dataset(files: list[UploadFile] = File(...)):
    """Parse the canonical four-file CSV upload format."""
    return await load_uploaded_dataset(files)


@app.post("/api/upload-csv")
async def upload_csv_compat():
    """Deprecated endpoint kept to return a clear migration error."""
    raise HTTPException(
        status_code=410,
        detail="Single CSV upload is deprecated. Upload rooms.csv, timeslots.csv, exams.csv, and enrollements.csv.",
    )


@app.get("/api/benchmarks")
async def list_benchmarks():
    """List benchmark folders from benchmark/exam_benchmark_new_format."""
    return {"benchmarks": list_benchmark_folders(BENCHMARK_ROOT)}


@app.get("/api/benchmarks/{benchmark_name}")
async def load_benchmark(benchmark_name: str):
    """Load one benchmark folder by name."""
    safe_name = Path(benchmark_name).name
    if safe_name != benchmark_name:
        raise HTTPException(status_code=400, detail="Invalid benchmark name.")
    return load_dataset_folder(BENCHMARK_ROOT / safe_name)


@app.get("/api/default-dataset")
async def load_default_dataset():
    """Load a small new-format benchmark for the initial app state."""
    return load_dataset_folder(BENCHMARK_ROOT / "random_sp_06_synthetic")
