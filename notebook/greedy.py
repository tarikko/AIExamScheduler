from math import ceil
import heapq


class schedule:
    def init(self, exam_student, room_capacity, from_time, to_time, days_str, exam_duration):
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
        for assigned in current_schedule:
            if assigned['day'] == day:
                if start_t < assigned['end'] + 1 and assigned['start'] - 1 < end_t:
                    if not new_exam_students.isdisjoint(assigned['students']):
                        return True
        return False

    def find_valid_placements(self, exam, student_set, current_assignments):
        rooms_dict = self.room_capacity
        time_slots = self.slots
        days = self.days
        possible_placements = []

        for day in days:
            for start_t in time_slots:
                end_t = round(start_t + self.exam_duration[exam], 2)
                if end_t > self.end_f:
                    continue

                if self.has_student_conflict(student_set, day, start_t, end_t, current_assignments):
                    continue

                available_rooms = []
                for r_name, r_cap in rooms_dict.items():
                    if self.is_room_free(r_name, day, start_t, end_t, current_assignments):
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

    def greedySearch(self, strategy='largest_enrollment'):
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

        # Step 2: greedily assign each exam
        for exam in ordered_exams:
            student_set = self.studentAssignedToModule[exam]

            # Find every valid placement for this exam given what is already assigned
            valid_placements = self.find_valid_placements(exam, student_set, current_schedule)

            if not valid_placements:
                # Hard failure: greedy cannot backtrack
                return "No solution found"

            # Step 3: pick the best placement with a local cost function
            best_placement = self._pick_best_placement(valid_placements, current_schedule)
            current_schedule.append(best_placement)

        # All exams placed successfully
        self.schedule = current_schedule
        return "Success!"

    def _pick_best_placement(self, valid_placements, current_schedule):
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
        def placement_score(placement):
            # Simulate adding this placement and measure the penalty delta
            trial_schedule = current_schedule + [placement]
            penalty_after  = self.calculate_g(trial_schedule)
            penalty_before = self.calculate_g(current_schedule)
            incremental_penalty = penalty_after - penalty_before

            # Tie-break 1: prefer earlier days (day index in sorted self.days)
            day_index = self.days.index(placement['day']) if placement['day'] in self.days else 999

            # Tie-break 2: prefer earlier start time
            start_time = placement['start']

            return (incremental_penalty, day_index, start_time)

        return min(valid_placements, key=placement_score)
