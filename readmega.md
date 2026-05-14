# Genetic Algorithm Performance Changes

## What changed

- Replaced repeated full GA fitness recalculation with cached chromosome fitness.
- Added a precomputed conflict-pair list so the GA checks only exam pairs that actually share students.
- Builds conflict pairs through student enrolment lists instead of scanning every possible exam pair.
- Precomputed room capacity, timeslot index, timeslot day, and late-slot flags for faster scoring.
- Changed GA progress reporting to reuse the current generation's best score instead of rescanning the full population.
- Seeded the population with the greedy schedule and mutated variants, so GA starts from useful schedules instead of mostly invalid random schedules.
- Skips greedy seeding above 300 exams because the seed construction can be slower than the GA cap on large benchmarks.
- Added adaptive GA runtime caps based on dataset size.

## Adaptive GA limits

The old default was always:

```text
population_size = 350
generations = 300
```

That caused very large workloads on every dataset. The backend now caps GA work as follows:

```text
<= 100 exams:  population 80, generations 80, time limit 5s
<= 300 exams:  population 60, generations 50, time limit 8s
<= 800 exams:  population 35, generations 35, time limit 10s
> 800 exams:   population 20, generations 20, time limit 12s
```

If the request asks for smaller values, the smaller values are respected.

## Why this helps

The previous GA cost was roughly:

```text
generations * population_size * exams^2
```

With the old defaults, that meant 105,000 fitness evaluations per run. For large benchmarks, each evaluation compared hundreds of thousands or millions of exam pairs.

The new implementation cuts work by:

- avoiding duplicate fitness calls in the same generation,
- checking only conflicting exam pairs,
- starting from a feasible greedy solution,
- avoiding greedy seeding on large datasets where the seed itself is too expensive,
- stopping by dataset-aware generation/population caps and time limit.

## Expected behavior

- Small datasets should still run several GA generations and return quickly.
- Large datasets should no longer appear stuck for a long time.
- GA should be treated as an improvement pass over a greedy seed, not a from-scratch solver for huge benchmarks.
- Greedy/CSP/A* behavior is unchanged.
