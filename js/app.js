/**
 * Main application — connects the frontend to the FastAPI backend.
 * Uses Server-Sent Events (SSE) for real-time progress during algorithm execution.
 */

import { renderDataOverview, renderSchedule, buildMasterGrid, buildHeatmap } from "./ui.js";

// ─── Configuration ───────────────────────────────────────────────────────────

const API_BASE = ""; // same origin — FastAPI serves the frontend

const algorithms = {
	greedy: {
		label: "Greedy Search (Largest Enrollment)",
		note: "Assigns the busiest exam first to the tightest-fitting non-conflicting slot. Fast but no backtracking.",
	},
	csp: {
		label: "CSP (MRV + Forward Checking)",
		note: "Backtracking search with Minimum Remaining Values heuristic and forward checking. Time-limited on the Python backend.",
	},
	ga: {
		label: "Genetic Algorithm (Roulette Wheel + Elitism)",
		note: "Evolves a population of schedules using crossover, mutation, and fitness-based selection. Runs on the Python backend.",
	},
	a_star: {
		label: "A* Search (Conflict Density Heuristic)",
		note: "Explores partial schedules, prioritizing assignments that leave fewer high-conflict exams unscheduled.",
	},
};

// ─── State ───────────────────────────────────────────────────────────────────

let dataset = null;
let currentAbort = null;

// Default timeslots for the fake dataset
const DEFAULT_TIMESLOTS = [
	"2026-06-10 09:00", "2026-06-10 14:00", "2026-06-10 17:30",
	"2026-06-11 09:00", "2026-06-11 14:00", "2026-06-11 17:30",
	"2026-06-12 09:00", "2026-06-12 14:00",
	"2026-06-13 09:00", "2026-06-13 14:00",
];

// ─── Progress ────────────────────────────────────────────────────────────────

function showProgress(percent, message) {
	const container = document.getElementById("progress-container");
	const bar = document.getElementById("progress-bar");
	const msg = document.getElementById("progress-message");
	container.style.display = "block";
	bar.style.width = percent + "%";
	if (msg && message) msg.textContent = message;
}

function hideProgress() {
	document.getElementById("progress-container").style.display = "none";
}

// ─── Theme toggle ────────────────────────────────────────────────────────────

function initThemeToggle() {
	const toggle = document.getElementById("theme-toggle");
	const track = document.getElementById("toggle-track");
	let isNeo = true;

	toggle.addEventListener("click", () => {
		isNeo = !isNeo;
		document.documentElement.setAttribute(
			"data-theme",
			isNeo ? "neo-brutalism" : ""
		);
		track.classList.toggle("active", isNeo);
	});
}

// ─── CSV Upload ──────────────────────────────────────────────────────────────

function initCSVUpload() {
	const input = document.getElementById("csv-file-input");
	const filenameEl = document.getElementById("csv-filename");

	input.addEventListener("change", async (e) => {
		const file = e.target.files[0];
		if (!file) return;

		filenameEl.textContent = `Uploading: ${file.name}...`;

		const formData = new FormData();
		formData.append("file", file);

		try {
			const res = await fetch(`${API_BASE}/api/upload-csv`, {
				method: "POST",
				body: formData,
			});

			if (!res.ok) {
				const err = await res.json();
				throw new Error(err.detail || "Upload failed");
			}

			const data = await res.json();

			// Ensure timeslots exist
			if (!data.timeslots || data.timeslots.length === 0) {
				data.timeslots = DEFAULT_TIMESLOTS;
			}

			// Reshape for the frontend rendering
			dataset = reshapeDataset(data);
			renderDataOverview(dataset);
			filenameEl.textContent = `✅ Loaded ${file.name} — ${data.courses.length} courses, ${data.students.length} students, ${data.rooms.length} rooms`;
		} catch (err) {
			filenameEl.textContent = `❌ Error: ${err.message}`;
			console.error("CSV upload error:", err);
		}
	});
}

// ─── Data helpers ────────────────────────────────────────────────────────────

function reshapeDataset(raw) {
	// Create time slot objects for the frontend grid and heatmap
	const timeSlots = (raw.timeslots || DEFAULT_TIMESLOTS).map((ts, index) => {
		// ts can be a string "YYYY-MM-DD HH:MM" or an object {date: "..."}
		const dateStr = typeof ts === "string" ? ts : ts.date;
		const parts = dateStr.split(" ");
		const datePart = parts[0];
		const timePart = parts[1] || "09:00";
		const dayNames = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
		const d = new Date(datePart);
		const dayShort = dayNames[d.getDay()] || datePart;

		return {
			id: `${datePart}-${timePart.replace(":", "")}`,
			day: datePart,
			label: `${dayShort} ${datePart} • ${timePart}`,
			durationMins: 120,
			index,
			date: dateStr,
		};
	});

	return {
		courses: raw.courses || [],
		students: raw.students || [],
		rooms: raw.rooms || [],
		timeSlots,
		timeslotStrings: (raw.timeslots || DEFAULT_TIMESLOTS).map(
			(ts) => (typeof ts === "string" ? ts : ts.date)
		),
	};
}

// ─── Run algorithm via SSE ───────────────────────────────────────────────────

async function runStrategy(key) {
	if (!dataset) return;

	// Abort previous request
	if (currentAbort) currentAbort.abort();
	currentAbort = new AbortController();

	// UI feedback
	Array.from(document.querySelectorAll(".algo-btn")).forEach((btn) =>
		btn.classList.remove("active")
	);
	const buttons = Array.from(document.querySelectorAll("button.algo-btn"));
	const button = buttons.find(
		(btn) => btn.textContent === algorithms[key].label
	);
	button?.classList.add("active");

	document.getElementById("algo-note").textContent = algorithms[key].note;
	showProgress(0, "Sending request to backend...");

	const start = performance.now();

	// Build request payload
	const payload = {
		courses: dataset.courses.map((c) => ({
			code: c.code,
			name: c.name,
			enrollment: c.enrollment,
		})),
		students: dataset.students.map((s) => ({
			id: s.id,
			courses: s.courses,
		})),
		rooms: dataset.rooms.map((r) => ({
			name: r.name,
			capacity: r.capacity,
		})),
		timeslots: dataset.timeslotStrings.map((d) => ({ date: d })),
	};

	try {
		const response = await fetch(`${API_BASE}/api/schedule/${key}`, {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify(payload),
			signal: currentAbort.signal,
		});

		if (!response.ok) {
			throw new Error(`Server error: ${response.status}`);
		}

		// Parse SSE stream
		const reader = response.body.getReader();
		const decoder = new TextDecoder();
		let buffer = "";

		while (true) {
			const { done, value } = await reader.read();
			if (done) break;

			buffer += decoder.decode(value, { stream: true });
			const lines = buffer.split("\n");
			buffer = lines.pop(); // keep incomplete line

			let eventType = null;
			for (const line of lines) {
				if (line.startsWith("event: ")) {
					eventType = line.slice(7).trim();
				} else if (line.startsWith("data: ") && eventType) {
					const data = JSON.parse(line.slice(6));

					if (eventType === "progress") {
						showProgress(data.percent, data.message);
					} else if (eventType === "result") {
						handleResult(data, key, start);
					} else if (eventType === "error") {
						console.error("Algorithm error:", data.error);
						hideProgress();
					}
					eventType = null;
				}
			}
		}
	} catch (err) {
		if (err.name !== "AbortError") {
			console.error("Schedule request error:", err);
			document.getElementById("algo-note").textContent =
				`Error: ${err.message}. Make sure the FastAPI server is running.`;
		}
		hideProgress();
	}
}

function handleResult(result, key, start) {
	const end = performance.now();
	hideProgress();

	// Convert backend assignments to the format expected by ui.js
	const assignments = result.assignments.map((a) => ({
		course: {
			code: a.course_code,
			name: a.course_name,
			enrollment: a.enrollment,
			durationMins: 120,
		},
		room: { name: a.room_name, capacity: a.room_capacity },
		slot: {
			id: `${a.timeslot_date.split(" ")[0]}-${(a.timeslot_date.split(" ")[1] || "0900").replace(":", "")}`,
			day: a.timeslot_date.split(" ")[0],
			label: a.timeslot_date,
			durationMins: 120,
			index: dataset.timeslotStrings.indexOf(a.timeslot_date),
		},
	}));

	// Compute simple penalties for display
	const penalty = computePenalties(assignments);

	renderSchedule(assignments, {
		label: algorithms[key].label,
		time: result.elapsed_seconds * 1000,
		penalty: penalty.total,
		softViolations: penalty.softViolations,
		students: dataset.students,
	});

	buildMasterGrid(assignments, dataset.rooms, dataset.timeSlots);
	buildHeatmap(assignments, dataset.students);

	document.getElementById("score-note").textContent =
		`${assignments.length} assignments · Fitness: ${result.fitness} · Server time: ${result.elapsed_seconds}s · Algorithm: ${result.algorithm}`;
}

function computePenalties(assignments) {
	let hardViolations = 0;
	let softViolations = 0;
	const seen = new Set();

	assignments.forEach((a) => {
		const k = `${a.slot.id}-${a.room.name}`;
		if (seen.has(k)) hardViolations++;
		seen.add(k);
	});

	if (dataset.students) {
		dataset.students.forEach((student) => {
			const slots = assignments
				.filter((a) => student.courses.includes(a.course.code))
				.map((a) => a.slot.index)
				.sort((a, b) => a - b);
			for (let i = 0; i < slots.length - 1; i++) {
				if (slots[i + 1] - slots[i] === 1) softViolations++;
			}
		});
	}

	return {
		total: hardViolations * 50 + softViolations * 3,
		hardViolations,
		softViolations,
	};
}

// ─── Init ────────────────────────────────────────────────────────────────────

async function init() {
	// Load default data
	const raw = await fetch("data/fake-data.json").then((r) => r.json());

	// Add default timeslots
	raw.timeslots = DEFAULT_TIMESLOTS;
	dataset = reshapeDataset(raw);
	renderDataOverview(dataset);

	// Build algorithm buttons
	const controlBar = document.getElementById("strategy-controls");
	Object.entries(algorithms).forEach(([key, config], index) => {
		const button = document.createElement("button");
		button.className = "algo-btn";
		button.textContent = config.label;
		button.addEventListener("click", () => runStrategy(key));
		if (index === 0) button.classList.add("active");
		controlBar.appendChild(button);
	});

	// Init features
	initThemeToggle();
	initCSVUpload();

	// Run default algorithm
	runStrategy("ga");
}

init();
