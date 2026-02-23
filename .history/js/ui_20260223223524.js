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

	// Header with algorithm, time, and penalty
	const header = document.createElement("div");
	header.style.cssText = "padding: 12px; margin-bottom: 12px; background: #f0f0f0; border-radius: 8px; border-left: 4px solid var(--accent);";
	header.innerHTML = `
		<strong>${meta.label}</strong> | 
		<span style="color: #666;">${meta.time.toFixed(1)}ms</span> | 
		<span style="font-size: 1.1rem; ${meta.penalty > 0 ? 'color: var(--accent); font-weight: bold;' : 'color: green; font-weight: bold;'}">
			Penalty Score: ${meta.penalty}
		</span>
	`;
	results.appendChild(header);

	// Room conflicts
	const roomConflicts = {};
	assignments.forEach((a1) => {
		assignments.forEach((a2) => {
			if (a1 !== a2 && a1.room.name === a2.room.name && a1.slot.id === a2.slot.id) {
				const key = `${a1.slot.label} @ ${a1.room.name}`;
				if (!roomConflicts[key]) roomConflicts[key] = [];
				roomConflicts[key].push(a1.course.code);
			}
		});
	});

	if (Object.keys(roomConflicts).length > 0) {
		const conflictDiv = document.createElement("div");
		conflictDiv.style.cssText = "margin: 12px 0; padding: 10px; background: #ffe0e0; border-radius: 6px; border-left: 4px solid var(--accent);";
		conflictDiv.innerHTML = `<strong style="color: var(--accent);">🚨 Room Conflicts (Multiple courses in same room-time)</strong>`;
		Object.entries(roomConflicts).forEach(([key, codes]) => {
			const item = document.createElement("div");
			item.style.marginTop = "6px";
			item.textContent = `${key}: ${[...new Set(codes)].join(", ")}`;
			conflictDiv.appendChild(item);
		});
		results.appendChild(conflictDiv);
	}

	// Student conflicts
	const studentConflicts = {};
	assignments.forEach((a1) => {
		assignments.forEach((a2) => {
			if (a1 !== a2 && a1.slot.id === a2.slot.id) {
				// Check if any student takes both courses
				const sharedStudents = [];
				if (meta.students) {
					meta.students.forEach((s) => {
						if (s.courses.includes(a1.course.code) && s.courses.includes(a2.course.code)) {
							sharedStudents.push(s.id);
						}
					});
					if (sharedStudents.length > 0) {
						const key = `${a1.slot.label}: ${a1.course.code} vs ${a2.course.code}`;
						if (!studentConflicts[key]) studentConflicts[key] = sharedStudents.length;
					}
				}
			}
		});
	});

	if (Object.keys(studentConflicts).length > 0) {
		const conflictDiv = document.createElement("div");
		conflictDiv.style.cssText = "margin: 12px 0; padding: 10px; background: #ffe0e0; border-radius: 6px; border-left: 4px solid var(--accent);";
		conflictDiv.innerHTML = `<strong style="color: var(--accent);">👤 Student Time Conflicts (Students taking 2 exams same time)</strong>`;
		Object.entries(studentConflicts).forEach(([key, count]) => {
			const item = document.createElement("div");
			item.style.marginTop = "6px";
			item.textContent = `${key} → ${count} student(s) affected`;
			conflictDiv.appendChild(item);
		});
		results.appendChild(conflictDiv);
	}

	// Soft violations (consecutive exams)
	if (meta.softViolations && meta.softViolations > 0) {
		const softDiv = document.createElement("div");
		softDiv.style.cssText = "margin: 12px 0; padding: 10px; background: #fff4e0; border-radius: 6px; border-left: 4px solid #ffa500;";
		softDiv.innerHTML = `
			<strong style="color: #ff8c00;">⚠️ Stress Load (Back-to-back exams)</strong><br>
			<span style="font-size: 0.95rem; color: #666;">
			${meta.softViolations} student(s) have consecutive exams on the same day. While not a hard violation, this is stressful.
			</span>
		`;
		results.appendChild(softDiv);
	}

	if (Object.keys(roomConflicts).length === 0 && Object.keys(studentConflicts).length === 0 && (!meta.softViolations || meta.softViolations === 0)) {
		const goodDiv = document.createElement("div");
		goodDiv.style.cssText = "margin: 12px 0; padding: 10px; background: #e0ffe0; border-radius: 6px; border-left: 4px solid green;";
		goodDiv.innerHTML = `<strong style="color: green;">✅ Perfect! No violations detected.</strong>`;
		results.appendChild(goodDiv);
	}

	document.getElementById("score-note").textContent = `Total penalty points: ${meta.penalty}`;
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
