export function buildConflicts(data) {
  const map = {};
  data.courses.forEach(course => {
    map[course.code] = new Set();
  });

  data.students.forEach(student => {
    student.courses.forEach(courseA => {
      student.courses.forEach(courseB => {
        if (courseA !== courseB) {
          map[courseA].add(courseB);
        }
      });
    });
  });

  return map;
}

export function isSlotAvailable(courseCode, slot, room, assignments, data) {
  for (const assigned of assignments) {
    if (assigned.slot.id === slot.id && assigned.room.name === room.name) {
      return false; // Room busy
    }
    if (assigned.slot.id === slot.id) {
      const conflict = data.students.some(student =>
        student.courses.includes(courseCode) && student.courses.includes(assigned.course.code)
      );
      if (conflict) {
        return false;
      }
    }
  }
  return true;
}

export function assessPenalties(assignments, students) {
  let hardViolations = 0;
  let softViolations = 0;
  const seen = new Set();

  assignments.forEach(assignment => {
    const key = `${assignment.slot.id}-${assignment.room.name}`;
    if (seen.has(key)) hardViolations++;
    seen.add(key);
  });

  students.forEach(student => {
    const slots = assignments
      .filter(assignment => student.courses.includes(assignment.course.code))
      .map(assignment => assignment.slot.index)
      .sort((a, b) => a - b);
    for (let i = 0; i < slots.length - 1; i++) {
      if (slots[i + 1] - slots[i] === 1) softViolations++;
    }
  });

  return {
    penalty: hardViolations * 50 + softViolations * 3,
    hardViolations,
    softViolations
  };
}
