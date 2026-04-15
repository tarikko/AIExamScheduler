import json
import os

nb_path = 'notebook/algorithms.ipynb'
with open(nb_path, 'r', encoding='utf-8') as f:
    nb = json.load(f)

md_cell = {
   'cell_type': 'markdown',
   'metadata': {},
   'source': ['## Benchmark Run\n', 'Importing the benchmark and running the GA']
}

code_cell_1 = {
   'cell_type': 'code',
   'execution_count': None,
   'metadata': {},
   'outputs': [],
   'source': [
       'import os\n',
       '\n',
       'benchmark_dir = "../benchmark/1"\n',
       '\n',
       'def load_benchmark():\n',
       '    # 1. Read rooms\n',
       '    rooms = []\n',
       '    with open(os.path.join(benchmark_dir, "data"), "r") as f:\n',
       '        lines = f.readlines()\n',
       '        \n',
       '    parsing_rooms = False\n',
       '    for line in lines:\n',
       '        line = line.strip()\n',
       '        if not line: continue\n',
       '        if line.startswith("ROOMS"):\n',
       '            parsing_rooms = True\n',
       '            continue\n',
       '        if parsing_rooms and line.startswith("-----"):\n',
       '            continue\n',
       '        if parsing_rooms and line.startswith("ROOM ASSIGNMENTS"):\n',
       '            break\n',
       '        if parsing_rooms:\n',
       '            parts = line.split()\n',
       '            if len(parts) >= 2:\n',
       '                name = parts[0]\n',
       '                try:\n',
       '                    cap = int(parts[1])\n',
       '                    # Use the Room class from the notebook\n',
       '                    rooms.append(Room(name, cap))\n',
       '                except ValueError:\n',
       '                    pass\n',
       '\n',
       '    # 2. Create timeslots based on benchmark specs\n',
       '    # Mon 23rd Jan - Sat 4th Feb 1995\n',
       '    times = ["09:00", "13:30", "16:30"]\n',
       '    dates = [\n',
       '        "1995-01-23", "1995-01-24", "1995-01-25", "1995-01-26", "1995-01-27", "1995-01-28",\n',
       '        "1995-01-30", "1995-01-31", "1995-02-01", "1995-02-02", "1995-02-03", "1995-02-04"\n',
       '    ]\n',
       '    \n',
       '    timeslots = []\n',
       '    for date in dates:\n',
       '        for t in times:\n',
       '            # Saturdays only have morning exams\n',
       '            if (date == "1995-01-28" or date == "1995-02-04") and t != "09:00":\n',
       '                continue\n',
       '            # Use the Timeslot class from the notebook\n',
       '            timeslots.append(Timeslot(f"{date} {t}"))\n',
       '            \n',
       '    # 3. Read exams\n',
       '    exam_to_idx = {}\n',
       '    with open(os.path.join(benchmark_dir, "exams"), "r") as f:\n',
       '        for idx, line in enumerate(f):\n',
       '            exam_code = line[:8].strip()\n',
       '            if exam_code:\n',
       '                exam_to_idx[exam_code] = len(exam_to_idx)\n',
       '            \n',
       '    exam_students = [set() for _ in range(len(exam_to_idx))]\n',
       '    \n',
       '    # 4. Read enrolments\n',
       '    with open(os.path.join(benchmark_dir, "enrolements"), "r") as f:\n',
       '        for line in f:\n',
       '            parts = line.split()\n',
       '            if len(parts) >= 2:\n',
       '                student, exam = parts[0], parts[1]\n',
       '                if exam in exam_to_idx:\n',
       '                    exam_students[exam_to_idx[exam]].add(student)\n',
       '                    \n',
       '    return rooms, timeslots, exam_students\n',
       '\n',
       '# Load data\n',
       'bm_rooms, bm_timeslots, bm_exam_students = load_benchmark()\n',
       'bm_room_timeslot = [(room, slot) for room in bm_rooms for slot in bm_timeslots]\n',
       '\n',
       'print(f"Loaded Benchmark: {len(bm_rooms)} rooms, {len(bm_timeslots)} timeslots, {len(bm_room_timeslot)} room-timeslots options, and {len(bm_exam_students)} exams.")\n'
   ]
}

code_cell_2 = {
   'cell_type': 'code',
   'execution_count': None,
   'metadata': {},
   'outputs': [],
   'source': [
       '# Setup GA for Benchmark\n',
       'num_exams_bm = len(bm_exam_students)\n',
       'domain_bm = list(range(len(bm_room_timeslot)))\n',
       '\n',
       '# Using a smaller population and generations for the benchmark to run in a reasonable time\n',
       'population_size_bm = 50\n',
       'mutation_probability_bm = 0.05\n',
       '\n',
       'population_bm = [\n',
       '    Chromosome(\n',
       '        size=num_exams_bm,\n',
       '        domain=domain_bm,\n',
       '        mutation_probability=mutation_probability_bm,\n',
       '    )\n',
       '    for _ in range(population_size_bm)\n',
       ']\n',
       '\n',
       'ga_bm = GeneticAlgorithm(population_bm, bm_room_timeslot, bm_exam_students)\n',
       '\n',
       'print("Running GA on benchmark data...")\n',
       'best_ga_bm = ga_bm.run(generations=10, printer=True)\n',
       '\n',
       'print("\\nGenerating report for Benchmark GA solution:")\n',
       'generate_quality_report(best_ga_bm.dna, \\'Benchmark Genetic Algorithm\\', fitness_value=ga_bm.fitness(best_ga_bm))\n'
   ]
}

nb['cells'].extend([md_cell, code_cell_1, code_cell_2])

with open(nb_path, 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=1)
print('Successfully appended benchmark cells to algorithms.ipynb.')
