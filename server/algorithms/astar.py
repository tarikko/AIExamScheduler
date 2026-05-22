from math import ceil
from math import floor
import heapq


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

    def addStudentToModule(self, module, student, studentToModule):
        if module not in studentToModule:
            studentToModule[module] = set()
        studentToModule[module].add(student)

    def assignStudentToModule(self):
        studentToModule = dict()
        for exam, student in self.exam_student:
            self.addStudentToModule(exam, student, studentToModule)
        return studentToModule

    def is_room_free(self, room_name, day, start_t, end_t, day_schedule):
        for assigned in day_schedule:
            # Assumes day_schedule ONLY contains assignments for the target day
            if start_t < assigned['end']+1.0 and assigned['start']-1.0 < end_t:
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

    def has_student_conflict(self, new_exam_students, day, start_t, end_t, day_schedule):
        for assigned in day_schedule:
            # Assumes day_schedule ONLY contains assignments for the target day
            if start_t < (assigned['end'] ) and assigned['start'] < (end_t ):
                if not new_exam_students.isdisjoint(assigned['students']):
                    return True
        return False

    def find_valid_placements(self, exam, student_set, current_assignments):
        rooms_dict = self.room_capacity
        time_slots = self.slots
        days = self.days
        possible_placements = []
        
        # Pre-group assignments by day to vastly speed up conflict checking
        day_assignments = {d: [] for d in days}
        for assigned in current_assignments:
            if assigned['day'] in day_assignments:
                day_assignments[assigned['day']].append(assigned)

        for day in days:
            day_sched = day_assignments[day]
            for start_t in time_slots:
                end_t = round(start_t + self.exam_duration[exam], 2)
                if end_t > self.end_f:
                    continue

                if self.has_student_conflict(student_set, day, start_t, end_t, day_sched):
                    continue

                available_rooms = []
                for r_name, r_cap in rooms_dict.items():
                    if self.is_room_free(r_name, day, start_t, end_t, day_sched):
                        available_rooms.append((r_name, r_cap))

                available_rooms.sort(key=lambda x: x[1], reverse=True)

                selected_rooms = []
                current_cap = 0
                for r_name, r_cap in available_rooms:
                    if current_cap < len(student_set):
                        selected_rooms.append(r_name)
                        current_cap += r_cap

                if current_cap >= len(student_set):
                    waste = current_cap - len(student_set)
                    possible_placements.append((waste, {
                        'exam': exam,
                        'day': day,
                        'start': start_t,
                        'end': end_t,
                        'rooms': selected_rooms,
                        'students': student_set
                    }))

        # Sort by least waste (best room fit) and prune branching factor to Top 5
        possible_placements.sort(key=lambda x: x[0])
        return [p[1] for p in possible_placements[:5]]

    def calculate_g(self, current_assignments):
        """
        FIX 2: g(n) should represent the COST incurred so far — penalties only.
        The original code used `len(current_assignments) + penalty`, which made
        nodes with MORE exams placed appear MORE expensive. In the A* min-heap this
        caused nearly-complete schedules to be explored LAST, because their g was
        higher than shallow nodes. Penalty-only g(n) correctly guides the search:
        0 cost for clean assignments, positive cost only when constraints are violated.

        FIX 3: The if/elif penalty block was indented inside `for student`, which
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
        Fast heuristic: number of remaining modules * heavily weighted.
        By weighting this massively (10000), we force A* to act like a Greedy-DFS.
        It will always prefer deeper nodes (placing more exams) over shallower nodes,
        even if the deeper node incurs soft penalty costs in g(n). 
        This completely eliminates thrashing/backtracking on massive datasets.
        """
        return len(remaining_modules) * 10000.0

    def f_function(self, remaining_modules, current_assignment):
        return self.calculate_g(current_assignment) + self.calculate_h(remaining_modules, current_assignment)

    def AstarSearch(self, time_limit_sec=None):
        """
        FIX 4: Represent the state as a frozenset of placed exam names so we can
        detect and skip already-explored states. Without a visited set the queue
        can grow exponentially as the same partial schedule is re-expanded through
        different insertion orders.

        The heap tuple is  (f_score, tie_breaker_count, schedule, remaining).
        `count` is always unique, so heapq never needs to compare schedules or
        remaining lists (which would crash on list-of-dicts).
        """
        import time
        start_time = time.perf_counter()

        all_modules = list(self.studentAssignedToModule.keys())
        # Sort modules descending by number of students to drastically reduce branching
        all_modules.sort(key=lambda m: len(self.studentAssignedToModule.get(m, set())), reverse=True)

        count = 0
        pq = []
        visited = set()  # FIX 4: track explored states
        
        # Track the best schedule found (fewest remaining)
        best_schedule = []
        best_remaining_count = float('inf')

        initial_f = self.f_function(all_modules, [])
        heapq.heappush(pq, (initial_f, count, [], all_modules))
        count += 1

        while pq:
            # Check time limit
            if time_limit_sec is not None and (time.perf_counter() - start_time) > time_limit_sec:
                with open("scratch/astar_debug.txt", "w") as f:
                    f.write(f"TIMED OUT! Time elapsed: {time.perf_counter() - start_time}\n")
                    f.write(f"Best remaining: {best_remaining_count}\n")
                self.schedule = best_schedule
                return "Success!" if best_remaining_count == 0 else "Partial Solution"

            current_f, _, current_schedule, remaining = heapq.heappop(pq)
            
            if len(remaining) < best_remaining_count:
                best_remaining_count = len(remaining)
                best_schedule = current_schedule

            # --- FIX 4: build a hashable state key and skip if already explored ---
            # We MUST include the placement details (day, start, rooms) in the state key.
            # Otherwise, backtracking is impossible because it will assume any configuration
            # with the same set of exams has already been explored!
            state_key = frozenset(
                (e['exam'], e['day'], e['start'], frozenset(e['rooms'])) 
                for e in current_schedule
            )
            if state_key in visited:
                continue
            visited.add(state_key)
            # --------------------------------------------------------------------

            if not remaining:
                with open("scratch/astar_debug.txt", "w") as f:
                    f.write(f"SUCCESS EARLY! Time elapsed: {time.perf_counter() - start_time}\n")
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

        with open("scratch/astar_debug.txt", "w") as f:
            f.write(f"Stopped. Best schedule length: {len(best_schedule)}\n")
            f.write(f"Remaining: {best_remaining_count}\n")
            f.write(f"Queue empty? {len(pq) == 0}\n")
            f.write(f"Time elapsed: {time.perf_counter() - start_time}\n")
            
        # Search exhausted
        self.schedule = best_schedule
        return "Success!" if best_remaining_count == 0 else "Partial Solution"


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
    "room_1": 120, 
    "room_2": 120, 
    "room_3": 120, 
    "room_4": 120, 
    "room_5": 120, 
    "room_6": 120, 
    "room_7": 120, 
    "room_8": 120, 
    }

    # Tight timeline to force conflicts
    from_time = "09:00"
    to_time = "15:00" 
    days_str = "Mond-01-06-2006, Tues-02-06-2006, Wed-03-06-2006, Thur-04-06-2006, Sat-06-06-2006, Sun-07-06-2006, Mon-08-06-2006"

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
        for i in range (1,181):
            exam_student_data.append((module,f"S4_{i}"))

    for module in fifth_year_modules:
        for i in range (1,101):
            exam_student_data.append((module,f"S5_{i}"))
    
    my_scheduler = schedule(
        exam_student_data, room_capacities,
        from_time, to_time, days_str, durations
    )

    print("🚀 Starting A* Search... This may take a moment given the dataset size.")
    result = my_scheduler.AstarSearch()

    if result == "Success!":
        print("\n" + "="*100)
        print(f"{'EXAM NAME':<40} | {'DAY':<18} | {'TIME':<15} | {'ROOMS'}")
        print("="*100)
        
        # Sort by day and then by start time for a clear calendar view
        sorted_schedule = sorted(my_scheduler.schedule, key=lambda e: (e['day'], e['start']))
        
        for entry in sorted_schedule:
            # --- Format Start Time ---
            s_hour = int(entry['start'])
            s_min = int(round((entry['start'] - s_hour) * 60))
            start_clock = f"{s_hour:02d}:{s_min:02d}"
            
            # --- Format End Time ---
            e_hour = int(entry['end'])
            e_min = int(round((entry['end'] - e_hour) * 60))
            end_clock = f"{e_hour:02d}:{e_min:02d}"
            
            rooms_str = ", ".join(entry['rooms'])
            
            print(f"{entry['exam']:<40} | {entry['day']:<18} | {start_clock} - {end_clock} | {rooms_str}")
            
        print("="*100)
    else:
        print("❌ No valid schedule could be found with these constraints.")


class AStarScheduler:
    """
    Adapter class to bridge the new A* `schedule` logic with the FastAPI `main.py` interface.
    Translates the API's index-based domain into the native A* domain and maps the output back.
    """
    def __init__(self, exam_students, room_timeslot, enrollments):
        self.exam_students = exam_students
        self.room_timeslot = room_timeslot
        self.enrollments = enrollments

    def run(self, time_limit_sec=None, progress_callback=None):
        import time
        start = time.perf_counter()
        
        # 1. Translate API inputs into native schedule class format
        exam_student_tuples = []
        exam_duration = {}
        course_names = []
        for i, students_set in enumerate(self.exam_students):
            course_name = f"EXAM_ID_{i}"
            course_names.append(course_name)
            exam_duration[course_name] = 2.0  # Default to 2 hours
            
            # If an exam has no students, add a dummy student so A* knows it exists
            if not students_set:
                exam_student_tuples.append((course_name, f"DUMMY_{i}"))
            else:
                for student in students_set:
                    exam_student_tuples.append((course_name, student))
                
        room_capacity = {}
        for room, _ in self.room_timeslot:
            room_capacity[room.name] = room.capacity
            
        days_set = set()
        from_hour = 24.0
        to_hour = 0.0
        
        for _, slot in self.room_timeslot:
            # Parse dates like "2026-06-01 09:00:00" or just "2026-06-01"
            parts = slot.date.split(" ")
            day_str = parts[0].strip()
            time_str = parts[1].strip() if len(parts) > 1 else "09:00:00"
            days_set.add(day_str)
            
            try:
                h, m, *_ = map(int, time_str.split(":"))
                hour_float = h + m / 60.0
                from_hour = min(from_hour, hour_float)
                to_hour = max(to_hour, hour_float + 4.0)
            except:
                from_hour = min(from_hour, 9.0)
                to_hour = max(to_hour, 18.0)
                
        to_hour = max(to_hour, 18.0)
                
        days_str = ", ".join(sorted(days_set))
        if not days_str:
            days_str = "Monday"  # Fallback
            
        from_time = f"{int(from_hour):02d}:{int((from_hour % 1) * 60):02d}"
        to_time = f"{int(to_hour):02d}:00"
        
        # Ensure we have at least something to schedule
        if not exam_student_tuples:
            return [], 0.0, 0, time.perf_counter() - start

        if progress_callback:
            progress_callback(10, "Initializing A* environment...")
            
        # 2. Initialize and run native A* logic
        my_scheduler = schedule(
            exam_student_tuples, 
            room_capacity, 
            from_time, 
            to_time, 
            days_str, 
            exam_duration
        )
        
        if progress_callback:
            progress_callback(50, "Executing A* state-space search...")
            
        # Run optimized search
        my_scheduler.AstarSearch(time_limit_sec=time_limit_sec)
        
        # 3. Translate native output back to API's 1D assignment array
        if progress_callback:
            progress_callback(90, "Translating schedule back to UI format...")

        assignment = [None] * len(self.exam_students)
        
        from server.models import Timeslot
        
        for entry in my_scheduler.schedule:
            course_name = entry['exam']
            try:
                idx = course_names.index(course_name)
            except ValueError:
                continue
                
            # A* can allocate multiple rooms. We must combine them into a single "Room" object
            # so the UI and constraint checker don't incorrectly flag a capacity violation.
            combined_room_name = " + ".join(entry['rooms']) if entry['rooms'] else list(room_capacity.keys())[0]
            total_capacity = sum(room_capacity[r] for r in entry['rooms']) if entry['rooms'] else list(room_capacity.values())[0]
            
            # Format the exact time generated by the A* algorithm
            sh = int(entry['start'])
            sm = int(round((entry['start'] - sh) * 60))
            exact_time_str = f"{sh:02d}:{sm:02d}:00"
            exact_date_str = f"{entry['day']} {exact_time_str}"
            
            # Find or create the corresponding composite Room object
            from server.models import Room
            
            target_room = None
            for r, _ in self.room_timeslot:
                if r.name == combined_room_name:
                    target_room = r
                    break
                    
            if target_room is None:
                target_room = Room(combined_room_name, total_capacity)
                
            # Create a new Timeslot matching exactly what A* scheduled
            # and append it to the shared list so the UI can render the 30-min precision.
            new_slot = Timeslot(exact_date_str)
            new_index = len(self.room_timeslot)
            self.room_timeslot.append((target_room, new_slot))
            
            assignment[idx] = new_index
                
        elapsed = time.perf_counter() - start
        assigned_count = sum(1 for a in assignment if a is not None)
        fitness = assigned_count / len(self.exam_students) if self.exam_students else 0.0
        
        if progress_callback:
            progress_callback(100, f"Finished. Assigned {assigned_count}/{len(self.exam_students)} exams.")

        return assignment, fitness, len(my_scheduler.schedule), elapsed


if __name__ == "__main__":
    test()