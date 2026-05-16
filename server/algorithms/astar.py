"""
A* scheduler — architecture mirrors the CSP solver exactly.

Domain model  (same as CSP/GA):
  - room_timeslot : pre-built list of (Room, Timeslot) pairs from CSV
  - Each exam is assigned ONE index into that list (one room, one timeslot)
  - Capacity check   : room.capacity >= len(exam.students)  (unary, same as CSP)
  - Conflict check   : epoch-based time-overlap + shared students (same as CSP binary_hard_constraint)
  - Room clash check : same room at overlapping times (same as CSP)

A* specifics (ported from notebook AstarSearch logic):
  - g(n) : uses CSP's solution_evaluation() — same weighted penalty system
  - h(n) : Σ(1 / |domain[exam]|) for remaining exams; returns inf on dead-end
  - Visited states keyed on frozenset of (exam_idx, rt_idx) for placed exams
  - Greedy fallback so we always return something even when time expires
"""

import heapq
import time
from copy import deepcopy
from typing import Callable, Optional

from server.models import Exam, Room, Timeslot
from server.algorithms.utils import room_utilization_score
from server.algorithms.common import greedy_assignment


class AStarScheduler:
    """
    A* search for exam scheduling.

    Constructor args:
        exams         – list of server.models.Exam objects
        room_timeslot – list of (Room, Timeslot) pairs (the pre-built CSV domain)
    """

    def __init__(self, exams: list, room_timeslot: list[tuple]):
        self.exams = exams
        self.room_timeslot = room_timeslot
        self.number_of_exams = len(exams)
        n = self.number_of_exams

        # Conflict graph — same as CSP
        self.exam_neighbours = [[] for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                m = len(self.exams[i].students & self.exams[j].students)
                if m > 0:
                    self.exam_neighbours[i].append((j, m))

        self.exam_overlap = [
            [len(self.exams[i].students & self.exams[j].students) for j in range(n)]
            for i in range(n)
        ]

        # Epoch-based start/end times — same as CSP
        self.start_time = [slot.to_epoch() for _, slot in self.room_timeslot]
        self.end_time = [
            [slot.add_time(minutes=exam.duration) for _, slot in self.room_timeslot]
            for exam in self.exams
        ]

        # Initial domain: all rt indices, then prune by capacity (node consistency)
        self.domain = {i: set(range(len(self.room_timeslot))) for i in range(n)}
        for e in range(n):
            self.domain[e] = {
                v for v in self.domain[e]
                if self._unary_ok(e, v)
            }

    # ------------------------------------------------------------------
    # Constraint helpers  (identical logic to CSP)
    # ------------------------------------------------------------------

    def _unary_ok(self, e: int, v: int) -> bool:
        """Room capacity must fit all students — same as CSP unary_hard_constraint."""
        return self.room_timeslot[v][0].capacity >= len(self.exams[e].students)

    def _binary_ok(self, e1: int, e2: int, v1: int, v2: int) -> bool:
        """
        Same room or overlapping students at the same time = conflict.
        Mirrors CSP binary_hard_constraint exactly.
        """
        if v1 == v2:
            return False
        has_shared = self.exam_overlap[e1][e2] > 0
        s1, s2 = self.start_time[v1], self.start_time[v2]
        e1_end, e2_end = self.end_time[e1][v1], self.end_time[e2][v2]
        time_overlap = not (s1 > e2_end or s2 > e1_end)
        room_clash = time_overlap and (self.room_timeslot[v1][0] == self.room_timeslot[v2][0])
        if (has_shared and time_overlap) or room_clash:
            return False
        return True

    # ------------------------------------------------------------------
    # Scoring  (reuse CSP's weighted evaluation — same weights)
    # ------------------------------------------------------------------

    def _solution_evaluation(self, schedule: list) -> float:
        """
        Weighted fitness score — identical to CSP.solution_evaluation().
        Higher is better.
        """
        hard_dup_w      = 20.0
        hard_std_w      = 10.0
        hard_room_w     = 10.0
        soft_consec_w   = 3.0
        soft_late_w     = 0.5
        soft_alloc_w    = 2.0

        duplicate_pairs = 0
        student_conflicts = 0
        room_conflicts = 0
        consecutive_exams = 0
        late_exams = 0
        alloc_score = 0.0

        days = [0] * self.number_of_exams
        is_late = [False] * self.number_of_exams
        used: set = set()
        room_assignments: dict = {}

        for i in range(self.number_of_exams):
            v = schedule[i]
            if v is None:
                continue
            if v in used:
                duplicate_pairs += 1
            else:
                used.add(v)
            room, slot = self.room_timeslot[v]
            room_assignments.setdefault(room, []).append(
                (self.start_time[v], self.end_time[i][v])
            )
            days[i] = slot.day
            is_late[i] = slot.is_late
            alloc_score += room_utilization_score(room.capacity, len(self.exams[i].students))
            if slot.is_late:
                late_exams += 1

        for i in range(self.number_of_exams):
            if schedule[i] is None:
                continue
            for j, overlap in self.exam_neighbours[i]:
                if schedule[j] is None:
                    continue
                s_i, s_j = self.start_time[schedule[i]], self.start_time[schedule[j]]
                e_i, e_j = self.end_time[i][schedule[i]], self.end_time[j][schedule[j]]
                if max(s_i, s_j) < min(e_i, e_j):
                    student_conflicts += overlap
                if days[i] == days[j]:
                    consecutive_exams += overlap

        for assignments in room_assignments.values():
            assignments.sort(key=lambda x: x[0])
            active_end = -1
            for start, end in assignments:
                if start < active_end:
                    room_conflicts += 1
                else:
                    active_end = end
                if end > active_end:
                    active_end = end

        unassigned_penalty = sum(1 for g in schedule if g is None) * 100.0
        hard = -(hard_dup_w * duplicate_pairs + hard_std_w * student_conflicts +
                 hard_room_w * room_conflicts + unassigned_penalty)
        soft = soft_alloc_w * alloc_score - soft_consec_w * consecutive_exams - soft_late_w * late_exams
        return hard + soft

    # ------------------------------------------------------------------
    # A* heuristic  (notebook's h(n) adapted to rt-index domain)
    # ------------------------------------------------------------------

    def _heuristic(self, remaining: list, assignment: list) -> float:
        """
        Notebook's h(n): Σ(1 / |feasible_values|) for each unassigned exam.
        Returns float('inf') if any remaining exam has an empty domain (dead end).
        """
        h = 0.0
        used_slots = {v for v in assignment if v is not None}
        for e in remaining:
            count = 0
            for v in self.domain[e]:
                if v in used_slots:
                    continue
                # Quick conflict check against already-assigned exams only
                ok = True
                for other_e, other_v in enumerate(assignment):
                    if other_v is None:
                        continue
                    if not self._binary_ok(e, other_e, v, other_v):
                        ok = False
                        break
                if ok:
                    count += 1
            if count == 0:
                return float("inf")
            h += 1.0 / count
        return h

    # ------------------------------------------------------------------
    # Main search
    # ------------------------------------------------------------------

    def run(self, time_limit_sec: float = 30.0, progress_callback: Optional[Callable] = None):
        """
        Run A* search over room_timeslot index assignments.
        Returns (assignment, fitness, nodes_explored, elapsed_seconds).
        """
        start_t = time.perf_counter()
        deadline = start_t + time_limit_sec
        nodes_explored = 0
        last_report = start_t

        # Greedy fallback — always return something
        exam_students_list = [e.students for e in self.exams]
        fallback = greedy_assignment(
            exam_students_list, self.room_timeslot,
            enrollments=[len(s) for s in exam_students_list]
        )
        best_assignment = fallback
        best_fitness = self._solution_evaluation(fallback)

        # Ordering: most-constrained exams first (smallest domain → hardest)
        all_exams = sorted(range(self.number_of_exams), key=lambda e: len(self.domain[e]))
        total = self.number_of_exams

        # Priority queue entries: (f_score, tie_break, assignment_tuple, remaining_list)
        counter = 0
        initial_assignment = tuple([None] * total)
        h0 = self._heuristic(all_exams, list(initial_assignment))
        pq: list = []
        heapq.heappush(pq, (h0, counter, initial_assignment, all_exams))
        counter += 1

        visited: set = set()

        while pq and time.perf_counter() < deadline:
            f_score, _, asgn_tuple, remaining = heapq.heappop(pq)
            nodes_explored += 1

            # Visited-state deduplication (notebook FIX 4, adapted to rt indices)
            state_key = frozenset(
                (i, v) for i, v in enumerate(asgn_tuple) if v is not None
            )
            if state_key in visited:
                continue
            visited.add(state_key)

            # Progress
            now = time.perf_counter()
            if progress_callback and now - last_report >= 0.25:
                placed = sum(1 for v in asgn_tuple if v is not None)
                pct = min(95.0, ((now - start_t) / max(time_limit_sec, 0.01)) * 100)
                progress_callback(pct, f"A* explored {nodes_explored} states ({placed}/{total} placed)")
                last_report = now

            # Update best partial solution
            current_list = list(asgn_tuple)
            score = self._solution_evaluation(current_list)
            if score > best_fitness:
                best_fitness = score
                best_assignment = current_list

            # Goal check
            if not remaining:
                break

            # Pick next exam (first in remaining — already sorted by domain size)
            next_exam = remaining[0]
            rest = remaining[1:]

            # Collect feasible rt values for next_exam, sort by soft preference
            used_slots = {v for v in current_list if v is not None}
            candidates = []
            for v in self.domain[next_exam]:
                if v in used_slots:
                    continue
                ok = True
                for other_e, other_v in enumerate(current_list):
                    if other_v is None:
                        continue
                    if not self._binary_ok(next_exam, other_e, v, other_v):
                        ok = False
                        break
                if ok:
                    candidates.append(v)

            # Sort candidates same way CSP does (prefer early, non-late, good utilisation)
            candidates.sort(key=lambda v: (
                self.room_timeslot[v][1].is_late,
                sum(
                    self.exam_overlap[next_exam][i]
                    for i in range(total)
                    if current_list[i] is not None and
                    self.room_timeslot[current_list[i]][1].calendar_date ==
                    self.room_timeslot[v][1].calendar_date
                ),
                -room_utilization_score(
                    self.room_timeslot[v][0].capacity,
                    len(self.exams[next_exam].students)
                )
            ))

            for v in candidates:
                next_asgn = list(asgn_tuple)
                next_asgn[next_exam] = v
                next_tuple = tuple(next_asgn)

                g = -self._solution_evaluation(next_asgn)   # lower g = better score
                h = self._heuristic(rest, next_asgn)
                if h == float("inf"):
                    continue
                heapq.heappush(pq, (g + h, counter, next_tuple, rest))
                counter += 1

        elapsed = time.perf_counter() - start_t

        # ── Completion guarantee ──────────────────────────────────────────────
        # If A* timed out before placing every exam, run a fast backtracking
        # pass on the remaining unassigned exams.  Only a few exams are ever
        # left, so this completes in milliseconds.
        if any(v is None for v in best_assignment):
            self._complete_assignment(best_assignment)
            best_fitness = self._solution_evaluation(best_assignment)
        # ─────────────────────────────────────────────────────────────────────

        if progress_callback:
            placed = sum(1 for v in best_assignment if v is not None)
            progress_callback(100, f"A* done: {nodes_explored} states, {placed}/{total} placed in {elapsed:.2f}s")

        return best_assignment, best_fitness, nodes_explored, elapsed

    # ------------------------------------------------------------------
    # Completion guarantee  (backtracking over unassigned exams only)
    # ------------------------------------------------------------------

    def _complete_assignment(self, assignment: list) -> bool:
        """
        Backtracking search that fills every None slot in `assignment`.
        Only the unassigned exams are touched; already-placed exams are
        kept fixed.  This ensures the A* result is always a complete
        schedule (0 unassigned) when any valid assignment exists.

        Candidates are tried in domain order, sorted by: prefer non-late
        slots, prefer slots with fewer same-day student overlaps, prefer
        better room utilisation — same ordering CSP uses.
        """
        unassigned = [e for e in range(self.number_of_exams) if assignment[e] is None]
        if not unassigned:
            return True

        def backtrack(idx: int) -> bool:
            if idx == len(unassigned):
                return True
            e = unassigned[idx]
            # Gather feasible values for this exam
            used = {assignment[j] for j in range(self.number_of_exams) if assignment[j] is not None}
            candidates = []
            for v in self.domain[e]:
                if v in used:
                    continue
                ok = True
                for other_e, other_v in enumerate(assignment):
                    if other_v is None:
                        continue
                    if not self._binary_ok(e, other_e, v, other_v):
                        ok = False
                        break
                if ok:
                    candidates.append(v)

            # Sort same way CSP sorts values
            candidates.sort(key=lambda v: (
                self.room_timeslot[v][1].is_late,
                sum(
                    self.exam_overlap[e][i]
                    for i in range(self.number_of_exams)
                    if assignment[i] is not None and
                    self.room_timeslot[assignment[i]][1].calendar_date ==
                    self.room_timeslot[v][1].calendar_date
                ),
                -room_utilization_score(
                    self.room_timeslot[v][0].capacity,
                    len(self.exams[e].students)
                )
            ))

            for v in candidates:
                assignment[e] = v
                if backtrack(idx + 1):
                    return True
                assignment[e] = None

            return False

        return backtrack(0)
