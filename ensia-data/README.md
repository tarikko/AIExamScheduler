This directory contains the exam timetabling data for ENSIA, based on the 5Y Program modules.
The data includes 4 years of students and their corresponding modules.

Summary:
- Total Exams: 56 modules (1Y: 14, 2Y: 14, 3Y: 13, 4Y: 15)
- Total Students: 780 students
  - 1Y: 250 students (Bac 2025)
  - 2Y: 200 students (Bac 2024)
  - 3Y: 180 students (Bac 2023)
  - 4Y: 150 students (Bac 2022)
- Rooms: 8 AMPHI rooms (Capacity 80 each)

The data is in the following files:

students.csv:
    List of students with IDs

exams.csv:
    List of exams with the following fields:
    - code: Module code (e.g., FMAT, DSA1)
    - name: Full name of the module
    - duration: Exam duration in minutes

enrolements.csv:
    Mapping of students to the exams they are sitting.
    - student: Student ID
    - exam: Exam code

room.csv:
    List of available rooms and their capacities.
    - Room Name (e.g., AMPHI_1)
    - Capacity (e.g., 80)
