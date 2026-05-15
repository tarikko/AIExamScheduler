"""
Pydantic models and internal data classes for the exam scheduler.
"""
from datetime import datetime, timezone, timedelta
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
    def __init__(self,date: str):
        '''
        format of the date string must be "YYYY-MM-DD HH:MM"
        '''
        self.date = date

        data = date.split(' ')
        a = data[1].split(':')
        b = data[0].split('-')
        self.calendar_date = data[0] # date without the hours and minutes
        self.hour, self.minute = int(a[0]) , int(a[1])
        self.year, self.month, self.day = int(b[0]), int(b[1]), int(b[2])

        self.is_late = self.hour >= 17

    def to_epoch(self, tzinfo=timezone.utc):
        '''
        returns the representation of the time in epochs in seconds
        '''
        dt = datetime(self.year, self.month, self.day, self.hour, self.minute, tzinfo=tzinfo)
        return int(dt.timestamp())


    def add_time(self, years=0, months=0, days=0, hours=0, minutes=0, seconds=0, tzinfo=timezone.utc):
        '''
        Generic method that takes a duration in years,months,days,hours,minutes and seconds 
        converts them to epoch and adds them to the epoch representation of the Timeslot instance
        and returns the result of the addition in epochs (seconds)
        '''
        base = datetime(self.year, self.month, self.day, self.hour, self.minute, tzinfo=tzinfo)
        total_months = (base.year * 12 + (base.month - 1)) + int(years) * 12 + int(months)
        target_year = total_months // 12
        target_month = total_months % 12 + 1
        target_day = min(base.day, self._days_in_month(target_year, target_month))
        shifted = base.replace(year=target_year, month=target_month, day=target_day)
        shifted += timedelta(days=int(days), hours=int(hours), minutes=int(minutes), seconds=int(seconds))
        return int(shifted.timestamp())

    @staticmethod
    def _days_in_month(year, month):
        if month == 12:
            next_month = datetime(year + 1, 1, 1)
        else:
            next_month = datetime(year, month + 1, 1)
        return (next_month - timedelta(days=1)).day

    def __eq__(self, value):
        return self.date == value.date

    def __hash__(self):
        return hash(self.date)

    def to_dict(self):
        return {"date": self.date, "is_late": self.is_late}
    

class Exam:
    def __init__(self,exam_code: str|int,exam_name: str = None,students: set = None,exam_duration: int = None):
        '''
        enrollements is dict with keys = student codes & values = exam codes
        exa_duration must be an int in minutes
        '''
        self.code = exam_code
        self.name = exam_name
        self.duration = exam_duration
        self.students = students # set of student codes who are concerned with this exam

# this class maybe used for the demo visualization
class Student:
    def __init__(self,student_code,exams: list = None):
        '''
        exams is a list containing exam codes that this particular student is taking
        '''
        self.code = student_code
        self.exams = exams


# ─── API request / response schemas ──────────────────────────────────────────

class RoomSchema(BaseModel):
    name: str
    capacity: int


class CourseSchema(BaseModel):
    code: str
    name: str
    enrollment: int
    duration_minutes: int = 120


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
    time_limit_sec: float | None = None
    first_find: bool = False


class AlgorithmSettings(BaseModel):
    """Optional algorithm settings for benchmark runs."""
    generations: int | None = None
    population_size: int | None = None
    mutation_probability: float | None = None
    time_limit_sec: float | None = None
    first_find: bool | None = None


class AssignmentResult(BaseModel):
    exam_index: int
    course_code: str
    course_name: str
    enrollment: int
    duration_minutes: int
    room_name: str
    room_capacity: int
    timeslot_date: str
    is_late: bool


class ScheduleResponse(BaseModel):
    assignments: list[AssignmentResult]
    fitness: float
    elapsed_seconds: float
    algorithm: str
    metrics: dict = {}
