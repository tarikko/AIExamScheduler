import { timeSlots } from '../time-slots.js';
import { buildConflicts } from '../utils.js';

export function cspSchedule(data) {
  const conflicts = buildConflicts(data);
  const domains = {};
  data.courses.forEach(course => {
    domains[course.code] = timeSlots.flatMap(slot =>
      data.rooms.filter(room => room.capacity >= course.enrollment).map(room => ({ slot, room }))
    );
  });

  function validAssignment(course, slot, room, partial) {
    return partial.every(assigned => {
      if (assigned.slot.id === slot.id && assigned.room.name === room.name) {
        return false;
      }
      if (assigned.slot.id === slot.id) {
        const conflictsWith = conflicts[course.code].has(assigned.course.code);
        if (conflictsWith) return false;
      }
      return true;
    });
  }

  function selectCourse(partial) {
    const assigned = new Set(partial.map(entry => entry.course.code));
    let candidate = null;
    data.courses.forEach(course => {
      if (assigned.has(course.code)) return;
      const choices = domains[course.code].filter(choice =>
        validAssignment(course, choice.slot, choice.room, partial)
      );
      if (!candidate || choices.length < candidate.choices.length) {
        candidate = { course, choices };
      }
    });
    return candidate;
  }

  function backtrack(partial) {
    if (partial.length === data.courses.length) return partial;
    const node = selectCourse(partial);
    if (!node || !node.choices.length) return null;
    for (const choice of node.choices) {
      const next = backtrack([...partial, { course: node.course, slot: choice.slot, room: choice.room }]);
      if (next) return next;
    }
    return null;
  }

  return backtrack([]) || [];
}
