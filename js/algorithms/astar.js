import { buildConflicts } from "../utils.js";

export function aStarSchedule(data, onProgress) {
	const conflicts = buildConflicts(data);
	const rooms = data.rooms;
	const slots = data.timeSlots;

	// Sort courses most-constrained first (highest conflict degree + largest enrollment)
	const orderedCourses = [...data.courses].sort((a, b) => {
		const dConflict = conflicts[b.code].size - conflicts[a.code].size;
		return dConflict !== 0 ? dConflict : b.enrollment - a.enrollment;
	});

	// Build per-course valid combos (capacity + duration satisfied)
	const courseDomain = new Map();
	orderedCourses.forEach((course) => {
		const valid = slots.flatMap((slot) =>
			slot.durationMins >= (course.durationMins || 0)
				? rooms
						.filter((r) => r.capacity >= course.enrollment)
						.map((room) => ({ slot, room }))
				: []
		);
		// Fallback: relax duration if no valid combo exists
		const pool =
			valid.length > 0
				? valid
				: slots.flatMap((slot) =>
						rooms
							.filter((r) => r.capacity >= course.enrollment)
							.map((room) => ({ slot, room }))
				  );
		courseDomain.set(course.code, pool.length > 0 ? pool : slots.flatMap((slot) => rooms.map((room) => ({ slot, room }))));
	});

	// g(n) = hard violation cost so far; h(n) = remaining courses × avg domain size inverse
	function heuristic(depth) {
		return (orderedCourses.length - depth) * 2;
	}

	function violations(assignments, newSlot, newRoom, courseCode) {
		let cost = 0;
		for (const a of assignments) {
			if (a.slot.id === newSlot.id && a.room.name === newRoom.name) cost += 50;
			if (a.slot.id === newSlot.id && conflicts[courseCode].has(a.course.code)) cost += 50;
		}
		return cost;
	}

	// frontier: min-heap by f = g + h (lower = better)
	const frontier = [{ assignments: [], g: 0, f: heuristic(0) }];
	const maxFrontierSize = 2000;

	let best = [];
	let steps = 0;
	const maxSteps = 30000;

	while (frontier.length > 0 && steps < maxSteps) {
		steps++;
		if (onProgress && steps % 500 === 0)
			onProgress(Math.min(95, (steps / maxSteps) * 100));

		// Pop node with lowest f (simple linear scan — fast enough for bounded frontier)
		let bestIdx = 0;
		for (let i = 1; i < frontier.length; i++) {
			if (frontier[i].f < frontier[bestIdx].f) bestIdx = i;
		}
		const node = frontier.splice(bestIdx, 1)[0];

		if (node.assignments.length > best.length) best = node.assignments;

		if (node.assignments.length === orderedCourses.length) {
			if (onProgress) onProgress(100);
			return node.assignments;
		}

		const depth = node.assignments.length;
		const nextCourse = orderedCourses[depth];
		const domain = courseDomain.get(nextCourse.code);

		for (const { slot, room } of domain) {
			const v = violations(node.assignments, slot, room, nextCourse.code);
			const g = node.g + v;
			const child = {
				assignments: [
					...node.assignments,
					{ course: nextCourse, slot, room },
				],
				g,
				f: g + heuristic(depth + 1),
			};
			frontier.push(child);
		}

		// Keep frontier bounded to avoid memory blowup
		if (frontier.length > maxFrontierSize) {
			frontier.sort((a, b) => a.f - b.f);
			frontier.length = maxFrontierSize;
		}
	}

	if (onProgress) onProgress(100);
	return best;
}
