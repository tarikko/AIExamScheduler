export function renderDataOverview(data) {
	const container = document.getElementById("data-overview");
	container.innerHTML = "";

	const enrolmentRows =
		data.metadata.enrolment_rows ||
		data.students.reduce((sum, student) => sum + student.courses.length, 0);
	const totalSeats = data.rooms.reduce((sum, room) => sum + room.capacity, 0);
	const examCount = data.courses.length || data.metadata.exam_count || 0;
	const studentCount = data.students.length || data.metadata.student_count || 0;
	const roomCount = data.rooms.length || data.metadata.room_count || 0;
	const timeslotCount = data.timeSlots.length || data.metadata.timeslot_count || 0;
	const originalRoomCount = data.metadata.original_room_count || roomCount;
	const roomDetail = data.metadata.room_grouping === "virtual-room-groups"
		? `${originalRoomCount} physical rooms grouped into ${roomCount} schedulable room blocks.`
		: data.rooms.length ? `${totalSeats} total available seats.` : "Manifest room count.";

	const cards = [
		{ title: "Exams", value: examCount, detail: "Exam catalog from exams.csv." },
		{ title: "Students", value: studentCount, detail: "Unique students from enrollements.csv." },
		{ title: "Enrolments", value: enrolmentRows, detail: "Student-exam rows used for conflicts." },
		{ title: "Rooms", value: roomCount, detail: roomDetail },
		{ title: "Timeslots", value: timeslotCount, detail: "Available schedule positions." },
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
	const metrics = meta.metrics || {};

	const rows = [
		["Algorithm", meta.label, `${metrics.assigned_count ?? assignments.length} assigned / ${metrics.unassigned_count ?? 0} unassigned`],
		["Runtime", `${((metrics.elapsed_seconds || 0) * 1000).toFixed(1)} ms`, `Fitness ${metrics.fitness ?? 0}`],
		["Hard Violations", metrics.hard_violations ?? 0, `Capacity, room-timeslot, student overlap, and unassigned exams`],
		["Student Conflicts", metrics.student_conflict_count ?? 0, "Same-timeslot overlaps"],
		["Room Conflicts", metrics.room_conflict_count ?? 0, "Duplicate room-timeslot assignments"],
		["Room Capacity Exceeded", metrics.capacity_violations ?? 0, "Exams where the number of students exceeded the room capacity"],
		["Stress Load", metrics.consecutive_exam_stress ?? 0, "Consecutive same-day exams for students"],
		["Room Day Load", metrics.max_room_daily_exams ?? 0, "Max exams in one room on a single day"],
		["Penalty", metrics.penalty ?? 0, "Combined display penalty"],
	];

	rows.forEach(([label, value, detail]) => {
		const row = document.createElement("div");
		row.className = "grid-row";
		row.innerHTML = `<div class="grid-cell slot-label">${label}</div><div class="grid-cell">${value}</div><div class="grid-cell">${detail}</div>`;
		results.appendChild(row);
	});

	if ((metrics.unassigned_courses || []).length) {
		const row = document.createElement("div");
		row.className = "grid-row";
		row.innerHTML = `<div class="grid-cell slot-label">Unassigned</div><div class="grid-cell">${metrics.unassigned_courses.length}</div><div class="grid-cell">${metrics.unassigned_courses.slice(0, 8).join(", ")}</div>`;
		results.appendChild(row);
	}
}

export function buildMasterGrid(assignments, rooms, timeSlots) {
	const table = document.getElementById("master-grid");
	table.innerHTML = "";

	if (!rooms.length || !timeSlots.length) {
		table.innerHTML = "<tbody><tr><td>No dataset loaded.</td></tr></tbody>";
		return;
	}

	const thead = table.createTHead();
	const headRow = thead.insertRow();
	const anchor = document.createElement("th");
	anchor.textContent = "Time Slot / Room";
	headRow.appendChild(anchor);
	rooms.forEach((room) => {
		const th = document.createElement("th");
		th.textContent = `${room.name} (${room.capacity})`;
		headRow.appendChild(th);
	});

	const byCell = new Map();
	assignments.forEach((assignment) => {
		byCell.set(`${assignment.slot.id}|${assignment.room.name}`, assignment);
	});

	const tbody = table.createTBody();
	timeSlots.forEach((slot) => {
		const row = tbody.insertRow();
		const slotCell = row.insertCell();
		slotCell.innerHTML = `<div>${slot.label}</div><small>${slot.durationMins}m slot</small>`;
		slotCell.className = "slot-label";

		rooms.forEach((room) => {
			const cell = row.insertCell();
			const match = byCell.get(`${slot.id}|${room.name}`);
			if (!match) {
				cell.textContent = "-";
				return;
			}
			cell.innerHTML = `<strong>${match.course.name}</strong><br><small>${match.course.enrollment} students | ${match.course.durationMins}m</small>`;
			if (match.course.enrollment > room.capacity) {
				cell.style.border = "2px solid var(--danger)";
				cell.title = "Room capacity violation";
			}
		});
	});
}

export function buildHeatmap(assignments, students, roomDailyLoad) {
	const container = document.getElementById("heatmap");
	container.innerHTML = "";

	const studentDayStress = {};
	students.forEach((student) => {
		const slots = assignments
			.filter((assignment) => student.courses.includes(assignment.course.code))
			.map((assignment) => assignment.slot)
			.sort((a, b) => a.index - b.index);

		for (let i = 0; i < slots.length - 1; i++) {
			if (slots[i].day === slots[i + 1].day && slots[i + 1].index === slots[i].index + 1) {
				studentDayStress[slots[i].day] = (studentDayStress[slots[i].day] || 0) + 1;
			}
		}
	});

	const roomDayStress = {};
	(roomDailyLoad || []).forEach((row) => {
		const key = `${row.day} | ${row.room}`;
		roomDayStress[key] = row.exam_count;
	});

	const maxStudentStress = Math.max(1, ...Object.values(studentDayStress));
	const maxRoomLoad = Math.max(1, ...Object.values(roomDayStress));

	const renderCell = (label, value, kind, maxValue) => {
		const cell = document.createElement("div");
		const opacity = Math.min(0.9, 0.18 + value / 20);
		const intensity = Math.min(1, maxValue ? value / maxValue : 0);
		const hue = 220 - intensity * 160;
		const saturation = 78;
		const lightness = 34 + (1 - intensity) * 18;
		cell.className = "heat-cell";
		cell.style.background = `hsla(${hue}, ${saturation}%, ${lightness}%, ${opacity})`;
		cell.innerHTML = `<strong>${label}</strong><div class="heat-bar" style="opacity:${opacity}"></div><small>${value} ${kind === "room" ? "room exams" : "student chains"}</small>`;
		container.appendChild(cell);
	};

	Object.entries(studentDayStress).forEach(([day, count]) => renderCell(day, count, "student", maxStudentStress));
	Object.entries(roomDayStress)
		.filter(([, count]) => count > 0)
		.slice(0, 24)
		.forEach(([label, count]) => renderCell(label, count, "room", maxRoomLoad));

	if (!container.children.length) {
		container.innerHTML = "<p>No schedule heatmap data yet.</p>";
	}
}

function resolveHeatmapTarget(target) {
	if (!target) return document.getElementById("heatmap");
	if (typeof target === "string") return document.querySelector(target);
	return target;
}

function renderHeatCell(container, day, value, label, maxValue) {
	const cell = document.createElement("div");
	const opacity = Math.min(0.9, 0.18 + value / 20);
	const intensity = Math.min(1, maxValue ? value / maxValue : 0);
	const hue = 220 - intensity * 160;
	const saturation = 78;
	const lightness = 34 + (1 - intensity) * 18;
	cell.className = "heat-cell";
	cell.style.background = `hsla(${hue}, ${saturation}%, ${lightness}%, ${opacity})`;
	cell.innerHTML = `<strong>${day}</strong><div class="heat-bar" style="opacity:${opacity}"></div><small>${value} ${label}</small>`;
	container.appendChild(cell);
}

export function buildHeatmapByStudentsStress(assignments, students, days, target) {
	const container = resolveHeatmapTarget(target);
	if (!container) return;
	container.innerHTML = "";

	const orderedDays = Array.from(new Set(days || []));
	if (!orderedDays.length) {
		container.innerHTML = "<p>No schedule heatmap data yet.</p>";
		return;
	}

	const dayStress = new Map(orderedDays.map((day) => [day, 0]));

	for (const student of students || []) {
		const slots = (assignments || [])
			.filter((assignment) => (student.courses || []).includes(assignment.course.code))
			.map((assignment) => assignment.slot)
			.sort((left, right) => left.index - right.index);

		for (let index = 0; index < slots.length - 1; index++) {
			const current = slots[index];
			const next = slots[index + 1];
			if (current.day === next.day && next.index === current.index + 1) {
				dayStress.set(current.day, (dayStress.get(current.day) || 0) + 1);
			}
		}
	}

	const maxStress = Math.max(1, ...orderedDays.map((day) => dayStress.get(day) || 0));

	for (const day of orderedDays) {
		renderHeatCell(container, day, dayStress.get(day) || 0, "student stress events", maxStress);
	}
}

export function buildHeatmapByNumberOfExamsPerDay(assignments, days, target) {
	const container = resolveHeatmapTarget(target);
	if (!container) return;
	container.innerHTML = "";

	const orderedDays = Array.from(new Set(days || []));
	if (!orderedDays.length) {
		container.innerHTML = "<p>No schedule heatmap data yet.</p>";
		return;
	}

	const examCountPerDay = new Map(orderedDays.map((day) => [day, 0]));
	for (const assignment of assignments || []) {
		const day = assignment?.slot?.day;
		if (!examCountPerDay.has(day)) {
			examCountPerDay.set(day, 0);
		}
		examCountPerDay.set(day, (examCountPerDay.get(day) || 0) + 1);
	}

	const maxExamsPerDay = Math.max(1, ...orderedDays.map((day) => examCountPerDay.get(day) || 0));

	for (const day of orderedDays) {
		renderHeatCell(container, day, examCountPerDay.get(day) || 0, "exams", maxExamsPerDay);
	}
}

export function buildHeatmapByRoomLoad(roomDailyLoad, target) {
	const container = resolveHeatmapTarget(target);
	if (!container) return;
	container.innerHTML = "";

	if (!roomDailyLoad || !roomDailyLoad.length) {
		container.innerHTML = "<p>No room load data available.</p>";
		return;
	}

	const roomTotals = new Map();
	for (const row of roomDailyLoad) {
		const roomName = row.room || "Unknown Room";
		const current = roomTotals.get(roomName) || 0;
		roomTotals.set(roomName, current + (row.exam_count || 0));
	}

	const maxLoad = Math.max(1, ...roomTotals.values());
	const orderedRooms = Array.from(roomTotals.keys()).sort((left, right) =>
		left.localeCompare(right)
	);

	for (const roomName of orderedRooms) {
		renderHeatCell(container, roomName, roomTotals.get(roomName) || 0, "exams", maxLoad);
	}
}