"""
A* Search algorithm for exam scheduling.
Placeholder implementation — uses a priority queue over partial assignments
with a heuristic based on remaining exams × conflict density.
Includes integrated progress reporting.
"""
import heapq
import time
from typing import Callable, Optional


class AStarScheduler:
    """A* search over partial exam schedules."""

    def __init__(self, exam_students: list[set], room_timeslot: list[tuple], course_enrollments: list[int]):
        self.exam_students = exam_students
        self.room_timeslot = room_timeslot
        self.number_of_exams = len(exam_students)
        self.course_enrollments = course_enrollments

        # Precompute conflict density: how many other exams each exam conflicts with
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

        # Sort exams by conflict degree (descending) — most constrained first
        exam_order = sorted(
            range(self.number_of_exams),
            key=lambda i: (self.conflict_degrees[i], self.course_enrollments[i]),
            reverse=True,
        )

        # State: (f_cost, g_cost, assignment_tuple, depth)
        # g_cost = number of exams assigned so far (negative for min-heap)
        # h_cost = estimated remaining cost
        initial_assignment = tuple([None] * self.number_of_exams)
        h = self._heuristic(initial_assignment, 0)
        # Use negative g so that deeper states are preferred at same f
        heapq.heappush(open_set := [], (h, 0, nodes_explored, initial_assignment, 0))

        while open_set:
            now = time.perf_counter()
            if now >= deadline:
                break

            nodes_explored += 1

            # Progress update
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
                # Complete assignment — evaluate
                assignment = list(assignment_tuple)
                fitness = self._compute_fitness(assignment)
                if fitness > best_fitness:
                    best_fitness = fitness
                    best_assignment = assignment
                continue

            # Pick next exam to assign
            exam_idx = exam_order[depth]
            assignment_list = list(assignment_tuple)

            # Find used room_timeslot indices
            used = set(a for a in assignment_list if a is not None)

            # Try each possible slot, ordered by fit quality
            candidates = []
            for rt_idx, (room, timeslot) in enumerate(self.room_timeslot):
                if rt_idx in used:
                    continue
                if room.capacity < len(self.exam_students[exam_idx]):
                    continue

                # Check student conflicts
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

            # Sort candidates by cost (prefer tight fit, non-late)
            candidates.sort()

            # Limit branching to keep it tractable
            for cost, rt_idx in candidates[:8]:
                new_assignment = list(assignment_list)
                new_assignment[exam_idx] = rt_idx
                new_tuple = tuple(new_assignment)

                g = depth + 1
                h = self._heuristic(new_tuple, g)
                f = -g + h  # prefer deeper assignments

                heapq.heappush(open_set, (f, -g, nodes_explored, new_tuple, g))

        elapsed = time.perf_counter() - start

        if progress_callback:
            progress_callback(100, f"Done — explored {nodes_explored} states in {elapsed:.2f}s")

        if best_assignment is None:
            # Fallback: return whatever partial we have
            best_fitness = 0.0

        return best_assignment, best_fitness, nodes_explored, elapsed

    def _heuristic(self, assignment: tuple, depth: int) -> float:
        """Estimate remaining cost: unassigned exams × average conflict density."""
        remaining = self.number_of_exams - depth
        if remaining == 0:
            return 0
        avg_density = sum(self.conflict_degrees) / self.number_of_exams if self.number_of_exams > 0 else 0
        return remaining * avg_density * 0.1

    def _compute_fitness(self, assignment: list) -> float:
        """Compute fitness matching the GA/CSP formula."""
        assigned_count = sum(1 for a in assignment if a is not None)
        if assigned_count == 0:
            return 0.0

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
