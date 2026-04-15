"""
Genetic Algorithm for exam scheduling.
Ported from notebook/algorithms.ipynb with integrated progress reporting.
"""
import random
from typing import Callable, Optional


class Chromosome:
    """One candidate schedule: each gene is an index into the room×timeslot list."""

    def __init__(self, size: int, domain: list[int], mutation_probability: float, dna: Optional[list[int]] = None):
        self.mutation = mutation_probability
        self.size = size
        self.domain = domain
        if dna is None:
            self.dna = [random.choice(domain) for _ in range(size)]
        else:
            self.dna = dna

    def mutate(self):
        for i in range(self.size):
            if random.random() <= self.mutation:
                self.dna[i] = random.choice(self.domain)


class GeneticAlgorithm:
    """Evolves a population of Chromosomes using crossover + mutation."""

    def __init__(self, population: list[Chromosome], rooms_timeslots: list[tuple], exam_students: list[set]):
        self.population = population
        self.room_timeslot = rooms_timeslots
        self.exam_students = exam_students

    def crossover(self, chromo1: Chromosome, chromo2: Chromosome):
        crossover_point = chromo1.size // 2
        child1 = Chromosome(
            chromo1.size, chromo1.domain, chromo1.mutation,
            chromo1.dna[:crossover_point] + chromo2.dna[crossover_point:]
        )
        child2 = Chromosome(
            chromo1.size, chromo1.domain, chromo1.mutation,
            chromo2.dna[:crossover_point] + chromo1.dna[crossover_point:]
        )
        child1.mutate()
        child2.mutate()
        return child1, child2

    def fitness(self, chromo: Chromosome) -> float:
        # ── Hard constraints ──
        for i in range(chromo.size):
            for j in range(i + 1, chromo.size):
                if chromo.dna[i] == chromo.dna[j]:
                    return 0

        for i in range(chromo.size):
            for j in range(i + 1, chromo.size):
                same_students = len(self.exam_students[i] & self.exam_students[j]) > 0
                same_timeslot = self.room_timeslot[chromo.dna[i]][1] == self.room_timeslot[chromo.dna[j]][1]
                if same_students and same_timeslot:
                    return 0

        for i in range(chromo.size):
            if self.room_timeslot[chromo.dna[i]][0].capacity < len(self.exam_students[i]):
                return 0

        # ── Soft constraints ──
        consecutive_exams_penalty = 0
        total_mutual_students = 0
        for i in range(chromo.size):
            for j in range(i + 1, chromo.size):
                overlap = len(self.exam_students[i] & self.exam_students[j])
                total_mutual_students += overlap
                if self.room_timeslot[chromo.dna[i]][1].day == self.room_timeslot[chromo.dna[j]][1].day:
                    consecutive_exams_penalty += overlap

        late_exams = 0
        total_exams = chromo.size
        for i in range(chromo.size):
            if self.room_timeslot[chromo.dna[i]][1].is_late:
                late_exams += 1

        efficient_allocation_factor = 0
        for i in range(chromo.size):
            n = len(self.exam_students[i])
            c = self.room_timeslot[chromo.dna[i]][0].capacity
            efficient_allocation_factor += -4 * n * (n - c) / (c ** 2)

        if total_mutual_students == 0:
            penalty_factor = 1 + late_exams / total_exams
        else:
            penalty_factor = 1 + late_exams / total_exams + 2 * (consecutive_exams_penalty / total_mutual_students)

        fitness_value = (efficient_allocation_factor / total_exams) / penalty_factor
        return fitness_value

    def selection(self):
        population_fitness = [self.fitness(p) for p in self.population]

        # Elitism
        next_population = []
        best_index = max(range(len(self.population)), key=lambda i: population_fitness[i])
        next_population.append(self.population[best_index])

        # Roulette wheel parent selection
        total_fitness = sum(population_fitness)
        target_parent_count = max(2, len(self.population) // 2)

        while len(next_population) < target_parent_count:
            if total_fitness == 0:
                selected = random.choice(self.population)
            else:
                r = random.uniform(0, total_fitness)
                acc = 0
                selected = self.population[-1]
                for chromo, fit in zip(self.population, population_fitness):
                    acc += fit
                    if acc >= r:
                        selected = chromo
                        break
            next_population.append(selected)

        if len(next_population) % 2 == 1:
            next_population.append(random.choice(next_population))

        children = []
        while len(next_population) + len(children) < len(self.population):
            parent1, parent2 = random.sample(next_population, 2)
            child1, child2 = self.crossover(parent1, parent2)
            children.extend([child1, child2])

        self.population = (next_population + children)[:len(self.population)]
        return self.population

    def run(self, generations: int, progress_callback: Optional[Callable] = None) -> Chromosome:
        """
        Run the genetic algorithm for the given number of generations.
        
        Args:
            generations: Number of generations to evolve.
            progress_callback: Optional callback(percent, message) for progress updates.
        """
        for epoch in range(generations):
            self.selection()

            if progress_callback and (epoch % 5 == 0 or epoch == generations - 1):
                pct = ((epoch + 1) / generations) * 100
                best_fit = max(self.fitness(p) for p in self.population)
                progress_callback(
                    pct,
                    f"Generation {epoch + 1}/{generations} — best fitness: {best_fit:.4f}"
                )

        return max(self.population, key=self.fitness)
