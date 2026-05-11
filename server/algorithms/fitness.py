"""
Shared fitness evaluation for all scheduling algorithms.
"""


def compute_fitness(assignment, exam_students, room_timeslot, total_exams=None):
    """
    Compute schedule fitness. Works with partial assignments (None values skipped).
    Higher is better. Returns 0.0 for empty assignments.
    """
    if total_exams is None:
        total_exams = len(assignment)

    assigned_indices = [i for i in range(len(assignment)) if assignment[i] is not None]
    assigned_count = len(assigned_indices)
    if assigned_count == 0:
        return 0.0

    consecutive_exams_penalty = 0
    total_mutual_students = 0
    for idx_a in range(len(assigned_indices)):
        i = assigned_indices[idx_a]
        for idx_b in range(idx_a + 1, len(assigned_indices)):
            j = assigned_indices[idx_b]
            overlap = len(exam_students[i] & exam_students[j])
            total_mutual_students += overlap
            if room_timeslot[assignment[i]][1].same_date_as(room_timeslot[assignment[j]][1]):
                consecutive_exams_penalty += overlap

    late_exams = sum(1 for i in assigned_indices if room_timeslot[assignment[i]][1].is_late)

    efficient_allocation_factor = 0
    for i in assigned_indices:
        n = len(exam_students[i])
        c = room_timeslot[assignment[i]][0].capacity
        if c > 0:
            efficient_allocation_factor += n / c

    if total_mutual_students == 0:
        penalty_factor = 1 + late_exams / assigned_count
    else:
        penalty_factor = (1 + late_exams / assigned_count
                         + 2 * (consecutive_exams_penalty / total_mutual_students))

    fitness_value = (efficient_allocation_factor / assigned_count) / penalty_factor

    completeness = assigned_count / total_exams
    return fitness_value * completeness


def compute_ga_fitness(dna, exam_students, room_timeslot):
    """
    GA fitness with graduated penalty for infeasible solutions.
    Negative for invalid (gradient toward feasibility), positive for valid.
    """
    size = len(dna)

    room_conflicts = 0
    student_conflicts = 0
    capacity_violations = 0

    for i in range(size):
        for j in range(i + 1, size):
            if dna[i] == dna[j]:
                room_conflicts += 1

    for i in range(size):
        for j in range(i + 1, size):
            if len(exam_students[i] & exam_students[j]) > 0:
                if room_timeslot[dna[i]][1] == room_timeslot[dna[j]][1]:
                    student_conflicts += 1

    for i in range(size):
        if room_timeslot[dna[i]][0].capacity < len(exam_students[i]):
            capacity_violations += 1

    total_violations = room_conflicts + student_conflicts + capacity_violations

    if total_violations > 0:
        max_possible = size * (size - 1) // 2 + size
        return -(total_violations / max_possible)

    return compute_fitness(dna, exam_students, room_timeslot)
