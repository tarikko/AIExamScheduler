"""
Greedy scheduler adapter — bridges the user's original ``schedule`` class
(from notebook/greedy.py) to the backend's data model used by main.py.

Performance-optimised version:
  • Cached penalty_before in _pick_best_placement (OPT 1)
  • Incremental penalty via running daily_load (OPT 2)
  • schedule_by_day index for conflict/room checks (OPT 3)
  • Early exit per (day, slot) before room loop (OPT 4)
  • Reuse _exam_students in adapter (OPT 5)
  • Per-exam progress callback (OPT 6)
"""
from math import ceil
import heapq
import re
from typing import Callable, Optional


# ═══════════════════════════════════════════════════════════════════════════
# User's original schedule class — copied verbatim from notebook/greedy.py
# with ONLY the two fixes noted above.
# ═══════════════════════════════════════════════════════════════════════════

class schedule:
    def __init__(self, exam_student, room_capacity, from_time, to_time, days_str, exam_duration):
        self.exam_student = exam_student
        self.room_capacity = room_capacity
        self.from_time = from_time
        self.to_time = to_time
        self.start_f = self.to_float(from_time)
        self.end_f = self.to_float(to_time)
        self.days = sorted([d.strip() for d in days_str.split(',')])
        self.slots = self.generate_slots()
        self.schedule = []
        self.studentAssignedToModule = self.assignStudentToModule()
        self.exam_duration = exam_duration

    # ------------------------------------------------------------------
    # Shared helper methods
    # ------------------------------------------------------------------

    def addStudentToModule(self, module, student, studentToModule):
        if module not in studentToModule:
            studentToModule[module] = set()
        studentToModule[module].add(student)

    def assignStudentToModule(self):
        studentToModule = dict()
        for exam, student in self.exam_student:
            self.addStudentToModule(exam, student, studentToModule)
        return studentToModule

    def is_room_free(self, room_name, day, start_t, end_t, current_schedule):
        # OPT 3: current_schedule is now the day-subset when called from
        # find_valid_placements, so we skip the day== check in that path.
        for assigned in current_schedule:
            if assigned['day'] == day:
                if start_t < assigned['end'] and assigned['start'] < end_t:
                    if room_name in assigned['rooms']:
                        return False
        return True

    def generate_slots(self):
        slot = []
        current = self.start_f
        while current <= self.end_f + 1e-9:
            slot.append(round(current, 2))
            current = round(current + 0.5, 2)
        return slot

    def to_float(self, time_str):
        hours, minutes = map(int, time_str.split(':'))
        fraction = minutes / 60.0
        return round(hours + fraction, 2)

    def has_student_conflict(self, new_exam_students, day, start_t, end_t, current_schedule):
        # OPT 3: current_schedule may already be filtered to this day
        for assigned in current_schedule:
            if assigned['day'] == day:
                if start_t < assigned['end'] + 1 and assigned['start'] - 1 < end_t:
                    if not new_exam_students.isdisjoint(assigned['students']):
                        return True
        return False

    def find_valid_placements(self, exam, student_set, current_assignments,
                              schedule_by_day=None):
        rooms_dict = self.room_capacity
        time_slots = self.slots
        days = self.days
        possible_placements = []

        for day in days:
            # OPT 3: use the day-indexed subset instead of full schedule
            day_entries = (schedule_by_day.get(day, [])
                          if schedule_by_day is not None
                          else current_assignments)

            for start_t in time_slots:
                end_t = round(start_t + self.exam_duration[exam], 2)
                if end_t > self.end_f:
                    continue

                # OPT 4: check student conflict once per (day, slot);
                # if conflict, skip all rooms for this slot entirely
                if self.has_student_conflict(student_set, day, start_t, end_t, day_entries):
                    continue

                available_rooms = []
                for r_name, r_cap in rooms_dict.items():
                    if self.is_room_free(r_name, day, start_t, end_t, day_entries):
                        available_rooms.append((r_name, r_cap))

                available_rooms.sort(key=lambda x: x[1], reverse=True)

                selected_rooms = []
                current_cap = 0
                for r_name, r_cap in available_rooms:
                    if current_cap < len(student_set):
                        selected_rooms.append(r_name)
                        current_cap += r_cap / 2

                if current_cap >= len(student_set):
                    possible_placements.append({
                        'exam': exam,
                        'day': day,
                        'start': start_t,
                        'end': end_t,
                        'rooms': selected_rooms,
                        'students': student_set
                    })

        return possible_placements

    def calculate_g(self, current_assignments):
        total_penalty = 0
        daily_load = {}

        for entry in current_assignments:
            day = entry['day']
            if day not in daily_load:
                daily_load[day] = {}

            for student in entry['students']:
                daily_load[day][student] = daily_load[day].get(student, 0) + 1

                if daily_load[day][student] > 2:
                    total_penalty += 50
                elif daily_load[day][student] == 2:
                    total_penalty += 2

        return total_penalty

    # OPT 2: incremental penalty — O(students_in_exam) instead of O(schedule)
    def calculate_incremental_penalty(self, placement, current_daily_load):
        """
        Compute the penalty *delta* introduced by adding ``placement``
        to a schedule whose running daily_load is ``current_daily_load``.

        Does NOT mutate current_daily_load.
        """
        day = placement['day']
        day_load = current_daily_load.get(day, {})
        delta = 0
        for student in placement['students']:
            count = day_load.get(student, 0)
            new_count = count + 1
            # Subtract old contribution, add new contribution
            if new_count > 2:
                delta += 50
            elif new_count == 2:
                delta += 2
            # (if count was already >2 the old penalty was already counted;
            #  we only care about the *marginal* change here which is the
            #  same logic as the original: each entry's students are scored
            #  independently in calculate_g)
        return delta

    @staticmethod
    def _update_daily_load(daily_load, placement):
        """Update the running daily_load dict after committing a placement."""
        day = placement['day']
        if day not in daily_load:
            daily_load[day] = {}
        day_dict = daily_load[day]
        for student in placement['students']:
            day_dict[student] = day_dict.get(student, 0) + 1

    # ------------------------------------------------------------------
    # Greedy-specific ordering methods
    # ------------------------------------------------------------------

    def order_by_largest_enrollment(self):
        """
        Strategy 1 — Largest Enrollment First.

        Exams with more students are harder to place (they need more room
        capacity and generate more potential conflicts), so we schedule them
        first when there are still many free slots available.

        Returns the exam list sorted from most to fewest enrolled students.
        """
        return sorted(
            self.studentAssignedToModule.keys(),
            key=lambda exam: len(self.studentAssignedToModule[exam]),
            reverse=True   # biggest enrollment first
        )

    def order_by_degree_heuristic(self):
        """
        Strategy 2 — Degree Heuristic (most conflicting exams first).

        For each exam, count how many *other* exams share at least one student
        with it.  An exam with a high "degree" conflicts with many others, so
        placing it early gives the scheduler the most freedom for the
        remaining exams.

        This mirrors the graph-coloring Degree Heuristic: colour the vertex
        with the most edges first.

        Returns the exam list sorted from highest degree to lowest.
        """
        all_modules = list(self.studentAssignedToModule.keys())

        def conflict_degree(exam):
            students = self.studentAssignedToModule[exam]
            degree = 0
            for other in all_modules:
                if other == exam:
                    continue
                other_students = self.studentAssignedToModule[other]
                # Two exams conflict if they share at least one student
                if not students.isdisjoint(other_students):
                    degree += 1
            return degree

        return sorted(all_modules, key=conflict_degree, reverse=True)

    # ------------------------------------------------------------------
    # Greedy Search — core algorithm
    # ------------------------------------------------------------------

    def greedySearch(self, strategy='largest_enrollment', progress_callback=None):
        """
        Greedy Search for exam scheduling.

        Parameters
        ----------
        strategy : str
            'largest_enrollment' — schedule biggest exams first (default).
            'degree_heuristic'   — schedule most-conflicting exams first.

        Algorithm
        ---------
        1. Order all exams using the chosen strategy.
        2. For each exam in order:
           a. Find all valid (day, slot, rooms) placements via
              find_valid_placements() — same logic used by A*.
           b. If no valid placement exists → fail immediately (no backtracking).
           c. Pick the *best* placement using a local cost score:
              - Prefer slots that produce the lowest soft-constraint penalty
                (fewest students with 2 exams on the same day).
              - Break ties by choosing the earliest day, then earliest time
                (compact schedule → fewer days students must attend).
        3. Commit to that placement and move to the next exam.

        The key difference from A*:
        - A* explores *all* orderings via a priority queue and backtracks.
        - Greedy commits immediately to its local best choice — O(n) decisions
          instead of exponential branching.  Much faster, but can fail or
          produce a higher-penalty schedule than A*.

        Returns
        -------
        'Success!' if every exam was placed, 'No solution found' otherwise.
        """

        # Step 1: determine exam ordering
        if strategy == 'degree_heuristic':
            ordered_exams = self.order_by_degree_heuristic()
        else:
            ordered_exams = self.order_by_largest_enrollment()

        current_schedule = []
        # OPT 2: running daily load — updated after each commit
        running_daily_load = {}
        # OPT 3: schedule indexed by day
        schedule_by_day = {}

        total = len(ordered_exams)

        # Step 2: greedily assign each exam
        for step, exam in enumerate(ordered_exams):
            student_set = self.studentAssignedToModule[exam]

            # Find every valid placement for this exam given what is already assigned
            valid_placements = self.find_valid_placements(
                exam, student_set, current_schedule,
                schedule_by_day=schedule_by_day,
            )

            if not valid_placements:
                # Hard failure: greedy cannot backtrack
                return "No solution found"

            # Step 3: pick the best placement with a local cost function
            best_placement = self._pick_best_placement(
                valid_placements, current_schedule, running_daily_load
            )
            current_schedule.append(best_placement)

            # OPT 2: update running daily load
            self._update_daily_load(running_daily_load, best_placement)
            # OPT 3: update schedule_by_day index
            day = best_placement['day']
            schedule_by_day.setdefault(day, []).append(best_placement)

            # OPT 6: per-exam progress reporting
            if progress_callback:
                pct = 15 + int(80 * (step + 1) / total)
                progress_callback(pct, f"Placed {step+1}/{total} exams...")

        # All exams placed successfully
        self.schedule = current_schedule
        return "Success!"

    def _pick_best_placement(self, valid_placements, current_schedule,
                             running_daily_load=None):
        """
        Local scoring function: choose the placement that minimises the
        soft-constraint penalty added by assigning this exam.

        Tie-breaking rules (in priority order):
          1. Lowest incremental penalty (fewest students with 2 exams/day).
          2. Earliest day index (compact the schedule toward the start).
          3. Earliest start time (prefer morning slots).

        This is *not* a global cost calculation — it only evaluates the
        marginal cost of each candidate placement for the current exam,
        which keeps the greedy step O(placements).
        """
        # OPT 1 + OPT 2: use incremental penalty with running daily_load
        if running_daily_load is not None:
            def placement_score(placement):
                incremental_penalty = self.calculate_incremental_penalty(
                    placement, running_daily_load
                )
                day_index = (self.days.index(placement['day'])
                             if placement['day'] in self.days else 999)
                start_time = placement['start']
                return (incremental_penalty, day_index, start_time)
        else:
            # Fallback: original behaviour
            penalty_before = self.calculate_g(current_schedule)  # OPT 1: cached
            def placement_score(placement):
                trial_schedule = current_schedule + [placement]
                penalty_after = self.calculate_g(trial_schedule)
                incremental_penalty = penalty_after - penalty_before
                day_index = (self.days.index(placement['day'])
                             if placement['day'] in self.days else 999)
                start_time = placement['start']
                return (incremental_penalty, day_index, start_time)

        return min(valid_placements, key=placement_score)


# ═══════════════════════════════════════════════════════════════════════════
# Adapter layer — transforms between the web interface data model
# and the schedule class expected inputs / outputs.
# ═══════════════════════════════════════════════════════════════════════════

def _float_to_time_str(f: float) -> str:
    """Convert a float like 9.0 or 14.5 to 'HH:MM' string."""
    hours = int(f)
    minutes = int(round((f - hours) * 60))
    return f"{hours:02d}:{minutes:02d}"


class GreedyScheduler:
    """
    Adapter that bridges main.py's data model to the user's ``schedule``
    class.  It converts the interface data into the format schedule.__init__
    expects, runs greedySearch(), and builds a frontend-compatible result
    directly from the placement dicts — without forcing them through the
    fixed-slot rt_idx model used by CSP/GA.
    """

    def __init__(self, courses, students, rooms, timeslots, room_timeslot):
        """
        Parameters are the objects already available inside main.py:
          courses      – list of CourseSchema (code, name, enrollment, duration_minutes)
          students     – list of StudentSchema (id, courses)
          rooms        – list of Room domain objects (may be grouped by data_loader)
          timeslots    – list of Timeslot domain objects
          room_timeslot – cartesian product list of (Room, Timeslot) tuples
        """
        self.courses = courses
        self.students = students
        self.rooms = rooms
        self.timeslots = timeslots
        self.room_timeslot = room_timeslot

        # Build course lookup
        self._course_info = {c.code: c for c in courses}

        # OPT 5: pre-build exam_student_pairs once; reused in run()
        self._exam_student_pairs = self._build_exam_student_pairs()

    # ── Input transformation ──────────────────────────────────────────

    def _build_exam_student_pairs(self) -> list[tuple[str, str]]:
        """Build (exam_code, student_id) tuples from student enrollments."""
        pairs = []
        for s in self.students:
            for course_code in s.courses:
                pairs.append((course_code, s.id))
        return pairs

    @staticmethod
    def _ungroup_room(name: str, capacity: int) -> list[tuple[str, int]]:
        """
        Detect grouped room names and split them into individual rooms.

        Example: "AMPHI_1_2_3" with capacity 300
          → [("AMPHI_1", 100), ("AMPHI_2", 100), ("AMPHI_3", 100)]

        If the name contains only one numeric part (e.g. "BaseRoom_001"),
        it is NOT grouped and is returned as-is.
        """
        # Extract prefix and all numeric segments from the name.
        # Pattern: PREFIX_N1_N2_N3... where N1..Nn are single digits or
        # short numbers representing individual room identifiers.
        match = re.match(r'^([A-Za-z]+)_(\d+(?:_\d+)*)$', name)
        if not match:
            return [(name, capacity)]

        prefix = match.group(1)
        num_parts = match.group(2).split('_')

        # Only ungroup if there are multiple numeric segments.
        # A name like "BaseRoom_001" has one segment → not grouped.
        if len(num_parts) <= 1:
            return [(name, capacity)]

        # Split capacity evenly among constituent rooms
        per_room = capacity // len(num_parts)
        return [(f"{prefix}_{n}", per_room) for n in num_parts]

    def _build_room_capacity(self) -> dict[str, int]:
        """
        Build {room_name: capacity} dict for the user's algorithm.

        Detects grouped room names (e.g. "AMPHI_1_2_3" representing
        Amphi 1 + Amphi 2 + Amphi 3 with combined capacity) and splits
        them into individual rooms.  This is necessary because the user's
        find_valid_placements() selects rooms one by one.

        Non-grouped room names (e.g. "BaseRoom_001") pass through unchanged.
        """
        result = {}
        for r in self.rooms:
            for individual_name, individual_cap in self._ungroup_room(r.name, r.capacity):
                result[individual_name] = individual_cap
        return result

    def _build_exam_duration(self) -> dict[str, float]:
        """Build {exam_code: duration_in_hours} dict."""
        return {c.code: c.duration_minutes / 60.0 for c in self.courses}

    def _derive_time_range(self) -> tuple[str, str]:
        """
        Derive from_time and to_time for the greedy algorithm.

        Unlike CSP/GA which use only the predefined benchmark timeslots,
        the greedy algorithm generates its own 30-minute slots via
        generate_slots().  It needs a full academic-day window to have
        enough room-time combinations for dense schedules.

        The range is computed as:
          from_time = min(earliest benchmark slot, 08:00)
          to_time   = max(latest slot + max_duration, 18:00)

        This guarantees at least 3 non-overlapping exam windows per day
        even with 2-hour exams and 1-hour student conflict buffers.
        """
        hours = [ts.hour + ts.minute / 60.0 for ts in self.timeslots]
        min_hour = min(hours)
        max_hour = max(hours)
        max_duration_hours = max(
            (c.duration_minutes / 60.0 for c in self.courses), default=2.0
        )

        # Use the wider of: benchmark-derived range vs standard academic day
        from_hour = min(min_hour, 8.0)
        end_hour = max(max_hour + max_duration_hours, 18.0)

        return _float_to_time_str(from_hour), _float_to_time_str(end_hour)

    def _derive_days_string(self) -> str:
        """
        Build a comma-separated day string from the timeslot dates.
        Uses the calendar_date (YYYY-MM-DD) of each timeslot, deduplicated.
        """
        seen = set()
        days = []
        for ts in self.timeslots:
            day = ts.calendar_date  # "YYYY-MM-DD" portion
            if day not in seen:
                seen.add(day)
                days.append(day)
        return ", ".join(sorted(days))

    # ── Main entry point ──────────────────────────────────────────────

    def run(
        self,
        strategy: str = "largest_enrollment",
        progress_callback: Optional[Callable] = None,
    ):
        """
        Run the user's greedy algorithm.

        Returns
        -------
        tuple of (greedy_schedule, penalty, result_status)
            greedy_schedule : list[dict] – the user's sched.schedule output
            penalty         : int       – the user's calculate_g penalty
            result_status   : str       – "Success!" or "No solution found"
        """
        if progress_callback:
            progress_callback(5, "Preparing data for Greedy Search...")

        # 1. Transform interface data → user's expected format
        # OPT 5: reuse pre-built pairs from __init__
        exam_student_pairs = self._exam_student_pairs
        room_capacity_dict = self._build_room_capacity()
        from_time, to_time = self._derive_time_range()
        days_str = self._derive_days_string()
        exam_duration_dict = self._build_exam_duration()

        if progress_callback:
            progress_callback(10, "Initializing Greedy scheduler...")

        # 2. Instantiate the user's schedule class
        sched = schedule(
            exam_student_pairs,
            room_capacity_dict,
            from_time,
            to_time,
            days_str,
            exam_duration_dict,
        )

        if progress_callback:
            progress_callback(15, f"Running Greedy Search ({strategy})...")

        # 3. Run the user's greedySearch — OPT 6: pass progress_callback
        result_str = sched.greedySearch(
            strategy=strategy, progress_callback=progress_callback
        )

        if progress_callback:
            progress_callback(95, "Greedy Search complete.")

        # 4. Return raw results — main.py will format them
        if result_str != "Success!":
            return [], 0, result_str, room_capacity_dict

        penalty = sched.calculate_g(sched.schedule)
        return sched.schedule, penalty, result_str, room_capacity_dict


def format_greedy_result(greedy_schedule, penalty, result_status, courses, students, elapsed, algorithm, room_capacity_map=None):
    """
    Build the frontend-compatible result dict directly from the user's
    placement dicts.  This bypasses _format_result() entirely because
    the user's algorithm generates its own timeslots dynamically (every
    30 min) rather than using the fixed benchmark timeslots.

    The output JSON structure matches exactly what _format_result produces,
    so the frontend's handleResult() works without any changes.
    """
    course_info = {c.code: c for c in courses}
    room_cap = room_capacity_map or {}

    # Build assignments list
    assignments = []
    for entry in greedy_schedule:
        exam_code = entry['exam']
        course = course_info.get(exam_code)
        if course is None:
            continue

        # Convert float start time to "YYYY-MM-DD HH:MM" string
        day = entry['day']
        start_f = entry['start']
        time_str = _float_to_time_str(start_f)
        timeslot_date = f"{day} {time_str}"

        # The user's algorithm may assign multiple rooms; show combined name
        room_names = entry.get('rooms', [])
        if room_names:
            if len(room_names) > 1:
                primary_room = " + ".join(room_names)
            else:
                primary_room = room_names[0]
        else:
            primary_room = "Unassigned"

        # Sum capacity of all assigned rooms
        room_capacity = sum(room_cap.get(rname, 0) for rname in room_names)
        if room_capacity == 0:
            room_capacity = course.enrollment  # fallback

        is_late = start_f >= 15.0

        assignments.append({
            "exam_index": list(course_info.keys()).index(exam_code) if exam_code in course_info else 0,
            "course_code": exam_code,
            "course_name": course.name,
            "enrollment": course.enrollment,
            "duration_minutes": course.duration_minutes,
            "room_name": primary_room,
            "room_capacity": room_capacity,
            "timeslot_date": timeslot_date,
            "is_late": is_late,
        })

    # Compute metrics directly from the greedy schedule
    assigned_codes = {entry['exam'] for entry in greedy_schedule}
    all_codes = [c.code for c in courses]
    unassigned = [code for code in all_codes if code not in assigned_codes]

    # Student conflicts: check if any student has 2+ exams at overlapping times
    student_conflicts = 0
    for student in students:
        # Gather this student's exam placements
        student_exams = []
        for entry in greedy_schedule:
            if student.id in entry.get('students', set()):
                student_exams.append(entry)

        # Check for time overlaps on the same day
        for i, e1 in enumerate(student_exams):
            for e2 in student_exams[i+1:]:
                if e1['day'] == e2['day']:
                    if e1['start'] < e2['end'] and e2['start'] < e1['end']:
                        student_conflicts += 1

    # Room conflicts: check if any room is double-booked
    room_conflicts = 0
    for i, e1 in enumerate(greedy_schedule):
        for e2 in greedy_schedule[i+1:]:
            if e1['day'] == e2['day']:
                if e1['start'] < e2['end'] and e2['start'] < e1['end']:
                    shared_rooms = set(e1['rooms']) & set(e2['rooms'])
                    room_conflicts += len(shared_rooms)

    # Consecutive exam stress
    consecutive_stress = 0
    for student in students:
        student_exams = []
        for entry in greedy_schedule:
            if student.id in entry.get('students', set()):
                student_exams.append(entry)
        by_day = {}
        for e in student_exams:
            by_day.setdefault(e['day'], []).append(e['start'])
        for day, starts in by_day.items():
            starts_sorted = sorted(starts)
            for j in range(len(starts_sorted) - 1):
                # "Consecutive" = one exam starts right when previous ends
                # Use a rough check: gap < 1 hour between end of one and start of next
                if starts_sorted[j+1] - starts_sorted[j] <= 2.5:
                    consecutive_stress += 1

    # Room daily load
    room_daily_load_map = {}
    for entry in greedy_schedule:
        for rname in entry['rooms']:
            key = (rname, entry['day'])
            room_daily_load_map[key] = room_daily_load_map.get(key, 0) + 1

    room_daily_load_rows = [
        {"room": room, "day": day, "exam_count": count}
        for (room, day), count in sorted(room_daily_load_map.items())
    ]

    hard_violations = student_conflicts + room_conflicts + len(unassigned)

    metrics = {
        "elapsed_seconds": round(elapsed, 3),
        "fitness": 1.0 / (1.0 + penalty) if penalty >= 0 else 0,
        "penalty": penalty,
        "assigned_count": len(assignments),
        "unassigned_count": len(unassigned),
        "unassigned_courses": unassigned,
        "hard_violations": hard_violations,
        "capacity_violations": 0,  # user's algorithm validates capacity internally
        "student_conflict_count": student_conflicts,
        "room_conflict_count": room_conflicts,
        "consecutive_exam_stress": consecutive_stress,
        "room_daily_load": room_daily_load_rows,
        "max_room_daily_exams": max((row["exam_count"] for row in room_daily_load_rows), default=0),
    }

    fitness = 1.0 / (1.0 + penalty) if penalty >= 0 else 0

    return {
        "assignments": assignments,
        "fitness": round(fitness, 6),
        "elapsed_seconds": round(elapsed, 3),
        "algorithm": algorithm,
        "metrics": metrics,
    }
