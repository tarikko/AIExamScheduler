import { timeSlots } from "../time-slots.js";
import { buildConflicts, isSlotAvailable } from "../utils.js";

export function greedySchedule(data) {
	const conflicts = buildConflicts(data);
	const sortedCourses = [...data.courses].sort((a, b) => {
		const delta = conflicts[b.code].size - conflicts[a.code].size;
		return delta !== 0 ? delta : b.enrollment - a.enrollment;
	});

	const assigned = [];
	sortedCourses.forEach((course) => {
		for (const slot of timeSlots) {
			for (const room of data.rooms) {
				if (room.capacity < course.enrollment) continue;
				if (isSlotAvailable(course.code, slot, room, assigned, data)) {
					assigned.push({ course, slot, room });
					return;
				}
			}
		}
	});
	return assigned;
}
