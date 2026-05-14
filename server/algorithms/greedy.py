"""Greedy scheduler ported from the notebook and adapted to backend objects."""
from typing import Callable, Optional

from server.algorithms.common import can_place, conflict_degrees, fitness


class GreedyScheduler:
    """Schedule the most constrained exams first and commit to the best local slot."""

    def __init__(self, exam_students: list[set], room_timeslot: list[tuple], course_enrollments: list[int]):
        self.exam_students = exam_students
        self.room_timeslot = room_timeslot
        self.number_of_exams = len(exam_students)
        self.course_enrollments = course_enrollments
        self.conflict_degrees = conflict_degrees(exam_students)

    def run(self, progress_callback: Optional[Callable] = None):
        exam_order = sorted(
            range(self.number_of_exams),
            key=lambda i: (self.conflict_degrees[i], self.course_enrollments[i]),
            reverse=True,
        )
        assignment = [None] * self.number_of_exams

        for step, exam_idx in enumerate(exam_order):
            if progress_callback:
                pct = ((step + 1) / max(1, self.number_of_exams)) * 100
                progress_callback(pct, f"Greedy placing exam {step + 1}/{self.number_of_exams}")

            candidates = []
            for rt_idx, (room, timeslot) in enumerate(self.room_timeslot):
                if not can_place(exam_idx, rt_idx, assignment, self.exam_students, self.room_timeslot):
                    continue
                waste = room.capacity - len(self.exam_students[exam_idx])
                daily_stress = self._same_day_overlap_delta(exam_idx, timeslot, assignment)
                candidates.append((daily_stress, timeslot.day, timeslot.hour, timeslot.minute, timeslot.is_late, waste, rt_idx))

            if candidates:
                assignment[exam_idx] = min(candidates)[-1]

        return assignment, fitness(assignment, self.exam_students, self.room_timeslot)

    def _same_day_overlap_delta(self, exam_idx: int, timeslot, assignment: list) -> int:
        stress = 0
        students = self.exam_students[exam_idx]
        for other_exam, other_rt in enumerate(assignment):
            if other_rt is None:
                continue
            _, other_timeslot = self.room_timeslot[other_rt]
            if other_timeslot.day == timeslot.day:
                stress += len(students & self.exam_students[other_exam])
        return stress
