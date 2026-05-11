"""
A* Search algorithm for exam scheduling.
Uses a priority queue over partial assignments with a heuristic
based on remaining exams x conflict density.
Includes integrated progress reporting.
"""
import heapq
import time
from typing import Callable, Optional

from server.algorithms.fitness import compute_fitness


class AStarScheduler:
    """A* search over partial exam schedules."""

    def __init__(self, exam_students: list[set], room_timeslot: list[tuple], course_enrollments: list[int]):
        self.exam_students = exam_students
        self.room_timeslot = room_timeslot
        self.number_of_exams = len(exam_students)
        self.course_enrollments = course_enrollments

        self.conflict_degrees = []
        for i in range(self.number_of_exams):
            degree = 0
            for j in range(self.number_of_exams):
                if i != j and len(exam_students[i] & exam_students[j]) > 0:
                    degree += 1
            self.conflict_degrees.append(degree)

    def run(self, time_limit_sec: float = 5.0, progress_callback: Optional[Callable] = None):
        """
        Run A* search with time limit.

        Returns:
            assignment: list of room_timeslot indices, or None for unassigned.
            fitness: float score.
            nodes_explored: int.
            elapsed: float seconds.
        """
        start = time.perf_counter()
        deadline = start + time_limit_sec
        nodes_explored = 0
        last_progress_time = start

        best_assignment = None
        best_fitness = float('-inf')

        exam_order = sorted(
            range(self.number_of_exams),
            key=lambda i: (self.conflict_degrees[i], self.course_enrollments[i]),
            reverse=True,
        )

        initial_assignment = tuple([None] * self.number_of_exams)
        h = self._heuristic(initial_assignment, 0)
        heapq.heappush(open_set := [], (h, 0, nodes_explored, initial_assignment, 0))

        while open_set:
            now = time.perf_counter()
            if now >= deadline:
                break

            nodes_explored += 1

            if progress_callback and (now - last_progress_time) >= 0.25:
                elapsed = now - start
                pct = min(95.0, (elapsed / time_limit_sec) * 100)
                msg = f"Explored {nodes_explored} states"
                if best_assignment is not None:
                    msg += f" — best fitness: {best_fitness:.4f}"
                progress_callback(pct, msg)
                last_progress_time = now

            f, neg_g, _, assignment_tuple, depth = heapq.heappop(open_set)

            if depth == self.number_of_exams:
                assignment = list(assignment_tuple)
                fitness = compute_fitness(assignment, self.exam_students, self.room_timeslot)
                if fitness > best_fitness:
                    best_fitness = fitness
                    best_assignment = assignment
                continue

            exam_idx = exam_order[depth]
            assignment_list = list(assignment_tuple)

            used = set(a for a in assignment_list if a is not None)

            candidates = []
            for rt_idx, (room, timeslot) in enumerate(self.room_timeslot):
                if rt_idx in used:
                    continue
                if room.capacity < len(self.exam_students[exam_idx]):
                    continue

                conflict = False
                for prev_depth in range(depth):
                    prev_exam = exam_order[prev_depth]
                    prev_rt = assignment_list[prev_exam]
                    if prev_rt is not None:
                        _, prev_ts = self.room_timeslot[prev_rt]
                        if prev_ts == timeslot:
                            if len(self.exam_students[exam_idx] & self.exam_students[prev_exam]) > 0:
                                conflict = True
                                break
                if conflict:
                    continue

                waste = room.capacity - len(self.exam_students[exam_idx])
                late_cost = 10 if timeslot.is_late else 0
                candidates.append((waste + late_cost, rt_idx))

            candidates.sort()

            for cost, rt_idx in candidates[:8]:
                new_assignment = list(assignment_list)
                new_assignment[exam_idx] = rt_idx
                new_tuple = tuple(new_assignment)

                g = depth + 1
                h = self._heuristic(new_tuple, g)
                f = -g + h

                heapq.heappush(open_set, (f, -g, nodes_explored, new_tuple, g))

        elapsed = time.perf_counter() - start

        if progress_callback:
            progress_callback(100, f"Done — explored {nodes_explored} states in {elapsed:.2f}s")

        if best_assignment is None:
            best_fitness = 0.0

        return best_assignment, best_fitness, nodes_explored, elapsed

    def _heuristic(self, assignment: tuple, depth: int) -> float:
        remaining = self.number_of_exams - depth
        if remaining == 0:
            return 0
        avg_density = sum(self.conflict_degrees) / self.number_of_exams if self.number_of_exams > 0 else 0
        return remaining * avg_density * 0.1
