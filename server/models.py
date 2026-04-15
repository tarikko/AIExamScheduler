"""
Pydantic models and internal data classes for the exam scheduler.
"""
from pydantic import BaseModel


# ─── Internal domain objects (used by algorithms) ─────────────────────────────

class Room:
    """A physical room with a name and seating capacity."""
    def __init__(self, name: str, capacity: int):
        self.name = name
        self.capacity = capacity

    def to_dict(self):
        return {"name": self.name, "capacity": self.capacity}


class Timeslot:
    """
    A time slot parsed from a date string in the format "YYYY-MM-DD HH:MM".
    """
    def __init__(self, date: str):
        self.date = date
        data = date.split(' ')
        time_parts = data[1].split(':')
        date_parts = data[0].split('-')

        self.hour, self.minute = int(time_parts[0]), int(time_parts[1])
        self.year, self.month, self.day = int(date_parts[0]), int(date_parts[1]), int(date_parts[2])
        self.is_late = self.hour >= 17

    def __eq__(self, value):
        return self.date == value.date

    def __hash__(self):
        return hash(self.date)

    def to_dict(self):
        return {"date": self.date, "is_late": self.is_late}


# ─── API request / response schemas ──────────────────────────────────────────

class RoomSchema(BaseModel):
    name: str
    capacity: int


class CourseSchema(BaseModel):
    code: str
    name: str
    enrollment: int


class StudentSchema(BaseModel):
    id: str
    courses: list[str]


class TimeslotSchema(BaseModel):
    date: str


class ScheduleRequest(BaseModel):
    """Payload sent by the frontend to run an algorithm."""
    courses: list[CourseSchema]
    students: list[StudentSchema]
    rooms: list[RoomSchema]
    timeslots: list[TimeslotSchema]
    # Algorithm-specific parameters
    generations: int = 300
    population_size: int = 350
    mutation_probability: float = 0.08
    time_limit_sec: float = 5.0


class AssignmentResult(BaseModel):
    exam_index: int
    course_code: str
    course_name: str
    enrollment: int
    room_name: str
    room_capacity: int
    timeslot_date: str
    is_late: bool


class ScheduleResponse(BaseModel):
    assignments: list[AssignmentResult]
    fitness: float
    elapsed_seconds: float
    algorithm: str
