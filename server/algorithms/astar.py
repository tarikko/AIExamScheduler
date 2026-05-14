"""A* scheduler adapted from the notebook implementation."""
import heapq
import itertools
import time
from typing import Callable, Optional

from server.algorithms.common import can_place, conflict_degrees, fitness, greedy_assignment


class AStarScheduler:
    """A time-limited A* search over partial exam assignments."""

    def __init__(self, exam_students: list[set], room_timeslot: list[tuple], course_enrollments: list[int]):
        self.exam_students = exam_students
        self.room_timeslot = room_timeslot
        self.number_of_exams = len(exam_students)
        self.course_enrollments = course_enrollments
        self.conflict_degrees = conflict_degrees(exam_students)

    def run(self, time_limit_sec: float = 5.0, progress_callback: Optional[Callable] = None):
        start = time.perf_counter()
        deadline = start + time_limit_sec
        nodes_explored = 0
        last_progress_time = start

        exam_order = sorted(
            range(self.number_of_exams),
            key=lambda i: (self.conflict_degrees[i], self.course_enrollments[i]),
            reverse=True,
        )
        fallback = greedy_assignment(self.exam_students, self.room_timeslot, self.course_enrollments)
        best_assignment = fallback
        best_fitness = fitness(fallback, self.exam_students, self.room_timeslot)

        counter = itertools.count()
        initial = tuple([None] * self.number_of_exams)
        open_set = [(self._heuristic(0), next(counter), 0, initial)]
        visited = set()

        while open_set and time.perf_counter() < deadline:
            _, _, depth, assignment_tuple = heapq.heappop(open_set)
            state_key = (depth, assignment_tuple)
            if state_key in visited:
                continue
            visited.add(state_key)
            nodes_explored += 1

            now = time.perf_counter()
            if progress_callback and now - last_progress_time >= 0.25:
                pct = min(95.0, ((now - start) / max(time_limit_sec, 0.01)) * 100)
                progress_callback(pct, f"A* explored {nodes_explored} states")
                last_progress_time = now

            if depth == self.number_of_exams:
                assignment = list(assignment_tuple)
                score = fitness(assignment, self.exam_students, self.room_timeslot)
                if score > best_fitness:
                    best_assignment = assignment
                    best_fitness = score
                continue

            exam_idx = exam_order[depth]
            assignment = list(assignment_tuple)
            candidates = self._candidate_slots(exam_idx, assignment)[:12]
            for slot_cost, rt_idx in candidates:
                next_assignment = assignment.copy()
                next_assignment[exam_idx] = rt_idx
                g_cost = self._soft_cost(next_assignment)
                f_cost = g_cost + slot_cost + self._heuristic(depth + 1)
                heapq.heappush(open_set, (f_cost, next(counter), depth + 1, tuple(next_assignment)))

        elapsed = time.perf_counter() - start
        if progress_callback:
            progress_callback(100, f"A* done after {nodes_explored} states in {elapsed:.2f}s")
        return best_assignment, best_fitness, nodes_explored, elapsed

    def _candidate_slots(self, exam_idx: int, assignment: list) -> list[tuple]:
        candidates = []
        for rt_idx, (room, timeslot) in enumerate(self.room_timeslot):
            if not can_place(exam_idx, rt_idx, assignment, self.exam_students, self.room_timeslot):
                continue
            waste = room.capacity - len(self.exam_students[exam_idx])
            late = 25 if timeslot.is_late else 0
            stress = 0
            for other_exam, other_rt in enumerate(assignment):
                if other_rt is None:
                    continue
                _, other_timeslot = self.room_timeslot[other_rt]
                if other_timeslot.day == timeslot.day:
                    stress += len(self.exam_students[exam_idx] & self.exam_students[other_exam])
            candidates.append((stress * 10 + late + waste / max(room.capacity, 1), rt_idx))
        candidates.sort()
        return candidates

    def _heuristic(self, depth: int) -> float:
        remaining = max(0, self.number_of_exams - depth)
        avg_degree = sum(self.conflict_degrees) / self.number_of_exams if self.number_of_exams else 0
        return remaining * avg_degree * 0.05

    def _soft_cost(self, assignment: list) -> float:
        return max(0.0, 1.0 - fitness(assignment, self.exam_students, self.room_timeslot))
