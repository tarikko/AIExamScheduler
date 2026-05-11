"""
Genetic Algorithm for exam scheduling.
Ported from notebook/algorithms.ipynb with integrated progress reporting.
"""
import random
from typing import Callable, Optional

from server.algorithms.fitness import compute_ga_fitness


class Chromosome:
    """One candidate schedule: each gene is an index into the room x timeslot list."""

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
        return compute_ga_fitness(chromo.dna, self.exam_students, self.room_timeslot)

    def _tournament_select(self, population_fitness, k=3):
        candidates = random.sample(range(len(self.population)), k)
        winner = max(candidates, key=lambda i: population_fitness[i])
        return self.population[winner]

    def selection(self):
        population_fitness = [self.fitness(p) for p in self.population]

        next_population = []
        best_index = max(range(len(self.population)), key=lambda i: population_fitness[i])
        next_population.append(self.population[best_index])

        target_parent_count = max(2, len(self.population) // 2)

        while len(next_population) < target_parent_count:
            selected = self._tournament_select(population_fitness)
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
