import random
import time
from utils import check_empty_domains

class Chromosome:
    def __init__(self,size,domain,mutation_probability,dna = None):
        if check_empty_domains(domain):
            raise ValueError("Empty domain was provided to the chromosome probably due to an exam's number of students exceeding all room capacities")

        self.mutation = mutation_probability # mutation rate
        self.size = size # length of the chormosome dna
        self.domain = domain # a list of lists where where each list[i] represent the values gene i can take
        used_values = set() # to enforce uniqueness of assignements of values so no two different exams are assigned the same (room,timeslot)
        if dna is None:
            self.dna = []
            for i in range(self.size):
                assigned = False
                for val in self.domain[i]:
                    if val not in used_values:
                        self.dna.append(val)
                        used_values.add(val)
                        assigned = True
                        break

                if not assigned:
                    raise ValueError("Could not initialize a chromosome there was insufficient range of values to accomodate all genes, i.e the set of legal values for a particular gene were exhausted and were used by other genes")
                
        else:
            self.dna = dna

    def mutate(self):
        for i in range(self.size):
            r = random.random()
            if r <= self.mutation:
                self.dna[i] = random.choice(self.domain[i])


class GeneticAlgorithm:
    def __init__(self,exams: list[Exam],rooms_timeslots: list[tuple[Room,Timeslot]],population: list[Chromosome] = None,population_size = 100):
        self.room_timeslot = rooms_timeslots
        self.exams = exams
        n = len(self.exams)
        # a graph where vertices are exams and two vertices are connected with an edge if their students sets overlap
        self.exam_neighbours = [[] for _ in range(n)]
        # elements are of the form (j,m) where 
        # j is the index of the neighbouring exam
        # m is the number of overlaping students
        for i in range(n):
            for j in range(i + 1,n):
                m = len(self.exams[i].students & self.exams[j].students)
                if m > 0:
                    self.exam_neighbours[i].append((j,m))

        # the start time for (room,timeslot) pair
        self.start_time = [timeslot.to_epoch() for room,timeslot in self.room_timeslot]
        # the end time of the exam when assigned to a particular (room,timeslot) pair
        self.end_time = [[timeslot.add_time(minutes=exam.duration) for room,timeslot in self.room_timeslot] for exam in self.exams]

        if population is not None:
            self.population = population
        else:
            # initialize a population
            num_exams = len(self.exams)
            num_room_timeslot = len(self.room_timeslot)
            # finding the domain of each gene
            domain = []
            for i in range(num_exams):
                domain_i = []
                num_of_students = len(self.exams[i].students)
                for j in range(num_room_timeslot):
                    if self.room_timeslot[j][0].capacity >= num_of_students:
                        domain_i.append(j)

                domain.append(domain_i)
            # creating the popualation list
            self.population = [Chromosome(size=num_exams,domain=domain,mutation_probability=1 / num_exams) for _ in range(population_size)]

    def _pmx_child(self,primary,secondary,start,end):
        # PMX helper to keep relative order and reduce duplicates
        size = len(primary)
        child = [None] * size
        child[start:end + 1] = primary[start:end + 1]

        mapping = {}
        for i in range(start, end + 1):
            mapping[secondary[i]] = primary[i]

        for i in range(size):
            if start <= i <= end:
                continue
            candidate = secondary[i]
            visited = set()
            while candidate in child and candidate in mapping and candidate not in visited:
                visited.add(candidate)
                candidate = mapping[candidate]
            child[i] = candidate

        for i in range(size):
            if child[i] is None:
                child[i] = primary[i]

        return child

    def crossover(self,chromo1 : Chromosome,chromo2 : Chromosome):
        n = chromo1.size
        if n < 2:
            child1 = Chromosome(chromo1.size,chromo1.domain,chromo1.mutation,chromo1.dna[:])
            child2 = Chromosome(chromo2.size,chromo2.domain,chromo2.mutation,chromo2.dna[:])
            return child1 , child2

        start, end = sorted(random.sample(range(n), 2))
        child1_dna = self._pmx_child(chromo1.dna, chromo2.dna, start, end)
        child2_dna = self._pmx_child(chromo2.dna, chromo1.dna, start, end)

        child1 = Chromosome(chromo1.size,chromo1.domain,chromo1.mutation,child1_dna)
        child2 = Chromosome(chromo2.size,chromo2.domain,chromo2.mutation,child2_dna)

        child1.mutate()
        child2.mutate()
        return child1 , child2

    def fitness(self,chromo: Chromosome):
        # weights
        hard_duplicate_weight = 20.0
        hard_capacity_weight = 20.0
        hard_student_conflict_weight = 10.0
        soft_consecutive_exams_weight = 3
        soft_late_exams_weight = 0.5
        soft_efficient_allocation_weight = 2.0

        # scores
        duplicate_pairs = 0
        capacity_violations = 0
        student_time_conflicts = 0
        consecutive_exams = 0
        late_exams = 0
        efficient_allocation_score = 0

        days = [0] * chromo.size
        is_late = [False] * chromo.size

        ## HARD CONSTRAINTS
        used = set()
        for i in range(chromo.size):
            gene = chromo.dna[i]
            if gene in used:
                duplicate_pairs += 1
            else:
                used.add(gene)

            room, slot = self.room_timeslot[gene]
            if room.capacity < len(self.exams[i].students):
                capacity_violations += 1

            days[i] = slot.calendar_date
            is_late[i] = slot.is_late
            efficient_allocation_score += room_utilization_score(
                room_capacity=room.capacity,
                number_of_students=len(self.exams[i].students),
            )

            if is_late[i]:
                late_exams += 1

        for i in range(chromo.size):
            for j, overlap in self.exam_neighbours[i]:
                if max(self.start_time[chromo.dna[i]], self.start_time[chromo.dna[j]]) < min(self.end_time[i][chromo.dna[i]], self.end_time[j][chromo.dna[j]]):
                    student_time_conflicts += overlap

                if days[i] == days[j]:
                    consecutive_exams += overlap

        hard_score =  -(hard_duplicate_weight * duplicate_pairs + hard_capacity_weight * capacity_violations + hard_student_conflict_weight * student_time_conflicts)
        soft_score =  soft_efficient_allocation_weight * efficient_allocation_score - soft_consecutive_exams_weight * consecutive_exams - soft_late_exams_weight * late_exams
        final_score = hard_score + soft_score

        return final_score

    def selection(self,selection_method = "tournament",k = 3):
        '''
        k is the sample size if selection_method = 'tournament' its irrelevant otherwise
        '''
        population_fitness = [self.fitness(p) for p in self.population]

        # elitism: always keep best chromosome
        next_population = []
        best_index = max(range(len(self.population)), key=lambda i: population_fitness[i])
        next_population.append(self.population[best_index])

        # roulette wheel parent selection
        if selection_method == "roulette":
            min_fit = min(population_fitness)
            if min_fit < 0:
                shifted_fitness = [fit - min_fit + 1e-6 for fit in population_fitness]
            else:
                shifted_fitness = population_fitness

            total_fitness = sum(shifted_fitness)
            target_parent_count = max(2, len(self.population) // 2)

            while len(next_population) < target_parent_count:
                if total_fitness <= 0:
                    selected = random.choice(self.population)
                else:
                    r = random.uniform(0, total_fitness)
                    acc = 0
                    selected = self.population[-1]
                    for chromo, fit in zip(self.population, shifted_fitness):
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

        # tournament parent selection
        elif selection_method == "tournament":
            while len(next_population) < len(self.population):
                sample1 = random.sample(self.population,k)
                sample2 = random.sample(self.population,k)
                parent1,parent2 = max(sample1, key=self.fitness),max(sample2, key=self.fitness)

                child1, child2 = self.crossover(parent1,parent2)
                next_population.append(child1)
                if len(next_population) < len(self.population):
                    next_population.append(child2)

            self.population = next_population

        return self.population

    def run(self, max_generations: int,time_limit: int = None,selection_method = "tournament",sample_size = 3,print_details = False):
        generation = 1
        start_time = time.perf_counter()
        time_limit = float('inf') if time_limit is None else time_limit
        while generation <= max_generations and (time.perf_counter() - start_time) <= time_limit:
            if print_details:
                print("generation #",generation," best solution fitness value: ", max([self.fitness(p) for p in self.population]), "\n")
            self.selection(selection_method= selection_method,k = sample_size)
            generation += 1
        return max(self.population, key=self.fitness)