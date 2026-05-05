"""
Helpers for discovering and parsing local benchmark datasets.
"""
from __future__ import annotations

from datetime import date, timedelta
import re
from pathlib import Path


MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

REQUIRED_FILES = ("README", "data", "exams", "enrolements")
AVAILABLE_ALGORITHMS = ("greedy", "csp", "ga", "a_star")


def list_benchmarks(root: Path) -> list[dict]:
    """Return local benchmark folders that contain the expected files."""
    datasets = []
    if not root.exists():
        return datasets

    for child in sorted(root.iterdir(), key=lambda item: item.name):
        if not child.is_dir():
            continue
        if not all((child / filename).exists() for filename in REQUIRED_FILES):
            continue

        datasets.append({
            "id": child.name,
            "name": f"Benchmark {child.name}",
            "summary": "University exam timetabling dataset from the local benchmark folder.",
        })

    return datasets


def load_benchmark_dataset(root: Path, benchmark_id: str) -> dict:
    """Parse one benchmark folder into the frontend-friendly dataset shape."""
    benchmark_dir = root / benchmark_id
    if not benchmark_dir.exists() or not benchmark_dir.is_dir():
        raise FileNotFoundError(f"Benchmark '{benchmark_id}' was not found.")

    missing = [filename for filename in REQUIRED_FILES if not (benchmark_dir / filename).exists()]
    if missing:
        missing_display = ", ".join(missing)
        raise FileNotFoundError(
            f"Benchmark '{benchmark_id}' is missing required files: {missing_display}."
        )

    readme_text = (benchmark_dir / "README").read_text(encoding="utf-8", errors="ignore")
    data_text = (benchmark_dir / "data").read_text(encoding="utf-8", errors="ignore")
    exams_text = (benchmark_dir / "exams").read_text(encoding="utf-8", errors="ignore")
    enrollments_text = (benchmark_dir / "enrolements").read_text(encoding="utf-8", errors="ignore")

    courses = _parse_courses(exams_text)
    students = _parse_students_and_enrollments(enrollments_text, courses)
    rooms = _parse_rooms(data_text)
    timeslots = _parse_timeslots(data_text)

    active_courses = [course for course in courses if course["enrollment"] > 0]
    room_slot_capacity = len(rooms) * len(timeslots)
    can_fully_place = room_slot_capacity >= len(active_courses)

    return {
        "courses": active_courses,
        "students": students,
        "rooms": rooms,
        "timeslots": timeslots,
        "meta": {
            "id": benchmark_id,
            "name": f"Benchmark {benchmark_id}",
            "source": "benchmark",
            "summary": _summarize_readme(readme_text),
            "default_algorithm": "greedy",
            "available_algorithms": list(AVAILABLE_ALGORITHMS),
            "room_slot_capacity": room_slot_capacity,
            "can_fully_place": can_fully_place,
            "run_note": (
                "Large benchmarks use reduced runtime settings. Results can be partial when "
                "there are more exams than room-time slots."
            ),
        },
    }


def _parse_courses(exams_text: str) -> list[dict]:
    courses = []
    for raw_line in exams_text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue

        code = line[:8].strip()
        name = line[8:48].strip() or code
        duration_match = re.search(r"(\d+:\d+)", line[48:])
        duration = _parse_duration(duration_match.group(1) if duration_match else "")

        courses.append({
            "code": code,
            "name": name,
            "durationMins": duration,
            "enrollment": 0,
        })

    return courses


def _parse_students_and_enrollments(enrollments_text: str, courses: list[dict]) -> list[dict]:
    by_code = {course["code"]: course for course in courses}
    student_course_map: dict[str, list[str]] = {}

    for raw_line in enrollments_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        parts = line.split()
        if len(parts) < 2:
            continue

        student_id, course_code = parts[0], parts[1]
        student_course_map.setdefault(student_id, []).append(course_code)

        if course_code in by_code:
            by_code[course_code]["enrollment"] += 1

    return [
        {"id": student_id, "courses": courses_taken}
        for student_id, courses_taken in student_course_map.items()
    ]


def _parse_rooms(data_text: str) -> list[dict]:
    rooms_section = _extract_section(data_text, "ROOMS", "ROOM ASSIGNMENTS")
    rooms = []

    for raw_line in rooms_section.splitlines():
        line = raw_line.strip()
        if not line or set(line) == {"-"}:
            continue

        match = re.match(r"^([A-Z0-9-]+)\s+(\d+)\b", line)
        if not match:
            continue

        rooms.append({
            "name": match.group(1),
            "capacity": int(match.group(2)),
        })

    if not rooms:
        rooms = [
            {"name": "Hall-1", "capacity": 500},
            {"name": "Hall-2", "capacity": 400},
        ]

    return rooms


def _parse_timeslots(data_text: str) -> list[dict]:
    dates_section = _extract_section(data_text, "DATES", "TIMES")
    timeslots = []

    date_line = next(
        (line.strip() for line in dates_section.splitlines() if line.strip() and set(line.strip()) != {"-"}),
        "",
    )
    match = re.search(
        r"\w+\s+(\d+)(?:st|nd|rd|th)\s+([A-Za-z]+)\s*-\s*\w+\s+(\d+)(?:st|nd|rd|th)\s+([A-Za-z]+)\s+(\d{4})",
        date_line,
    )
    if not match:
        return []

    start_day = int(match.group(1))
    start_month = MONTHS[match.group(2)[:3].lower()]
    end_day = int(match.group(3))
    end_month = MONTHS[match.group(4)[:3].lower()]
    end_year = int(match.group(5))
    start_year = end_year if start_month <= end_month else end_year - 1

    current = date(start_year, start_month, start_day)
    end = date(end_year, end_month, end_day)

    while current <= end:
        weekday = current.weekday()
        if weekday <= 4:
            timeslots.extend([
                {"date": f"{current.isoformat()} 09:00", "durationMins": 180},
                {"date": f"{current.isoformat()} 13:30", "durationMins": 120},
                {"date": f"{current.isoformat()} 16:30", "durationMins": 120},
            ])
        elif weekday == 5:
            timeslots.append({"date": f"{current.isoformat()} 09:00", "durationMins": 180})

        current += timedelta(days=1)

    return timeslots


def _parse_duration(duration_text: str) -> int:
    if not duration_text:
        return 120

    if ":" in duration_text:
        hours, minutes = duration_text.split(":", maxsplit=1)
        return (int(hours) * 60) + int(minutes)

    parts = duration_text.split()
    if len(parts) == 2 and all(part.isdigit() for part in parts):
        return (int(parts[0]) * 60) + int(parts[1])

    return 120


def _extract_section(text: str, start_marker: str, end_marker: str) -> str:
    if start_marker not in text:
        return ""

    tail = text.split(start_marker, maxsplit=1)[1]
    if end_marker in tail:
        tail = tail.split(end_marker, maxsplit=1)[0]
    return tail


def _summarize_readme(readme_text: str) -> str:
    for line in readme_text.splitlines():
        clean = line.strip()
        if clean:
            return clean
    return "Local benchmark dataset."
