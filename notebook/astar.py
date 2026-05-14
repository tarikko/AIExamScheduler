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
        """
        FIX 1: Round each slot to avoid float accumulation drift.
        0.5 is exactly representable in IEEE 754, so drift is unlikely here,
        but rounding makes the intent explicit and safe for any step size.
        """
        slot = []
        current = self.start_f
        while current <= self.end_f + 1e-9:   # small epsilon guards against drift dropping the last slot
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
                if start_t < assigned['end']+1 and assigned['start']-1 < end_t:
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

def calculate_g(self,self, current_assignments):
        """
        FIX 2: g(n) should represent the COST incurred so far — penalties only.
        The original code used len(current_assignments) + penalty, which made
        nodes with MORE exams placed appear MORE expensive. In the A* min-heap this
        caused nearly-complete schedules to be explored LAST, because their g was
        higher than shallow nodes. Penalty-only g(n) correctly guides the search:
        0 cost for clean assignments, positive cost only when constraints are violated.

        FIX 3: The if/elif penalty block was indented inside for student, which
        is correct for per-student tracking. No change needed there — but it is now
        dedented to sit clearly at the per-student level, outside the entry loop,
        to make the intent unambiguous.
        """
        total_penalty = 0
        daily_load = {}  # {day: {student_id: exam_count}}

        for entry in current_assignments:
            day = entry['day']
            if day not in daily_load:
                daily_load[day] = {}

            for student in entry['students']:
                daily_load[day][student] = daily_load[day].get(student, 0) + 1

                # Check penalty at the moment the count changes (correct placement)
                if daily_load[day][student] > 2:
                    total_penalty += 50   # Hard-constraint violation: 3+ exams in one day
                elif daily_load[day][student] == 2:
                    total_penalty += 2    # Soft penalty: 2 exams in one day

        # FIX 2: Return penalty only — do NOT add len(current_assignments)
        return total_penalty

    def calculate_h(self, remaining_modules, current_assignments):
        """
        Heuristic: sum of (1 / number_of_options) for each remaining module.
        Returns inf if any module has zero valid placements (dead end).
        """
        h_val = 0
        for module_name in remaining_modules:
            students = self.studentAssignedToModule.get(module_name, set())
            valid_options = self.find_valid_placements(module_name, students, current_assignments)
            num_options = len(valid_options)

            if num_options == 0:
                return float('inf')  # Dead end: prune this branch

            h_val += (1.0 / num_options)

        return h_val

    def f_function(self, remaining_modules, current_assignment):
        return self.calculate_g(current_assignment) + self.calculate_h(remaining_modules, current_assignment)

    def AstarSearch(self):
        """
        FIX 4: Represent the state as a frozenset of placed exam names so we can
        detect and skip already-explored states. Without a visited set the queue
        can grow exponentially as the same partial schedule is re-expanded through
        different insertion orders.

        The heap tuple is  (f_score, tie_breaker_count, schedule, remaining).
        count is always unique, so heapq never needs to compare schedules or
        remaining lists (which would crash on list-of-dicts).
        """
        all_modules = list(self.studentAssignedToModule.keys())
        count = 0
        pq = []
        visited = set()  # FIX 4: track explored states

        initial_f = self.f_function(all_modules, [])
        heapq.heappush(pq, (initial_f, count, [], all_modules))
        count += 1

        while pq:
            current_f, _, current_schedule, remaining = heapq.heappop(pq)

            # --- FIX 4: build a hashable state key and skip if already explored ---
            state_key = frozenset(e['exam'] for e in current_schedule)
            if state_key in visited:
                continue
            visited.add(state_key)
            # --------------------------------------------------------------------

            if not remaining:
                self.schedule = current_schedule
                return "Success!"

            next_mod = remaining[0]
            other_remaining = remaining[1:]
            student_set = self.studentAssignedToModule[next_mod]

valid_placements = self.find_valid_placements(next_mod, student_set, current_schedule)

            for placement in valid_placements:
                new_schedule = current_schedule + [placement]
                f_score = self.f_function(other_remaining, new_schedule)

                if f_score != float('inf'):
                    heapq.heappush(pq, (f_score, count, new_schedule, other_remaining))
                    count += 1

        return "No solution found"


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------
def test():
    #exam_student_data = [
    # A core group of students (S1-S3) in every single exam
   # ("Advanced_Math", "S1"), ("Advanced_Math", "S2"), ("Advanced_Math", "S3"),
  #  ("Quantum_Physics", "S1"), ("Quantum_Physics", "S2"), ("Quantum_Physics", "S3"),
   # ("Organic_Chem", "S1"), ("Organic_Chem", "S2"), ("Organic_Chem", "S3"),
   # ("Linear_Algebra", "S1"), ("Linear_Algebra", "S4"), ("Linear_Algebra", "S5"),
    #("Bio_Stats", "S2"), ("Bio_Stats", "S6"), ("Bio_Stats", "S7")
    #]

    room_capacities = {
    "room_1": 80, 
    "room_2": 80, 
    "room_3": 80, 
    "room_4": 80, 
    "room_5": 80, 
    "room_6": 80, 
    "room_7": 80, 
    "room_8": 80, 
    }

    # Tight timeline to force conflicts
    from_time = "09:00"
    to_time = "17:00" 
    days_str = "Mond-01-06-2006, Tues02-06-2006, Wed-03-06-2006, Thur-04-06-2006, Sat-06-06-2006, Sun-07-06-2006, Mon-08-06-2006"

    durations = {
    "Linear_algebra": 2.0, 
    "Statistics": 2.0,
    "Introduction_to_linux": 2.0,
    "oop": 1.0, 
    "Analyse_1": 1.0,
    "English_2":2.0,
    "history_of_algeria":1.0,
    "introduction_to_AI":2.0,
    "lab_circuit":1.5,
    "analyse_3":2.0,
    "computer_architecture":2.0,
    "inferential_statistic":2.0,
    "operating_system":2.0,
    "theory_of_computing":2.0,
    "MAchine_Learning":2.0,
    "Computer_networking_security":2.0,
    "Numerical_methods_and_optimizations":2.0,
    "Advanced_databases":2.0,
    "Time_Series_Analysis_and_Classification":2.0,
    "Big Data Analytics & Visualization":2.0,
    "Computer Vision":2.0,
    "Speech Processing":2.0,
    "Academic Communication and Research":2.0,
    "High Performance Computing":2.0,
    "Enterprise Computing":2.0,
    "Reinforcement Learning":2.0,
    "Introduction to Business Law":2.0,
    "Introduction to Research Methodology":2.0,
    "Advanced Research Topics":2.0,
    "History_of_algeria1":1.0,
    "Citizenship":1.0,
    "Market Research":1.5
    }
    exam_student_data=[]
    
    first_year_modules=[
    "Linear_algebra", 
    "Statistics",
    "Introduction_to_linux",
    "oop", 
    "Analyse_1",
    "English_2",
    "history_of_algeria"
    ]

    second_year_modules=[
    "introduction_to_AI",
    "lab_circuit",
    "analyse_3",
    "computer_architecture",
    "inferential_statistic",
    "operating_system",
    "theory_of_computing",
    ]

    third_year_modules=[
    "MAchine_Learning",
    "Computer_networking_security",
    "Numerical_methods_and_optimizations",
    "Advanced_databases",
    "Time_Series_Analysis_and_Classification",
    ]

    fourth_year_modules=[
    "Big Data Analytics & Visualization",
    "Computer Vision",
    "Speech Processing",
    "Academic Communication and Research",
    "High Performance Computing",
    "Enterprise Computing",
    "Reinforcement Learning"
    ]

    fifth_year_modules=[
    "Introduction to Business Law",
    "Introduction to Research Methodology",
    "Advanced Research Topics",
    "History_of_algeria1",
    "Citizenship",
    "Market Research"
    ]

    for module in first_year_modules:
        for i in range (1,181):
            exam_student_data.append((module,f"S1_{i}"))

    for module in second_year_modules:
        for i in range (1,301):
            exam_student_data.append((module,f"S2_{i}"))

    for module in third_year_modules:
        for i in range (1,271):
            exam_student_data.append((module,f"S3_{i}"))

    for module in fourth_year_modules:
        for i in range (1,181):exam_student_data.append((module,f"S4_{i}"))

    for module in fifth_year_modules:
        for i in range (1,101):
            exam_student_data.append((module,f"S5_{i}"))
    
    my_scheduler = schedule(
        exam_student_data, room_capacities,
        from_time, to_time, days_str, durations
    )

    print("Starting A* Search...")
    result = my_scheduler.AstarSearch()

    if result == "Success!":
        print("\n--- Final Schedule Found ---")
        for entry in sorted(my_scheduler.schedule, key=lambda e: (e['day'], e['start'])):
            print(f"Exam: {entry['exam']:<15} | Day: {entry['day']:<10} | "
                  f"Time: {entry['start']}-{entry['end']} | Rooms: {entry['rooms']} |Students:{entry['students']}")
    else:
        print("No valid schedule could be found with these constraints.")


if name == "main":
    test()
