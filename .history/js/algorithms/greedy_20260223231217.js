import { timeSlots } from "../time-slots.js";
import { buildConflicts, isSlotAvailable } from "../utils.js";

export function greedySchedule(data, onProgress) {
	const conflicts = buildConflicts(data);
	const slots = data.timeSlots || timeSlots;
	const sortedCourses = [...data.courses].sort((a, b) => {
		const delta = conflicts[b.code].size - conflicts[a.code].size;
		return delta !== 0 ? delta : b.enrollment - a.enrollment;
	});

	const assigned = [];
	const total = sortedCourses.length;

	for (let i = 0; i < total; i++) {
		const course = sortedCourses[i];
		if (onProgress && i % 20 === 0) onProgress((i / total) * 100);

		let placed = false;
		for (const slot of slots) {
			for (const room of data.rooms) {
				if (room.capacity < course.enrollment) continue;
				if (isSlotAvailable(course.code, slot, room, assigned, data)) {
					assigned.push({ course, slot, room });
					placed = true;
					break;
				}
			}
			if (placed) break;
		}
	}
	if (onProgress) onProgress(100);
	return assigned;
}
