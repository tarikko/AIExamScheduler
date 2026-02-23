export function renderDataOverview(data) {
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

export function renderSchedule(assignments, meta) {
	const results = document.getElementById("schedule-results");
	results.innerHTML = "";

	// Header
	const header = document.createElement("div");
	header.className = "grid-row";
	header.innerHTML = `<div class="grid-cell slot-label">${meta.label}</div>`;
	header.innerHTML += `<div class="grid-cell">Duration: ${meta.time.toFixed(1)}ms</div>`;
	header.innerHTML += `<div class="grid-cell">Total Penalties: ${meta.penalty}</div>`;
	results.appendChild(header);

	// Analyze Room Conflicts
	const roomSlotMap = new Map();
	const roomViolations = [];
	assignments.forEach((a) => {
		const key = `${a.slot.id}|${a.room.name}`;
		if (!roomSlotMap.has(key)) roomSlotMap.set(key, []);
		roomSlotMap.get(key).push(a.course.code);
	});
	roomSlotMap.forEach((courses, key) => {
		if (courses.length > 1) {
			const [slotId, roomName] = key.split("|");
			roomViolations.push(`${roomName} @ ${slotId}: ${courses.join(", ")}`);
		}
	});

	// Analyze Student Overlaps
	const studentSlotMap = new Map(); // student -> slot -> [courseCodes]
	const studentOverlaps = [];
	if (meta.students) {
		meta.students.forEach((student) => {
			const myAssignments = assignments.filter((a) =>
				student.courses.includes(a.course.code)
			);
			const slots = new Map();
			myAssignments.forEach((a) => {
				if (!slots.has(a.slot.id)) slots.set(a.slot.id, []);
				slots.get(a.slot.id).push(a.course.code);
			});
			slots.forEach((courses, slotId) => {
				if (courses.length > 1) {
					studentOverlaps.push(`Student ${student.id} @ ${slotId}: ${courses.join(" & ")}`);
				}
			});
		});
	}

	// 1. Room Conflict Rows
	if (roomViolations.length > 0) {
		const row = document.createElement("div");
		row.className = "grid-row";
		row.innerHTML = `<div class="grid-cell slot-label">ROOM CONFLICTS</div>`;
		row.innerHTML += `<div class="grid-cell">${roomViolations.length} double-bookings</div>`;
		row.innerHTML += `<div class="grid-cell">${roomViolations.slice(0, 3).join("; ")}${roomViolations.length > 3 ? "..." : ""}</div>`;
		results.appendChild(row);
	}

	// 2. Student Conflict Rows
	if (studentOverlaps.length > 0) {
		const row = document.createElement("div");
		row.className = "grid-row";
		row.innerHTML = `<div class="grid-cell slot-label">STUDENT CONFLICTS</div>`;
		row.innerHTML += `<div class="grid-cell">${studentOverlaps.length} overlaps</div>`;
		row.innerHTML += `<div class="grid-cell">${studentOverlaps.slice(0, 2).join("; ")}${studentOverlaps.length > 2 ? "..." : ""}</div>`;
		results.appendChild(row);
	}

	// 3. Stress Load Row
	if (meta.softViolations > 0) {
		const row = document.createElement("div");
		row.className = "grid-row";
		row.innerHTML = `<div class="grid-cell slot-label">STRESS LOAD</div>`;
		row.innerHTML += `<div class="grid-cell">${meta.softViolations} consecutive</div>`;
		row.innerHTML += `<div class="grid-cell">Students with back-to-back exams on same day</div>`;
		results.appendChild(row);
	}

	// 4. Success Row
	if (roomViolations.length === 0 && studentOverlaps.length === 0) {
		const row = document.createElement("div");
		row.className = "grid-row";
		row.innerHTML = `<div class="grid-cell slot-label">STATUS</div>`;
		row.innerHTML += `<div class="grid-cell">FEASIBLE</div>`;
		row.innerHTML += `<div class="grid-cell">No hard violations detected in the current schedule.</div>`;
		results.appendChild(row);
	}

	document.getElementById("score-note").textContent =
		"Calculated report based on " + assignments.length + " assignments.";
}

export function buildMasterGrid(assignments, rooms, timeSlots) {
	const table = document.getElementById("master-grid");
	table.innerHTML = "";

	const thead = table.createTHead();
	const headRow = thead.insertRow();
	const anchor = document.createElement("th");
	anchor.textContent = "Time Slot ↓ / Room →";
	headRow.appendChild(anchor);
	rooms.forEach((room) => {
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

		rooms.forEach((room) => {
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

export function buildHeatmap(assignments, students) {
	const container = document.getElementById("heatmap");
	container.innerHTML = "";
	const dayStress = {};

	students.forEach((student) => {
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
		container.innerHTML = "<p>No consecutive exam conflicts detected.</p>";
	}
}
