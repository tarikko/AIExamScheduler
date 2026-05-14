# Exam Benchmark CSV Package — Folder-Based Schema

This package replaces the old flat `csv/` files with one folder per benchmark. Each benchmark folder contains exactly these four CSV files:

- `rooms.csv` with columns: `room name`, `capacity`
- `timeslots.csv` with column: `timeslot`
- `exams.csv` with columns: `exam code`, `exam name`, `duration in minutes`
- `enrollements.csv` with columns: `student code`, `exam code`

## Important notes

- Students are **not assigned to rooms** in the enrolment file. `enrollements.csv` only maps students to exams.
- Room and timeslot assignments from the previous per-row format were separated into independent resource lists.
- The original source files did not provide exam durations, so every exam is assigned a default duration of `120` minutes. Change the `duration in minutes` column later if your project needs dataset-specific durations.
- The file name `enrollements.csv` follows the spelling requested in the task.

## Package contents

- Benchmark folders: 35
- Total enrolment rows across all benchmark folders: 944,659
- `manifest.csv`: row counts and sanity-check summary for each benchmark.
