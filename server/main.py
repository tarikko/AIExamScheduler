"""
FastAPI backend for the Intelligent University Exam Scheduling System.
Provides SSE-streamed algorithm execution and CSV upload endpoints.
"""
import csv
import io
import json
import threading
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from server.models import ScheduleRequest, Room, Timeslot
from server.progress import ProgressTracker
from server.algorithms.genetic import Chromosome, GeneticAlgorithm
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
app.mount("/css", StaticFiles(directory=str(BASE_DIR / "css")), name="css")
app.mount("/js", StaticFiles(directory=str(BASE_DIR / "js")), name="js")
app.mount("/data", StaticFiles(directory=str(BASE_DIR / "data")), name="data")
app.mount("/benchmark", StaticFiles(directory=str(BASE_DIR / "benchmark")), name="benchmark")


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


def _format_result(assignment, course_codes, courses, room_timeslot, fitness, elapsed, algorithm):
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
                    "room_name": room.name,
                    "room_capacity": room.capacity,
                    "timeslot_date": slot.date,
                    "is_late": slot.is_late,
                })

    return {
        "assignments": assignments,
        "fitness": round(fitness, 6) if fitness else 0,
        "elapsed_seconds": round(elapsed, 3),
        "algorithm": algorithm,
    }


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

            domain = list(range(len(room_timeslot)))
            population = [
                Chromosome(
                    size=len(course_codes),
                    domain=domain,
                    mutation_probability=request.mutation_probability,
                )
                for _ in range(request.population_size)
            ]

            ga = GeneticAlgorithm(population, room_timeslot, exam_students)
            best = ga.run(
                generations=request.generations,
                progress_callback=tracker.report_progress,
            )

            elapsed = time.perf_counter() - start
            fitness = ga.fitness(best)

            result = _format_result(
                best.dna, course_codes, request.courses,
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
            csp = CSP(exam_students, room_timeslot)
            assignment, fitness, nodes, elapsed = csp.run(
                time_limit_sec=request.time_limit_sec,
                progress_callback=tracker.report_progress,
            )

            result = _format_result(
                assignment, course_codes, request.courses,
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
                assignment, course_codes, request.courses,
                room_timeslot, fitness, elapsed, "Greedy (Largest Enrollment First)"
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
                time_limit_sec=request.time_limit_sec,
                progress_callback=tracker.report_progress,
            )

            result = _format_result(
                assignment, course_codes, request.courses,
                room_timeslot, fitness, elapsed, "A* Search (Conflict Density Heuristic)"
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


# ─── CSV Upload endpoint ─────────────────────────────────────────────────────

@app.post("/api/upload-csv")
async def upload_csv(file: UploadFile = File(...)):
    """
    Parse an uploaded CSV file into the internal data format.

    Expected CSV columns:
      course_code, course_name, enrollment, student_id, room_name, room_capacity

    Each row is one student-course enrollment.
    Returns JSON in the same shape as fake-data.json.
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted.")

    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))

    courses_map = {}   # code -> {code, name, enrollment}
    students_map = {}  # id   -> set of course codes
    rooms_map = {}     # name -> capacity
    timeslots_set = set()

    for row in reader:
        code = row.get("course_code", "").strip()
        name = row.get("course_name", "").strip()
        enrollment = row.get("enrollment", "0").strip()
        student_id = row.get("student_id", "").strip()
        room_name = row.get("room_name", "").strip()
        room_cap = row.get("room_capacity", "0").strip()
        timeslot = row.get("timeslot", "").strip()

        if code and code not in courses_map:
            courses_map[code] = {
                "code": code,
                "name": name or code,
                "enrollment": int(enrollment) if enrollment else 0,
            }

        if student_id:
            if student_id not in students_map:
                students_map[student_id] = set()
            if code:
                students_map[student_id].add(code)

        if room_name and room_name not in rooms_map:
            rooms_map[room_name] = int(room_cap) if room_cap else 50

        if timeslot:
            timeslots_set.add(timeslot)

    # Build response
    courses = list(courses_map.values())
    students = [{"id": sid, "courses": list(codes)} for sid, codes in students_map.items()]
    rooms = [{"name": rn, "capacity": rc} for rn, rc in rooms_map.items()]
    timeslots = sorted(timeslots_set)

    return {
        "courses": courses,
        "students": students,
        "rooms": rooms,
        "timeslots": timeslots,
    }
