"""Shared scoring and validation helpers for scheduler algorithms."""


def conflict_degrees(exam_students: list[set]) -> list[int]:
    degrees = []
    for i, students in enumerate(exam_students):
        degree = 0
        for j, other in enumerate(exam_students):
            if i != j and not students.isdisjoint(other):
                degree += 1
        degrees.append(degree)
    return degrees


def can_place(exam_idx: int, rt_idx: int, assignment: list, exam_students: list[set], room_timeslot: list[tuple]) -> bool:
    room, timeslot = room_timeslot[rt_idx]
    if room.capacity < len(exam_students[exam_idx]):
        return False
    if rt_idx in assignment:
        return False
    for other_exam, other_rt in enumerate(assignment):
        if other_rt is None:
            continue
        _, other_timeslot = room_timeslot[other_rt]
        if timeslot == other_timeslot and not exam_students[exam_idx].isdisjoint(exam_students[other_exam]):
            return False
    return True


def greedy_assignment(exam_students: list[set], room_timeslot: list[tuple], enrollments: list[int] | None = None) -> list:
    degrees = conflict_degrees(exam_students)
    if enrollments is None:
        enrollments = [len(students) for students in exam_students]
    order = sorted(
        range(len(exam_students)),
        key=lambda i: (degrees[i], enrollments[i]),
        reverse=True,
    )
    assignment = [None] * len(exam_students)
    for exam_idx in order:
        candidates = []
        for rt_idx, (room, timeslot) in enumerate(room_timeslot):
            if not can_place(exam_idx, rt_idx, assignment, exam_students, room_timeslot):
                continue
            waste = room.capacity - len(exam_students[exam_idx])
            candidates.append((timeslot.day, timeslot.hour, timeslot.minute, timeslot.is_late, waste, rt_idx))
        if candidates:
            assignment[exam_idx] = min(candidates)[-1]
    return assignment


def hard_violations(assignment: list, exam_students: list[set], room_timeslot: list[tuple]) -> int:
    violations = 0
    used = set()
    for exam_idx, rt_idx in enumerate(assignment):
        if rt_idx is None or not isinstance(rt_idx, int) or rt_idx < 0 or rt_idx >= len(room_timeslot):
            violations += 1
            continue
        room, _ = room_timeslot[rt_idx]
        if room.capacity < len(exam_students[exam_idx]):
            violations += 1
        if rt_idx in used:
            violations += 1
        used.add(rt_idx)

    for i in range(len(assignment)):
        if assignment[i] is None:
            continue
        for j in range(i + 1, len(assignment)):
            if assignment[j] is None:
                continue
            if not exam_students[i].isdisjoint(exam_students[j]):
                if room_timeslot[assignment[i]][1] == room_timeslot[assignment[j]][1]:
                    violations += 1
    return violations


def fitness(assignment: list, exam_students: list[set], room_timeslot: list[tuple]) -> float:
    if not assignment:
        return 0.0
    assigned = [i for i, gene in enumerate(assignment) if isinstance(gene, int)]
    if not assigned:
        return 0.0
    hard = hard_violations(assignment, exam_students, room_timeslot)
    if hard:
        return 1.0 / (1.0 + 1000.0 * hard)

    consecutive_penalty = 0
    total_mutual_students = 0
    for left_pos, i in enumerate(assigned):
        for j in assigned[left_pos + 1:]:
            overlap = len(exam_students[i] & exam_students[j])
            total_mutual_students += overlap
            if room_timeslot[assignment[i]][1].day == room_timeslot[assignment[j]][1].day:
                consecutive_penalty += overlap

    late_exams = sum(1 for i in assigned if room_timeslot[assignment[i]][1].is_late)
    efficient_allocation = 0.0
    for i in assigned:
        n = len(exam_students[i])
        c = room_timeslot[assignment[i]][0].capacity
        efficient_allocation += -4 * n * (n - c) / (c ** 2) if c else 0

    penalty_factor = 1 + late_exams / len(assigned)
    if total_mutual_students:
        penalty_factor += 2 * (consecutive_penalty / total_mutual_students)
    completeness = len(assigned) / len(assignment)
    return completeness * (efficient_allocation / len(assigned)) / penalty_factor
