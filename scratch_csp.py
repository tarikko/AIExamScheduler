import time
from copy import deepcopy

class CSP:
    def __init__(self,exams: list[Exam],room_timeslot: list[tuple[Room,Timeslot]]):
        self.number_of_exams = len(exams)
        self.exams = exams
        self.room_timeslot = room_timeslot
        n = self.number_of_exams
        # a graph where vertices are exams and two vertices are connected with an edge if their students sets overlap
        self.exam_neighbours = [[] for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                m = len(self.exams[i].students & self.exams[j].students)
                if m > 0:
                    self.exam_neighbours[i].append((j,m))

        self.exam_overlap = [[len(self.exams[i].students & self.exams[j].students) for j in range(self.number_of_exams)] for i in range(self.number_of_exams)]
        # the start time for (room,timeslot) pair
        self.start_time = [timeslot.to_epoch() for room,timeslot in self.room_timeslot]
        # the end time of the exam when assigned to a particular (room,timeslot) pair
        self.end_time = [[timeslot.add_time(minutes=exam.duration) for room,timeslot in self.room_timeslot] for exam in self.exams]  
        

        self.domain = {i: set(range(len(self.room_timeslot))) for i in range(self.number_of_exams)}

        # domains reduction enforcing node consistency by removing possible assignments of rooms
        # where their capacity is less than the number of students in the exam
        # NODE CONSISTENCY
        for e in range(self.number_of_exams):
            for v in list(self.domain[e]):
                if not self.unary_hard_constraint(e,v):
                    self.domain[e].remove(v)
            if len(self.domain[e]) == 0: # empty domain no solution exists
                raise ValueError(f"CSP cannot find a solution since there is an exam whose number of students surpasses the capacity of all rooms\nExam code is: {self.exams[e].code}")

    def binary_hard_constraint(self,e1,e2,v1,v2):
        ''' 
        e1: index of the first exam 
        e2: index of the second exam
        v1: index of pair (room,timeslot) to be assigned to e1
        v2: index of pair (room,timeslot) to be assigned to e2
        '''
        # no two exams can have the same (room,timeslot)
        if v1 == v2:
            return False
        # no student can sit for two different exams at the same time
        same_students = self.exam_overlap[e1][e2] > 0 
        exam_e1_start = self.start_time[v1]
        exam_e2_start = self.start_time[v2]
        exam_e1_end = self.end_time[e1][v1]
        exam_e2_end = self.end_time[e2][v2]
        conflicting_timeslots = not (exam_e1_start > exam_e2_end or exam_e2_start > exam_e1_end)
        if same_students and conflicting_timeslots:
            return False

        return True

    def unary_hard_constraint(self,e1,v1):
        # room capacity must exceed number of students
        if len(self.exams[e1].students) > self.room_timeslot[v1][0].capacity:
            return False

        return True
    
    def calc_consecutive_exams(self,assignment: list,current_exam_idx,proposed_value):
        overlap = 0

        for i in range(self.number_of_exams):
            if assignment[i] is not None and self.room_timeslot[assignment[i]][1].calendar_date == self.room_timeslot[proposed_value][1].calendar_date:
                overlap += self.exam_overlap[i][current_exam_idx]

        return overlap

    def solution_evaluation(self,schedule):
        # weights
        hard_duplicate_weight = 20.0
        hard_student_conflict_weight = 10.0
        soft_consecutive_exams_weight = 3
        soft_late_exams_weight = 0.5
        soft_efficient_allocation_weight = 2.0

        # scores
        duplicate_pairs = 0
        student_time_conflicts = 0
        consecutive_exams = 0
        late_exams = 0
        efficient_allocation_score = 0

        days = [0] * self.number_of_exams
        is_late = [False] * self.number_of_exams

        used = set()
        for i in range(self.number_of_exams):
            gene = schedule[i]
            if gene in used:
                duplicate_pairs += 1
            else:
                used.add(gene)

            room, slot = self.room_timeslot[gene]

            days[i] = slot.day
            is_late[i] = slot.is_late
            efficient_allocation_score += room_utilization_score(
                room_capacity=room.capacity,
                number_of_students=len(self.exams[i].students),
            )

            if is_late[i]:
                late_exams += 1

        for i in range(self.number_of_exams):
            for j, overlap in self.exam_neighbours[i]:
                if max(self.start_time[schedule[i]], self.start_time[schedule[j]]) < min(self.end_time[i][schedule[i]], self.end_time[j][schedule[j]]):
                    student_time_conflicts += overlap

                if days[i] == days[j]:
                    consecutive_exams += overlap

        hard_score =  -(hard_duplicate_weight * duplicate_pairs + hard_student_conflict_weight * student_time_conflicts)
        soft_score =  soft_efficient_allocation_weight * efficient_allocation_score - soft_consecutive_exams_weight * consecutive_exams - soft_late_exams_weight * late_exams
        final_score = hard_score + soft_score

        return final_score

    def run(self, time_limit_sec=5.0, print_details=False, first_find=False):
        start = time.perf_counter()
        deadline = start + time_limit_sec

        best_assignment = None
        best_fitness = float('-inf')

        def solve(assignment: list, not_assigned: set[int], domains: dict):
            nonlocal best_assignment, best_fitness

            if time.perf_counter() >= deadline:
                return True 

            if not not_assigned:
                sol_fitness = self.solution_evaluation(assignment)
                if sol_fitness > best_fitness:
                    best_fitness = sol_fitness
                    best_assignment = assignment.copy()
                    if print_details:
                        print(f"A new best solution was found with score: {best_fitness}\\n")
                if first_find:
                    return True 
                return False

            curr = min(not_assigned, key=lambda i: len(domains[i]))
            not_assigned.remove(curr)

            values = sorted(
                domains[curr],
                key=lambda v: (
                    self.room_timeslot[v][1].is_late,
                    self.calc_consecutive_exams(assignment, curr, v),
                    -room_utilization_score(
                        self.room_timeslot[v][0].capacity,
                        len(self.exams[curr].students)
                    )
                )
            )

            for possible_value in values:
                if time.perf_counter() >= deadline:
                    break
                
                invalid_possible_value = False
                trail = []
                for e in not_assigned:
                    to_remove = set()
                    for v in domains[e]:
                        if not self.binary_hard_constraint(curr, e, possible_value, v):
                            to_remove.add(v)
                            trail.append((e, v))

                    domains[e] -= to_remove
                    if not domains[e]:
                        invalid_possible_value = True
                        break

                if not invalid_possible_value:
                    assignment[curr] = possible_value
                    if solve(assignment, not_assigned, domains):
                        return True
                    assignment[curr] = None
                    
                while trail:
                    var, val = trail.pop()
                    domains[var].add(val)
                
            not_assigned.add(curr)
            return False

        init_not_assigned = set(range(self.number_of_exams))
        init_assignment = [None] * self.number_of_exams

        solve(assignment=init_assignment, not_assigned=init_not_assigned, domains=deepcopy(self.domain))

        elapsed = time.perf_counter() - start
        if best_assignment:
            print(f'CSP search took {elapsed:.2f}s; best fitness so far: {best_fitness:.6f}')
        else:
            print(f'CSP search took {elapsed:.2f}s; no feasible solution found yet')

        return best_assignment