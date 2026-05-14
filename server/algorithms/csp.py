"""CSP solver ported from the notebook with backend progress reporting."""
import time
from typing import Callable, Optional

from server.algorithms.common import fitness, greedy_assignment


class CSP:
    """Backtracking CSP with MRV, forward checking, and a time limit."""

    def __init__(self, exam_students: list[set], room_timeslot: list[tuple]):
        self.number_of_exams = len(exam_students)
        self.exam_students = exam_students
        self.room_timeslot = room_timeslot
        self.domain = {i: set(range(len(self.room_timeslot))) for i in range(self.number_of_exams)}

    def binary_hard_constraint(self, e1: int, e2: int, v1: int, v2: int) -> bool:
        if v1 == v2:
            return False
        same_students = not self.exam_students[e1].isdisjoint(self.exam_students[e2])
        same_timeslot = self.room_timeslot[v1][1] == self.room_timeslot[v2][1]
        return not (same_students and same_timeslot)

    def unary_hard_constraint(self, e1: int, v1: int) -> bool:
        return len(self.exam_students[e1]) <= self.room_timeslot[v1][0].capacity

    def run(self, time_limit_sec: float = 5.0, progress_callback: Optional[Callable] = None):
        start = time.perf_counter()
        deadline = start + time_limit_sec
        nodes_explored = 0
        last_progress_time = start

        fallback = greedy_assignment(self.exam_students, self.room_timeslot)
        best_assignment = fallback
        best_fitness = fitness(fallback, self.exam_students, self.room_timeslot)

        def solve(assignment: list, not_assigned: set, domains: dict):
            nonlocal nodes_explored, best_assignment, best_fitness, last_progress_time
            now = time.perf_counter()
            if now >= deadline:
                return
            nodes_explored += 1

            if progress_callback and now - last_progress_time >= 0.2:
                pct = min(95.0, ((now - start) / max(time_limit_sec, 0.01)) * 100)
                progress_callback(pct, f"CSP explored {nodes_explored} nodes")
                last_progress_time = now

            if not not_assigned:
                score = fitness(assignment, self.exam_students, self.room_timeslot)
                if score > best_fitness:
                    best_assignment = assignment.copy()
                    best_fitness = score
                return

            current = min(not_assigned, key=lambda i: len(domains[i]))
            not_assigned.remove(current)
            values = sorted(
                domains[current],
                key=lambda v: (
                    self.room_timeslot[v][1].is_late,
                    self.room_timeslot[v][1].day,
                    self.room_timeslot[v][1].hour,
                    abs(self.room_timeslot[v][0].capacity - len(self.exam_students[current])),
                ),
            )

            for possible_value in values:
                if time.perf_counter() >= deadline:
                    break
                if not self.unary_hard_constraint(current, possible_value):
                    continue

                next_domains = {k: s.copy() for k, s in domains.items()}
                invalid = False
                for exam in not_assigned:
                    next_domains[exam] = {
                        value
                        for value in next_domains[exam]
                        if self.binary_hard_constraint(current, exam, possible_value, value)
                    }
                    if not next_domains[exam]:
                        invalid = True
                        break
                if invalid:
                    continue

                assignment[current] = possible_value
                solve(assignment, not_assigned, next_domains)
                assignment[current] = None

            not_assigned.add(current)

        solve(
            assignment=[None for _ in range(self.number_of_exams)],
            not_assigned=set(range(self.number_of_exams)),
            domains=self.domain,
        )

        elapsed = time.perf_counter() - start
        if progress_callback:
            progress_callback(100, f"CSP done after {nodes_explored} nodes in {elapsed:.2f}s")
        return best_assignment, best_fitness, nodes_explored, elapsed
