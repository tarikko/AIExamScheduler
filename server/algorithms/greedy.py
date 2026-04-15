"""
Greedy Search algorithm for exam scheduling.
Placeholder implementation — assigns exams by largest enrollment first
to the first available non-conflicting (room, timeslot) pair.
Includes integrated progress reporting.
"""
from typing import Callable, Optional


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
        # Sort exams by enrollment (descending) — largest first
        exam_order = sorted(
            range(self.number_of_exams),
            key=lambda i: self.course_enrollments[i],
            reverse=True,
        )

        assignment = [None] * self.number_of_exams
        used_slots = set()  # track used (room_timeslot index) to avoid duplicates

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

                # Hard: room capacity check
                if room.capacity < len(students):
                    continue

                # Hard: no student overlap at same timeslot
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

                # Prefer tighter room fit and non-late slots
                waste = room.capacity - len(students)
                if timeslot.is_late:
                    waste += 1000  # penalize late slots

                if waste < best_waste:
                    best_waste = waste
                    best_slot = rt_idx

            if best_slot is not None:
                assignment[exam_idx] = best_slot
                used_slots.add(best_slot)

        # Compute a simple fitness
        fitness = self._compute_fitness(assignment)
        return assignment, fitness

    def _compute_fitness(self, assignment: list) -> float:
        """Compute fitness matching the GA/CSP formula."""
        # Check for any unassigned
        assigned_count = sum(1 for a in assignment if a is not None)
        if assigned_count == 0:
            return 0.0

        # Only evaluate assigned exams
        consecutive_exams_penalty = 0
        total_mutual_students = 0
        for i in range(self.number_of_exams):
            if assignment[i] is None:
                continue
            for j in range(i + 1, self.number_of_exams):
                if assignment[j] is None:
                    continue
                overlap = len(self.exam_students[i] & self.exam_students[j])
                total_mutual_students += overlap
                if self.room_timeslot[assignment[i]][1].day == self.room_timeslot[assignment[j]][1].day:
                    consecutive_exams_penalty += overlap

        late_exams = 0
        total_exams = assigned_count
        efficient_allocation_factor = 0

        for i in range(self.number_of_exams):
            if assignment[i] is None:
                continue
            if self.room_timeslot[assignment[i]][1].is_late:
                late_exams += 1
            n = len(self.exam_students[i])
            c = self.room_timeslot[assignment[i]][0].capacity
            if c > 0:
                efficient_allocation_factor += -4 * n * (n - c) / (c ** 2)

        if total_exams == 0:
            return 0.0

        if total_mutual_students == 0:
            penalty_factor = 1 + late_exams / total_exams
        else:
            penalty_factor = 1 + late_exams / total_exams + 2 * (consecutive_exams_penalty / total_mutual_students)

        fitness_value = (efficient_allocation_factor / total_exams) / penalty_factor
        return fitness_value
