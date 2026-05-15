"""CSP solver ported from the notebook with backend progress reporting."""
import time
from copy import deepcopy
from typing import Callable, Optional

from server.models import Exam, Room, Timeslot
from server.algorithms.utils import room_utilization_score
from server.algorithms.common import greedy_assignment

class CSP:
    """Backtracking CSP with MRV, forward checking, and a time limit."""
    
    def __init__(self, exams: list[Exam], room_timeslot: list[tuple[Room, Timeslot]]):
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

        # NODE CONSISTENCY
        for e in range(self.number_of_exams):
            for v in list(self.domain[e]):
                if not self.unary_hard_constraint(e,v):
                    self.domain[e].remove(v)
            if len(self.domain[e]) == 0:
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
        confilicting_rooms = conflicting_timeslots and (self.room_timeslot[v1][0] == self.room_timeslot[v2][0])
        if (same_students and conflicting_timeslots) or confilicting_rooms:
            return False

        return True

    def unary_hard_constraint(self,e1,v1):
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
        hard_room_conflict_weight = 10.0
        soft_consecutive_exams_weight = 3
        soft_late_exams_weight = 0.5
        soft_efficient_allocation_weight = 2.0

        # scores
        duplicate_pairs = 0
        student_time_conflicts = 0
        room_time_conflicts = 0
        consecutive_exams = 0
        late_exams = 0
        efficient_allocation_score = 0

        days = [0] * self.number_of_exams
        is_late = [False] * self.number_of_exams

        used = set()
        room_assignments = {}

        for i in range(self.number_of_exams):
            assigned = schedule[i]
            
            if assigned is None:
                continue

            if assigned in used:
                duplicate_pairs += 1
            else:
                used.add(assigned)

            room, slot = self.room_timeslot[assigned]
            room_assignments.setdefault(room, []).append((self.start_time[assigned], self.end_time[i][assigned]))

            days[i] = slot.day
            is_late[i] = slot.is_late
            efficient_allocation_score += room_utilization_score(
                room_capacity=room.capacity,
                number_of_students=len(self.exams[i].students),
            )

            if is_late[i]:
                late_exams += 1

        for i in range(self.number_of_exams):
            if schedule[i] is None:
                continue
            for j, overlap in self.exam_neighbours[i]:
                if schedule[j] is None:
                    continue
                if max(self.start_time[schedule[i]], self.start_time[schedule[j]]) < min(self.end_time[i][schedule[i]], self.end_time[j][schedule[j]]):
                    student_time_conflicts += overlap

                if days[i] == days[j]:
                    consecutive_exams += overlap

        for assignments in room_assignments.values():
            assignments.sort(key=lambda item: item[0])
            active_end = -1
            for start_time, end_time in assignments:
                if start_time < active_end:
                    room_time_conflicts += 1
                else:
                    active_end = end_time
                    continue

                if end_time > active_end:
                    active_end = end_time

        unassigned_penalty = sum(1 for gene in schedule if gene is None) * 100.0

        hard_score =  -(hard_duplicate_weight * duplicate_pairs + hard_student_conflict_weight * student_time_conflicts + hard_room_conflict_weight * room_time_conflicts + unassigned_penalty)
        soft_score =  soft_efficient_allocation_weight * efficient_allocation_score - soft_consecutive_exams_weight * consecutive_exams - soft_late_exams_weight * late_exams
        final_score = hard_score + soft_score

        return final_score

    def run(self, time_limit_sec=5.0, first_find=False, progress_callback: Optional[Callable] = None):
        start = time.perf_counter()
        deadline = start + time_limit_sec
        nodes_explored = 0
        last_progress_time = start

        # Use greedy fallback so we always return *something*
        exam_students_list = [e.students for e in self.exams]
        fallback = greedy_assignment(exam_students_list, self.room_timeslot, enrollments=[len(s) for s in exam_students_list])
        best_assignment = fallback
        best_fitness = self.solution_evaluation(fallback)

        def solve(assignment: list, not_assigned: set[int], domains: dict):
            nonlocal best_assignment, best_fitness, nodes_explored, last_progress_time

            now = time.perf_counter()
            if now >= deadline:
                return True 

            nodes_explored += 1

            if progress_callback and now - last_progress_time >= 0.2:
                pct = min(95.0, ((now - start) / max(time_limit_sec, 0.01)) * 100)
                progress_callback(pct, f"CSP explored {nodes_explored} nodes")
                last_progress_time = now

            if not not_assigned:
                sol_fitness = self.solution_evaluation(assignment)
                if sol_fitness > best_fitness:
                    best_fitness = sol_fitness
                    best_assignment = assignment.copy()
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
        if progress_callback:
            progress_callback(100, f"CSP done after {nodes_explored} nodes in {elapsed:.2f}s")
        return best_assignment, best_fitness, nodes_explored, elapsed