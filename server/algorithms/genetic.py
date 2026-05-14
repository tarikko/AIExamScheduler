"""Genetic algorithm with cached scoring and constraint-aware seeding."""
import random
import time
from collections import defaultdict
from typing import Callable, Optional

from server.algorithms.common import fitness, greedy_assignment, hard_violations


class Chromosome:
    """One candidate schedule: each gene is an index into the room-timeslot list."""

    def __init__(self, size: int, domain: list[int], mutation_probability: float, dna: Optional[list[int]] = None):
        self.mutation = mutation_probability
        self.size = size
        self.domain = domain
        self.dna = list(dna) if dna is not None else [random.choice(domain) for _ in range(size)]
        self.cached_fitness: Optional[float] = None

    def mutate(self):
        changed = False
        for i in range(self.size):
            if random.random() <= self.mutation:
                self.dna[i] = random.choice(self.domain)
                changed = True
        if changed:
            self.cached_fitness = None


class GeneticAlgorithm:
    """Evolve schedules using elitism, roulette selection, crossover, and mutation."""

    def __init__(self, population: list[Chromosome], rooms_timeslots: list[tuple], exam_students: list[set]):
        self.population = population
        self.room_timeslot = rooms_timeslots
        self.exam_students = exam_students
        self.exam_count = len(exam_students)
        self.room_capacity = [room.capacity for room, _ in rooms_timeslots]
        self.slot_index_by_rt = []
        self.slot_day_by_rt = []
        self.slot_is_late_by_rt = []
        slot_ids = {}
        for _, slot in rooms_timeslots:
            if slot.date not in slot_ids:
                slot_ids[slot.date] = len(slot_ids)
        for _, slot in rooms_timeslots:
            self.slot_index_by_rt.append(slot_ids[slot.date])
            self.slot_day_by_rt.append(slot.day)
            self.slot_is_late_by_rt.append(slot.is_late)
        self.enrollments = [len(students) for students in exam_students]
        self.conflict_pairs = self._build_conflict_pairs()

    def _build_conflict_pairs(self) -> list[tuple[int, int, int]]:
        student_exams = defaultdict(list)
        for exam_idx, students in enumerate(self.exam_students):
            for student in students:
                student_exams[student].append(exam_idx)

        pair_weights = defaultdict(int)
        for exams in student_exams.values():
            exams = sorted(set(exams))
            for left_pos, i in enumerate(exams):
                for j in exams[left_pos + 1:]:
                    pair_weights[(i, j)] += 1

        return [(i, j, overlap) for (i, j), overlap in pair_weights.items()]

    def crossover(self, chromo1: Chromosome, chromo2: Chromosome):
        point = chromo1.size // 2
        child1 = Chromosome(
            chromo1.size,
            chromo1.domain,
            chromo1.mutation,
            chromo1.dna[:point] + chromo2.dna[point:],
        )
        child2 = Chromosome(
            chromo1.size,
            chromo1.domain,
            chromo1.mutation,
            chromo2.dna[:point] + chromo1.dna[point:],
        )
        child1.mutate()
        child2.mutate()
        return child1, child2

    def fitness(self, chromo: Chromosome) -> float:
        if chromo.cached_fitness is None:
            chromo.cached_fitness = self._fitness_fast(chromo.dna)
        return chromo.cached_fitness

    def _fitness_fast(self, dna: list[int]) -> float:
        if not dna:
            return 0.0

        used_room_timeslots = set()
        assigned_count = 0
        hard = 0
        late_exams = 0
        efficient_allocation = 0.0

        for exam_idx, gene in enumerate(dna):
            if not isinstance(gene, int) or gene < 0 or gene >= len(self.room_timeslot):
                hard += 1
                continue
            assigned_count += 1
            if gene in used_room_timeslots:
                hard += 1
            used_room_timeslots.add(gene)

            capacity = self.room_capacity[gene]
            enrollment = self.enrollments[exam_idx]
            if capacity < enrollment:
                hard += 1
            if self.slot_is_late_by_rt[gene]:
                late_exams += 1
            if capacity:
                efficient_allocation += -4 * enrollment * (enrollment - capacity) / (capacity ** 2)

        total_mutual_students = 0
        consecutive_penalty = 0
        for i, j, overlap in self.conflict_pairs:
            left = dna[i]
            right = dna[j]
            if not isinstance(left, int) or not isinstance(right, int):
                continue
            if left < 0 or right < 0 or left >= len(self.room_timeslot) or right >= len(self.room_timeslot):
                continue
            total_mutual_students += overlap
            if self.slot_index_by_rt[left] == self.slot_index_by_rt[right]:
                hard += 1
            if self.slot_day_by_rt[left] == self.slot_day_by_rt[right]:
                consecutive_penalty += overlap

        if assigned_count == 0:
            return 0.0
        if hard:
            return (assigned_count / len(dna)) / (1.0 + 1000.0 * hard)

        penalty_factor = 1 + late_exams / assigned_count
        if total_mutual_students:
            penalty_factor += 2 * (consecutive_penalty / total_mutual_students)
        completeness = assigned_count / len(dna)
        return completeness * (efficient_allocation / assigned_count) / penalty_factor

    def _seed_population(self):
        if self.exam_count > 300:
            return None
        seed = greedy_assignment(self.exam_students, self.room_timeslot)
        if not self.population or not seed:
            return seed

        domain = self.population[0].domain
        mutation = self.population[0].mutation
        self.population[0] = Chromosome(len(seed), domain, mutation, dna=seed)
        for idx in range(1, min(len(self.population), max(2, len(self.population) // 3))):
            dna = list(seed)
            swaps = max(1, len(dna) // 20)
            for _ in range(swaps):
                pos = random.randrange(len(dna))
                dna[pos] = random.choice(domain)
            self.population[idx] = Chromosome(len(seed), domain, mutation, dna=dna)
        return seed

    def selection(self) -> tuple[Chromosome, float]:
        population_fitness = [self.fitness(chromo) for chromo in self.population]
        best_index = max(range(len(self.population)), key=lambda i: population_fitness[i])
        best = self.population[best_index]
        best_score = population_fitness[best_index]
        next_population = [best]

        total_fitness = sum(max(0.0, score) for score in population_fitness)
        target_parent_count = max(2, len(self.population) // 2)
        while len(next_population) < target_parent_count:
            if total_fitness <= 0:
                selected = random.choice(self.population)
            else:
                r = random.uniform(0, total_fitness)
                acc = 0.0
                selected = self.population[-1]
                for chromo, score in zip(self.population, population_fitness):
                    acc += max(0.0, score)
                    if acc >= r:
                        selected = chromo
                        break
            next_population.append(selected)

        if len(next_population) % 2 == 1:
            next_population.append(random.choice(next_population))

        children = []
        while len(next_population) + len(children) < len(self.population):
            parent1, parent2 = random.sample(next_population, 2)
            children.extend(self.crossover(parent1, parent2))
        self.population = (next_population + children)[:len(self.population)]
        return best, best_score

    def run(
        self,
        generations: int,
        progress_callback: Optional[Callable] = None,
        time_limit_sec: Optional[float] = None,
    ) -> Chromosome:
        start = time.perf_counter()
        seed = self._seed_population()
        best = self.population[0] if self.population else Chromosome(0, [], 0.0, dna=[])
        best_score = self.fitness(best) if self.population else 0.0

        for epoch in range(generations):
            if time_limit_sec is not None and time.perf_counter() - start >= time_limit_sec:
                break
            candidate, candidate_score = self.selection()
            if candidate_score > best_score:
                best, best_score = candidate, candidate_score
            if progress_callback and (epoch % 5 == 0 or epoch == generations - 1):
                pct = ((epoch + 1) / max(1, generations)) * 100
                progress_callback(pct, f"GA generation {epoch + 1}/{generations}, best fitness {best_score:.4f}")

        if seed and hard_violations(best.dna, self.exam_students, self.room_timeslot):
            fallback = Chromosome(best.size, best.domain, best.mutation, dna=seed)
            fallback.cached_fitness = fitness(seed, self.exam_students, self.room_timeslot)
            return fallback
        return best
