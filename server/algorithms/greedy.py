"""
Greedy Search algorithm for exam scheduling.
Assigns exams by largest enrollment first to the first available
non-conflicting (room, timeslot) pair.
Includes integrated progress reporting.
"""
from typing import Callable, Optional

from server.algorithms.fitness import compute_fitness


class GreedyScheduler:
    """Greedy scheduler using Largest Enrollment + Degree heuristic."""

    def __init__(self, exam_students: list[set], room_timeslot: list[tuple], course_enrollments: list[int]):
        self.exam_students = exam_students
        self.room_timeslot = room_timeslot
        self.number_of_exams = len(exam_students)
        self.course_enrollments = course_enrollments

    def run(self, progress_callback: Optional[Callable] = None):
        """
        Run the greedy assignment.

        Returns:
            assignment: list of room_timeslot indices (one per exam), or None for unassigned.
            fitness: float score of the solution.
        """
        exam_order = sorted(
            range(self.number_of_exams),
            key=lambda i: self.course_enrollments[i],
            reverse=True,
        )

        assignment = [None] * self.number_of_exams
        used_slots = set()

        for step, exam_idx in enumerate(exam_order):
            if progress_callback and (step % 2 == 0 or step == self.number_of_exams - 1):
                pct = ((step + 1) / self.number_of_exams) * 100
                progress_callback(pct, f"Assigning exam {step + 1}/{self.number_of_exams}")

            students = self.exam_students[exam_idx]
            best_slot = None
            best_waste = float('inf')

            for rt_idx, (room, timeslot) in enumerate(self.room_timeslot):
                if rt_idx in used_slots:
                    continue

                if room.capacity < len(students):
                    continue

                conflict = False
                for other_exam in range(self.number_of_exams):
                    if assignment[other_exam] is None:
                        continue
                    other_room, other_ts = self.room_timeslot[assignment[other_exam]]
                    if other_ts == timeslot:
                        if len(students & self.exam_students[other_exam]) > 0:
                            conflict = True
                            break
                if conflict:
                    continue

                waste = room.capacity - len(students)
                if timeslot.is_late:
                    waste += 1000

                if waste < best_waste:
                    best_waste = waste
                    best_slot = rt_idx

            if best_slot is not None:
                assignment[exam_idx] = best_slot
                used_slots.add(best_slot)

        fitness = compute_fitness(assignment, self.exam_students, self.room_timeslot)
        return assignment, fitness
