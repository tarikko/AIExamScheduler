"""
Dataset loading helpers for the four-file exam scheduling CSV format.
"""
import csv
import io
from pathlib import Path
from typing import Iterable

from fastapi import HTTPException, UploadFile


REQUIRED_FILES = {
    "rooms.csv",
    "timeslots.csv",
    "exams.csv",
    "enrollements.csv",
}

HEADER_ALIASES = {
    "room name": ("room name", "room", "room_name", "name"),
    "capacity": ("capacity", "room_capacity"),
    "timeslot": ("timeslot", "date"),
    "exam code": ("exam code", "exam", "code", "course_code"),
    "exam name": ("exam name", "name", "course_name"),
    "duration in minutes": ("duration in minutes", "duration", "duration_minutes"),
    "student code": ("student code", "student", "student_id", "id"),
}


def _normalize_header(value: str) -> str:
    return value.strip().lower().replace("_", " ")


def _pick(row: dict, canonical: str, default: str = "") -> str:
    normalized = {_normalize_header(k): (v or "").strip() for k, v in row.items()}
    for alias in HEADER_ALIASES[canonical]:
        value = normalized.get(_normalize_header(alias), "")
        if value:
            return value
    return default


def _read_csv_text(text: str, filename: str) -> list[dict]:
    sample = text.lstrip("\ufeff")
    reader = csv.DictReader(io.StringIO(sample))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail=f"{filename} has no CSV header row.")
    return list(reader)


def _require_columns(rows: list[dict], filename: str, required: Iterable[str]) -> None:
    if not rows:
        raise HTTPException(status_code=400, detail=f"{filename} is empty.")
    headers = {_normalize_header(h) for h in rows[0].keys()}
    missing = []
    for column in required:
        aliases = {_normalize_header(alias) for alias in HEADER_ALIASES[column]}
        if headers.isdisjoint(aliases):
            missing.append(column)
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"{filename} is missing required column(s): {', '.join(missing)}.",
        )


def _parse_dataset(files: dict[str, str], source_name: str) -> dict:
    missing = REQUIRED_FILES - set(files)
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required file(s): {', '.join(sorted(missing))}.",
        )

    rooms_rows = _read_csv_text(files["rooms.csv"], "rooms.csv")
    timeslot_rows = _read_csv_text(files["timeslots.csv"], "timeslots.csv")
    exam_rows = _read_csv_text(files["exams.csv"], "exams.csv")
    enrolment_rows = _read_csv_text(files["enrollements.csv"], "enrollements.csv")

    _require_columns(rooms_rows, "rooms.csv", ("room name", "capacity"))
    _require_columns(timeslot_rows, "timeslots.csv", ("timeslot",))
    _require_columns(exam_rows, "exams.csv", ("exam code", "exam name", "duration in minutes"))
    _require_columns(enrolment_rows, "enrollements.csv", ("student code", "exam code"))

    rooms = []
    seen_rooms = set()
    for row in rooms_rows:
        name = _pick(row, "room name")
        if not name or name in seen_rooms:
            continue
        try:
            capacity = int(float(_pick(row, "capacity", "0")))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid room capacity for {name}.")
        rooms.append({"name": name, "capacity": capacity})
        seen_rooms.add(name)

    timeslots = []
    seen_timeslots = set()
    for row in timeslot_rows:
        date = _pick(row, "timeslot")
        if date and date not in seen_timeslots:
            timeslots.append(date)
            seen_timeslots.add(date)

    course_order = []
    courses_map = {}
    for row in exam_rows:
        code = _pick(row, "exam code")
        if not code or code in courses_map:
            continue
        try:
            duration = int(float(_pick(row, "duration in minutes", "120")))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid duration for exam {code}.")
        courses_map[code] = {
            "code": code,
            "name": _pick(row, "exam name", code),
            "enrollment": 0,
            "duration_minutes": duration,
        }
        course_order.append(code)

    students_map: dict[str, set[str]] = {}
    enrolment_count = 0
    for row in enrolment_rows:
        student_id = _pick(row, "student code")
        exam_code = _pick(row, "exam code")
        if not student_id or not exam_code:
            continue
        if exam_code not in courses_map:
            courses_map[exam_code] = {
                "code": exam_code,
                "name": exam_code,
                "enrollment": 0,
                "duration_minutes": 120,
            }
            course_order.append(exam_code)
        students_map.setdefault(student_id, set()).add(exam_code)
        enrolment_count += 1

    for course_codes in students_map.values():
        for code in course_codes:
            courses_map[code]["enrollment"] += 1

    courses = [courses_map[code] for code in course_order]
    original_room_count = len(rooms)
    rooms, room_grouping = _ensure_rooms_can_host_exams(rooms, courses)
    students = [
        {"id": student_id, "courses": sorted(codes)}
        for student_id, codes in sorted(students_map.items())
    ]

    if not rooms:
        raise HTTPException(status_code=400, detail="rooms.csv did not contain any rooms.")
    if not timeslots:
        raise HTTPException(status_code=400, detail="timeslots.csv did not contain any timeslots.")
    if not courses:
        raise HTTPException(status_code=400, detail="exams.csv did not contain any exams.")

    return {
        "courses": courses,
        "students": students,
        "rooms": rooms,
        "timeslots": timeslots,
        "metadata": {
            "source": source_name,
            "exam_count": len(courses),
            "student_count": len(students),
            "room_count": len(rooms),
            "original_room_count": original_room_count,
            "timeslot_count": len(timeslots),
            "enrolment_rows": enrolment_count,
            "room_grouping": room_grouping,
        },
    }


def _ensure_rooms_can_host_exams(rooms: list[dict], courses: list[dict]) -> tuple[list[dict], str]:
    if not rooms or not courses:
        return rooms, "none"

    max_enrollment = max(course["enrollment"] for course in courses)
    max_capacity = max(room["capacity"] for room in rooms)
    total_capacity = sum(room["capacity"] for room in rooms)
    if max_enrollment <= max_capacity:
        return rooms, "none"
    if total_capacity < max_enrollment:
        return rooms, "insufficient-total-capacity"

    grouped_rooms = []
    current_group = []
    current_capacity = 0
    for room in rooms:
        current_group.append(room)
        current_capacity += room["capacity"]
        if current_capacity >= max_enrollment:
            grouped_rooms.append(_room_group(current_group))
            current_group = []
            current_capacity = 0

    if current_group and current_capacity >= max_enrollment:
        grouped_rooms.append(_room_group(current_group))

    return grouped_rooms or rooms, "virtual-room-groups"


def _room_group(rooms: list[dict]) -> dict:
    names = [room["name"] for room in rooms]
    return {
        "name": " + ".join(names),
        "capacity": sum(room["capacity"] for room in rooms),
    }


async def load_uploaded_dataset(files: list[UploadFile]) -> dict:
    text_by_name = {}
    for upload in files:
        filename = Path(upload.filename or "").name.lower()
        if filename not in REQUIRED_FILES:
            raise HTTPException(
                status_code=400,
                detail=f"Unexpected file {upload.filename}. Upload exactly: {', '.join(sorted(REQUIRED_FILES))}.",
            )
        content = await upload.read()
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = content.decode("latin-1")
        text_by_name[filename] = text
    return _parse_dataset(text_by_name, "Uploaded dataset")


def load_dataset_folder(folder: Path) -> dict:
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail=f"Dataset folder not found: {folder.name}")

    files = {}
    for filename in REQUIRED_FILES:
        path = folder / filename
        if not path.exists():
            raise HTTPException(status_code=400, detail=f"{folder.name} is missing {filename}.")
        files[filename] = path.read_text(encoding="utf-8-sig")
    return _parse_dataset(files, folder.name)


def list_benchmark_folders(root: Path) -> list[dict]:
    manifest_path = root / "manifest.csv"
    if manifest_path.exists():
        rows = list(csv.DictReader(io.StringIO(manifest_path.read_text(encoding="utf-8-sig"))))
        return [
            {
                "name": row["benchmark"],
                "folder": row["folder"].rstrip("/"),
                "rooms": int(row["rooms"]),
                "timeslots": int(row["timeslots"]),
                "exams": int(row["exams"]),
                "students": int(row["students"]),
                "enrolment_rows": int(row["enrolment_rows"]),
            }
            for row in rows
        ]

    return [
        {"name": path.name, "folder": path.name}
        for path in sorted(root.iterdir())
        if path.is_dir()
    ]
