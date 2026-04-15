"""
Constraint Satisfaction Problem (CSP) solver for exam scheduling.
Ported from notebook/algorithms.ipynb with integrated progress reporting.
Uses MRV heuristic + forward checking with backtracking.
"""
import time
from typing import Callable, Optional


class CSP:
    """CSP solver with MRV + forward checking."""

    def __init__(self, exam_students: list[set], room_timeslot: list[tuple]):
        self.exam = [None for _ in range(len(exam_students))]
        self.number_of_exams = len(exam_students)
        self.exam_students = exam_students
        self.room_timeslot = room_timeslot
        self.domain = {i: set(range(len(self.room_timeslot))) for i in range(self.number_of_exams)}

    def binary_hard_constraint(self, e1: int, e2: int, v1: int, v2: int) -> bool:
        # No two exams can have the same (room, timeslot)
        if v1 == v2:
            return False
        # No student can sit for two different exams at the same time
        if len(self.exam_students[e1] & self.exam_students[e2]) > 0 and self.room_timeslot[v1][1] == self.room_timeslot[v2][1]:
            return False
        return True

    def unary_hard_constraint(self, e1: int, v1: int) -> bool:
        # Room capacity must exceed number of students
        if len(self.exam_students[e1]) > self.room_timeslot[v1][0].capacity:
            return False
        return True

    def _solution_fitness(self, schedule: list) -> float:
        """Compute fitness for a complete assignment."""
        consecutive_exams_penalty = 0
        total_mutual_students = 0
        for i in range(self.number_of_exams):
            for j in range(i + 1, self.number_of_exams):
                overlap = len(self.exam_students[i] & self.exam_students[j])
                total_mutual_students += overlap
                if self.room_timeslot[schedule[i]][1].day == self.room_timeslot[schedule[j]][1].day:
                    consecutive_exams_penalty += overlap

        late_exams = 0
        total_exams = self.number_of_exams
        for i in range(self.number_of_exams):
            if self.room_timeslot[schedule[i]][1].is_late:
                late_exams += 1

        efficient_allocation_factor = 0
        for i in range(self.number_of_exams):
            n = len(self.exam_students[i])
            c = self.room_timeslot[schedule[i]][0].capacity
            efficient_allocation_factor += -4 * n * (n - c) / (c ** 2)

        if total_mutual_students == 0:
            penalty_factor = 1 + late_exams / total_exams
        else:
            penalty_factor = 1 + late_exams / total_exams + 2 * (consecutive_exams_penalty / total_mutual_students)

        fitness_value = (efficient_allocation_factor / total_exams) / penalty_factor
        return fitness_value

    def run(self, time_limit_sec: float = 5.0, progress_callback: Optional[Callable] = None):
        """
        Run the CSP solver with time-limited backtracking.
        
        Args:
            time_limit_sec: Maximum number of seconds to search.
            progress_callback: Optional callback(percent, message) for progress updates.
        """
        start = time.perf_counter()
        deadline = start + time_limit_sec
        nodes_explored = 0

        best_assignment = None
        best_fitness = float('-inf')

        last_progress_time = start

        def solve(assignment: list, not_assigned: set, domains: dict):
            nonlocal nodes_explored, best_assignment, best_fitness, last_progress_time

            now = time.perf_counter()
            if now >= deadline:
                return

            nodes_explored += 1

            # Report progress based on elapsed time fraction
            if progress_callback and (now - last_progress_time) >= 0.2:
                elapsed = now - start
                pct = min(95.0, (elapsed / time_limit_sec) * 100)
                msg = f"Explored {nodes_explored} nodes"
                if best_assignment is not None:
                    msg += f" — best fitness: {best_fitness:.4f}"
                progress_callback(pct, msg)
                last_progress_time = now

            if len(not_assigned) == 0:
                sol_fitness = self._solution_fitness(assignment)
                if sol_fitness > best_fitness:
                    best_fitness = sol_fitness
                    best_assignment = assignment.copy()
                return

            # Minimum Remaining Values (MRV)
            curr = min(not_assigned, key=lambda i: len(domains[i]))
            not_assigned.remove(curr)

            # Value ordering: prefer non-late slots and tighter capacity fit
            values = sorted(
                domains[curr],
                key=lambda v: (
                    self.room_timeslot[v][1].is_late,
                    abs(self.room_timeslot[v][0].capacity - len(self.exam_students[curr]))
                )
            )

            for possible_value in values:
                if time.perf_counter() >= deadline:
                    break

                if not self.unary_hard_constraint(curr, possible_value):
                    continue

                new_domain = {k: s.copy() for k, s in domains.items()}

                invalid_possible_value = False
                for e in not_assigned:
                    to_remove = set()
                    for v in new_domain[e]:
                        if not self.binary_hard_constraint(curr, e, possible_value, v):
                            to_remove.add(v)
                    if to_remove:
                        new_domain[e] -= to_remove
                    if len(new_domain[e]) == 0:
                        invalid_possible_value = True
                        break

                if invalid_possible_value:
                    continue

                assignment[curr] = possible_value
                solve(assignment, not_assigned, new_domain)
                assignment[curr] = None

            not_assigned.add(curr)

        init_not_assigned = set(range(self.number_of_exams))
        init_assignment = [None for _ in range(self.number_of_exams)]
        solve(assignment=init_assignment, not_assigned=init_not_assigned, domains=self.domain)

        if best_assignment is not None:
            self.exam = best_assignment

        elapsed = time.perf_counter() - start

        if progress_callback:
            progress_callback(100, f"Done — explored {nodes_explored} nodes in {elapsed:.2f}s")

        return (self.exam if best_assignment is not None else None), best_fitness, nodes_explored, elapsed
