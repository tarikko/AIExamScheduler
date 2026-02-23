(() => {
	"use strict";

	const timeSlots = [
		{
			id: "Mon-09-11",
			day: "Monday",
			label: "Mon • 09:00 - 11:00",
			index: 0,
		},
		{
			id: "Mon-11-13",
			day: "Monday",
			label: "Mon • 11:00 - 13:00",
			index: 1,
		},
		{
			id: "Mon-13-15",
			day: "Monday",
			label: "Mon • 13:00 - 15:00",
			index: 2,
		},
		{
			id: "Tue-09-11",
			day: "Tuesday",
			label: "Tue • 09:00 - 11:00",
			index: 3,
		},
		{
			id: "Tue-11-13",
			day: "Tuesday",
			label: "Tue • 11:00 - 13:00",
			index: 4,
		},
		{
			id: "Tue-13-15",
			day: "Tuesday",
			label: "Tue • 13:00 - 15:00",
			index: 5,
		},
		{
			id: "Wed-09-11",
			day: "Wednesday",
			label: "Wed • 09:00 - 11:00",
			index: 6,
		},
		{
			id: "Wed-11-13",
			day: "Wednesday",
			label: "Wed • 11:00 - 13:00",
			index: 7,
		},
	];

	const algorithms = {
		greedy: {
			label: "Greedy Search (Largest Enrollment + Degree)",
			fn: greedySchedule,
			note: "Assigns the busiest exam to the first available non-conflicting slot. Penalties reward compact days.",
		},
		csp: {
			label: "CSP (MRV + Forward Checking)",
			fn: cspSchedule,
			note: "Backtracking with Minimum Remaining Values and forward checking to prune conflicts early.",
		},
		ga: {
			label: "Genetic Algorithm (Week Swap Crossover)",
			fn: gaSchedule,
			note: "Evolves schedule strings with heavy fitness penalty for hard violations, light for soft.",
		},
		a_star: {
			label: "A* Search (Conflict Density Heuristic)",
			fn: aStarSchedule,
			note: "Explores partial states, prioritizing boards that leave fewer high-conflict exams unscheduled.",
		},
	};

	let dataset;
	let bestCompare = {};

	function renderDataOverview(data) {
		const container = document.getElementById("data-overview");
		container.innerHTML = "";

		const enrollTotal = data.courses.reduce(
			(sum, course) => sum + course.enrollment,
			0
		);
		const roomTotal = data.rooms.length;

		const cards = [
			{
				title: "Courses",
				value: data.courses.length,
				detail: "Course catalog + enrollments (Carter 1996 formatting).",
			},
			{
				title: "Students",
				value: data.students.length,
				detail: "Enrollment log to compute conflicts.",
			},
			{
				title: "Total Seats",
				value: enrollTotal,
				detail: `Room inventory × capacities (${roomTotal} rooms).`,
			},
		];

		cards.forEach((card) => {
			const el = document.createElement("div");
			el.className = "data-card";
			el.innerHTML = `<strong>${card.title}</strong><span>${card.value}</span><p>${card.detail}</p>`;
			container.appendChild(el);
		});
	}

	function buildConflicts(data) {
		const map = {};
		data.courses.forEach((course) => {
			map[course.code] = new Set();
		});

		data.students.forEach((student) => {
			student.courses.forEach((courseA) => {
				student.courses.forEach((courseB) => {
					if (courseA !== courseB) {
						map[courseA].add(courseB);
					}
				});
			});
		});

		return map;
	}

	function isSlotAvailable(courseCode, slot, room, assignments, data) {
		for (const assigned of assignments) {
			if (
				assigned.slot.id === slot.id &&
				assigned.room.name === room.name
			) {
				return false; // Room busy
			}
			if (assigned.slot.id === slot.id) {
				const conflict = data.students.some(
					(student) =>
						student.courses.includes(courseCode) &&
						student.courses.includes(assigned.course.code)
				);
				if (conflict) {
					return false;
				}
			}
		}
		return true;
	}

	function greedySchedule(data) {
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
					if (
						isSlotAvailable(course.code, slot, room, assigned, data)
					) {
						assigned.push({ course, slot, room });
						return;
					}
				}
			}
		});
		return assigned;
	}

	function cspSchedule(data) {
		const conflicts = buildConflicts(data);
		const domains = {};
		data.courses.forEach((course) => {
			domains[course.code] = timeSlots.flatMap((slot) =>
				data.rooms
					.filter((room) => room.capacity >= course.enrollment)
					.map((room) => ({ slot, room }))
			);
		});

		function validAssignment(course, slot, room, partial) {
			return partial.every((assigned) => {
				if (
					assigned.slot.id === slot.id &&
					assigned.room.name === room.name
				) {
					return false;
				}
				if (assigned.slot.id === slot.id) {
					const conflictsWith = conflicts[course.code].has(
						assigned.course.code
					);
					if (conflictsWith) return false;
				}
				return true;
			});
		}

		function selectCourse(partial) {
			const assigned = new Set(partial.map((entry) => entry.course.code));
			let candidate = null;
			data.courses.forEach((course) => {
				if (assigned.has(course.code)) return;
				const choices = domains[course.code].filter((choice) =>
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
				const next = backtrack([
					...partial,
					{
						course: node.course,
						slot: choice.slot,
						room: choice.room,
					},
				]);
				if (next) return next;
			}
			return null;
		}

		return backtrack([]) || [];
	}

	function gaSchedule(data) {
		const populationSize = 40;
		const generations = 90;
		const rooms = data.rooms;
		const combos = timeSlots.flatMap((slot) =>
			rooms.map((room) => ({ slot, room }))
		);

		function randomIndividual() {
			return data.courses.map((course) => {
				const domain = combos.filter(
					(combo) => combo.room.capacity >= course.enrollment
				);
				return domain[Math.floor(Math.random() * domain.length)];
			});
		}

		function computeFitness(individual) {
			let hard = 0;
			let soft = 0;
			for (let i = 0; i < individual.length; i++) {
				for (let j = i + 1; j < individual.length; j++) {
					const courseA = individual[i];
					const courseB = individual[j];
					if (courseA.slot.id === courseB.slot.id) {
						if (courseA.room.name === courseB.room.name) {
							hard += 3;
						}
						const studentsConflict = data.students.some(
							(student) =>
								student.courses.includes(
									data.courses[i].code
								) &&
								student.courses.includes(data.courses[j].code)
						);
						if (studentsConflict) hard += 5;
					}
				}
			}
			const slotIndices = individual.map((assign) => assign.slot.index);
			slotIndices.forEach((slotIdx) => {
				if (slotIndices.includes(slotIdx + 1)) soft += 1;
			});
			return -(hard * 40 + soft * 2);
		}

		function crossover(parentA, parentB) {
			const pivot = Math.floor(Math.random() * parentA.length);
			return [
				[...parentA.slice(0, pivot), ...parentB.slice(pivot)],
				[...parentB.slice(0, pivot), ...parentA.slice(pivot)],
			];
		}

		let population = Array.from(
			{ length: populationSize },
			randomIndividual
		);
		for (let generation = 0; generation < generations; generation++) {
			population.sort((a, b) => computeFitness(b) - computeFitness(a));
			if (Math.random() < 0.4) {
				const [childA, childB] = crossover(
					population[0],
					population[1]
				);
				population.splice(-2, 2, childA, childB);
			}
			if (Math.random() < 0.3) {
				const idx = Math.floor(Math.random() * population.length);
				population[idx] = randomIndividual();
			}
		}

		const best = population.sort(
			(a, b) => computeFitness(b) - computeFitness(a)
		)[0];
		return best.map((assignment, index) => ({
			course: data.courses[index],
			slot: assignment.slot,
			room: assignment.room,
		}));
	}

	function aStarSchedule(data) {
		const conflicts = buildConflicts(data);
		const rooms = data.rooms;
		const domain = timeSlots.flatMap((slot) =>
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
			frontier.sort((a, b) => a.f - b.f);
			const node = frontier.shift();
			steps++;
			if (node.assignments.length === data.courses.length) {
				return node.assignments;
			}

			const nextCourse = data.courses[node.assignments.length];
			const filtered = domain.filter(
				({ slot, room }) => room.capacity >= nextCourse.enrollment
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
					child.assignments.length +
					heuristic(child.assignments.length);
				frontier.push(child);
			});
		}

		return frontier[0]?.assignments || [];
	}

	function renderSchedule(assignments, meta) {
		const results = document.getElementById("schedule-results");
		results.innerHTML = "";

		const header = document.createElement("div");
		header.className = "grid-row";
		header.innerHTML = `<div class="grid-cell slot-label">${meta.label}</div>`;
		header.innerHTML += `<div class="grid-cell">${meta.time.toFixed(
			1
		)}ms</div>`;
		header.innerHTML += `<div class="grid-cell">Penalties ${meta.penalty}</div>`;
		results.appendChild(header);

		assignments.forEach((slot) => {
			const row = document.createElement("div");
			row.className = "grid-row";
			row.innerHTML = `
        <div class="grid-cell slot-label">${slot.slot.label}</div>
        <div class="grid-cell">${slot.course.code}</div>
        <div class="grid-cell">${slot.course.name}</div>
        <div class="grid-cell">${slot.room.name} (${slot.room.capacity} seats)</div>
      `;
			results.appendChild(row);
		});

		document.getElementById("score-note").textContent =
			"Soft constrained students-in-a-row: " + meta.softViolations;
	}

	function buildMasterGrid(assignments) {
		const table = document.getElementById("master-grid");
		table.innerHTML = "";

		const thead = table.createTHead();
		const headRow = thead.insertRow();
		const anchor = document.createElement("th");
		anchor.textContent = "Time Slot ↓ / Room →";
		headRow.appendChild(anchor);
		dataset.rooms.forEach((room) => {
			const th = document.createElement("th");
			th.textContent = room.name;
			headRow.appendChild(th);
		});

		const tbody = table.createTBody();
		timeSlots.forEach((slot) => {
			const row = tbody.insertRow();
			const slotCell = row.insertCell();
			slotCell.textContent = slot.label;
			slotCell.className = "slot-label";

			dataset.rooms.forEach((room) => {
				const cell = row.insertCell();
				const match = assignments.find(
					(assignment) =>
						assignment.slot.id === slot.id &&
						assignment.room.name === room.name
				);
				cell.textContent = match
					? `${match.course.code} (${match.course.enrollment})`
					: "—";
			});
		});
	}

	function buildHeatmap(assignments) {
		const container = document.getElementById("heatmap");
		container.innerHTML = "";
		const dayStress = {};
		dataset.students.forEach((student) => {
			const assignedSlots = assignments
				.filter((assignment) =>
					student.courses.includes(assignment.course.code)
				)
				.map((assignment) => assignment.slot)
				.sort((a, b) => a.index - b.index);
			assignedSlots.forEach((slot, index) => {
				const next = assignedSlots[index + 1];
				if (
					next &&
					next.day === slot.day &&
					next.index === slot.index + 1
				) {
					dayStress[slot.day] = (dayStress[slot.day] || 0) + 1;
				}
			});
		});

		Object.entries(dayStress).forEach(([day, count]) => {
			const cell = document.createElement("div");
			const intensity = Math.min(100, count * 12);
			cell.className = "heat-cell";
			cell.style.background = `rgba(255, 94, 91, ${Math.min(
				0.9,
				intensity / 120
			)})`;
			cell.innerHTML = `${day}<div class="heat-bar" style="opacity:${Math.min(
				1,
				intensity / 120
			)}"></div><small>${count} conflicts</small>`;
			container.appendChild(cell);
		});
		if (!Object.keys(dayStress).length) {
			container.innerHTML =
				"<p>No consecutive exam conflicts detected.</p>";
		}
	}

	function assessPenalties(assignments) {
		let hardViolations = 0;
		let softViolations = 0;
		const seen = new Set();
		assignments.forEach((assignment) => {
			const key = `${assignment.slot.id}-${assignment.room.name}`;
			if (seen.has(key)) hardViolations++;
			seen.add(key);
		});
		dataset.students.forEach((student) => {
			const slots = assignments
				.filter((assignment) =>
					student.courses.includes(assignment.course.code)
				)
				.map((assignment) => assignment.slot.index)
				.sort((a, b) => a - b);
			for (let i = 0; i < slots.length - 1; i++) {
				if (slots[i + 1] - slots[i] === 1) softViolations++;
			}
		});
		return hardViolations * 50 + softViolations * 3;
	}

	function updateComparison(key, meta) {
		if (!bestCompare[key] || bestCompare[key].penalty > meta.penalty) {
			bestCompare[key] = meta;
		}
	}

	async function init() {
		dataset = await fetch("data/fake-data.json").then((res) => res.json());
		renderDataOverview(dataset);

		const controlBar = document.getElementById("strategy-controls");
		Object.entries(algorithms).forEach(([key, config], index) => {
			const button = document.createElement("button");
			button.className = "algo-btn";
			button.textContent = config.label;
			button.addEventListener("click", () => runStrategy(key));
			if (index === 0) button.classList.add("active");
			controlBar.appendChild(button);
		});

		runStrategy("greedy");
	}

	function runStrategy(key) {
		if (!dataset) return;
		Array.from(document.querySelectorAll(".algo-btn")).forEach((btn) =>
			btn.classList.remove("active")
		);
		const button = Array.from(document.querySelectorAll(".algo-btn")).find(
			(btn) => btn.textContent === algorithms[key].label
		);
		button?.classList.add("active");

		const start = performance.now();
		const result = algorithms[key].fn(dataset);
		const end = performance.now();
		const penalty = assessPenalties(result);
		const softViolations = penalty / 3;

		document.getElementById("algo-note").textContent = algorithms[key].note;

		renderSchedule(result, {
			label: algorithms[key].label,
			time: end - start,
			penalty,
			softViolations,
		});

		buildMasterGrid(result);
		buildHeatmap(result);
		updateComparison(key, {
			label: algorithms[key].label,
			penalty,
			time: end - start,
		});
	}

	init();
})();
