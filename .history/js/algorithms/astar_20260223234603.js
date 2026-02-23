import { buildConflicts } from "../utils.js";

export function aStarSchedule(data, onProgress) {
	const conflicts = buildConflicts(data);
	const rooms = data.rooms;
	const slots = data.timeSlots;
	const domain = slots.flatMap((slot) =>
		rooms.map((room) => ({ slot, room }))
	);

	function heuristic(assignedCount) {
		return (data.courses.length - assignedCount) * 3 + assignedCount;
	}

	const frontier = [
		{
			assignments: [],
			f: heuristic(0),
		},
	];

	const maxSteps = 500;
	let steps = 0;

	while (frontier.length && steps < maxSteps) {
		if (onProgress && steps % 20 === 0)
			onProgress((steps / maxSteps) * 100);
		frontier.sort((a, b) => a.f - b.f);
		const node = frontier.shift();
		steps++;
		if (node.assignments.length === data.courses.length) {
			if (onProgress) onProgress(100);
			return node.assignments;
		}

		const nextCourse = data.courses[node.assignments.length];
		const filtered = domain.filter(
			({ slot, room }) =>
				room.capacity >= nextCourse.enrollment &&
				slot.durationMins >= nextCourse.durationMins
		);

		filtered.forEach((choice) => {
			const valid = node.assignments.every((assigned) => {
				if (
					assigned.slot.id === choice.slot.id &&
					assigned.room.name === choice.room.name
				) {
					return false;
				}
				if (
					assigned.slot.id === choice.slot.id &&
					conflicts[nextCourse.code].has(assigned.course.code)
				) {
					return false;
				}
				return true;
			});
			if (!valid) return;
			const child = {
				assignments: [
					...node.assignments,
					{
						course: nextCourse,
						slot: choice.slot,
						room: choice.room,
					},
				],
			};
			child.f =
				child.assignments.length + heuristic(child.assignments.length);
			frontier.push(child);
		});
	}

	if (onProgress) onProgress(100);
	return frontier[0]?.assignments || [];
}
