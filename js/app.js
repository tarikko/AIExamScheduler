/**
 * Main application that connects the frontend to the FastAPI backend.
 */

import { renderDataOverview, renderSchedule, buildMasterGrid, buildHeatmap } from "./ui.js";
import { fetchBenchmarkCatalog, loadBenchmark } from "./benchmarks.js";

const API_BASE = "";

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

const DEFAULT_TIMESLOTS = [
	"2026-06-10 09:00", "2026-06-10 14:00", "2026-06-10 17:30",
	"2026-06-11 09:00", "2026-06-11 14:00", "2026-06-11 17:30",
	"2026-06-12 09:00", "2026-06-12 14:00",
	"2026-06-13 09:00", "2026-06-13 14:00",
];

const ALL_ALGORITHM_KEYS = Object.keys(algorithms);

let dataset = null;
let currentAbort = null;
const algorithmButtons = new Map();

function showProgress(percent, message) {
	const container = document.getElementById("progress-container");
	const bar = document.getElementById("progress-bar");
	const msg = document.getElementById("progress-message");
	container.style.display = "block";
	bar.style.width = percent + "%";
	if (msg && message) {
		msg.textContent = message;
	}
}

function hideProgress() {
	document.getElementById("progress-container").style.display = "none";
}

function resetResults() {
	document.getElementById("schedule-results").innerHTML = "";
	document.getElementById("master-grid").innerHTML = "";
	document.getElementById("heatmap").innerHTML = "";
	document.getElementById("score-note").textContent = "";
	hideProgress();
}

function initThemeToggle() {
	const toggle = document.getElementById("theme-toggle");
	const track = document.getElementById("toggle-track");
	let isNeo = true;

	toggle.addEventListener("click", () => {
		isNeo = !isNeo;
		document.documentElement.setAttribute("data-theme", isNeo ? "neo-brutalism" : "");
		track.classList.toggle("active", isNeo);
	});
}

function normalizeMeta(meta = {}) {
	const availableAlgorithms = Array.isArray(meta.available_algorithms) && meta.available_algorithms.length > 0
		? meta.available_algorithms
		: ALL_ALGORITHM_KEYS;

	return {
		source: meta.source || "default",
		name: meta.name || "Current dataset",
		defaultAlgorithm: meta.default_algorithm || "ga",
		availableAlgorithms,
		runNote: meta.run_note || "",
		roomSlotCapacity: meta.room_slot_capacity || null,
		canFullyPlace: meta.can_fully_place,
		summary: meta.summary || "",
	};
}

function reshapeDataset(raw, meta = {}) {
	const rawTimeslots = raw.timeslots && raw.timeslots.length > 0 ? raw.timeslots : DEFAULT_TIMESLOTS;

	const timeSlots = rawTimeslots.map((ts, index) => {
		const normalized = typeof ts === "string" ? { date: ts, durationMins: 120 } : ts;
		const dateStr = normalized.date;
		const parts = dateStr.split(" ");
		const datePart = parts[0];
		const timePart = parts[1] || "09:00";
		const dayNames = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
		const dayShort = dayNames[new Date(datePart).getDay()] || datePart;

		return {
			id: `${datePart}-${timePart.replace(":", "")}`,
			day: datePart,
			label: `${dayShort} ${datePart} • ${timePart}`,
			durationMins: normalized.durationMins || 120,
			index,
			date: dateStr,
		};
	});

	return {
		courses: raw.courses || [],
		students: raw.students || [],
		rooms: raw.rooms || [],
		timeSlots,
		timeslotStrings: timeSlots.map((slot) => slot.date),
		meta: normalizeMeta(meta),
	};
}

function setDataset(raw, meta = {}) {
	dataset = reshapeDataset(raw, meta);
	renderDataOverview(dataset);
	resetResults();
	updateAlgorithmAvailability();
	updateDatasetNotes();
}

function updateAlgorithmAvailability() {
	const allowed = new Set(dataset?.meta?.availableAlgorithms || ALL_ALGORITHM_KEYS);
	let firstEnabledKey = null;

	for (const [key, button] of algorithmButtons.entries()) {
		const enabled = allowed.has(key);
		button.disabled = false;
		button.dataset.available = enabled ? "true" : "false";
		button.classList.toggle("is-disabled", !enabled);
		button.title = enabled ? "" : "Disabled for this dataset.";
		if (enabled && !firstEnabledKey) {
			firstEnabledKey = key;
		}
		if (!enabled) {
			button.classList.remove("active");
		}
	}

	const activeEnabled = Array.from(algorithmButtons.entries()).some(
		([, button]) => button.classList.contains("active") && button.dataset.available !== "false"
	);

	if (!activeEnabled && firstEnabledKey) {
		algorithmButtons.get(firstEnabledKey)?.classList.add("active");
	}
}

function updateDatasetNotes() {
	const benchmarkNote = document.getElementById("benchmark-note");
	const benchmarkStatus = document.getElementById("benchmark-status");

	if (dataset?.meta?.source === "benchmark") {
		const roomSlotText = dataset.meta.roomSlotCapacity
			? `Room-slot capacity: ${dataset.meta.roomSlotCapacity}.`
			: "";
		benchmarkNote.textContent = dataset.meta.runNote || "Benchmark dataset loaded.";
		benchmarkStatus.textContent = `${dataset.meta.name} loaded — ${dataset.courses.length} exams, ${dataset.students.length} students, ${dataset.rooms.length} rooms. ${roomSlotText}`.trim();
	} else if (!benchmarkStatus.textContent) {
		benchmarkNote.textContent = "Load large datasets from the local benchmark folder and run the recommended solver directly from the website.";
	}
}

function buildRequestPayload() {
	const payload = {
		courses: dataset.courses.map((course) => ({
			code: course.code,
			name: course.name,
			enrollment: course.enrollment,
		})),
		students: dataset.students.map((student) => ({
			id: student.id,
			courses: student.courses,
		})),
		rooms: dataset.rooms.map((room) => ({
			name: room.name,
			capacity: room.capacity,
		})),
		timeslots: dataset.timeslotStrings.map((date) => ({ date })),
	};

	if (dataset.courses.length > 200) {
		payload.generations = 20;
		payload.population_size = 24;
		payload.time_limit_sec = 2.5;
	}

	return payload;
}

function setActiveAlgorithmButton(key) {
	for (const button of algorithmButtons.values()) {
		button.classList.remove("active");
	}
	algorithmButtons.get(key)?.classList.add("active");
}

function describeAlgorithm(key) {
	const baseNote = algorithms[key].note;
	const runNote = dataset?.meta?.runNote;
	return runNote ? `${baseNote} ${runNote}` : baseNote;
}

async function initCSVUpload() {
	const input = document.getElementById("csv-file-input");
	const filenameEl = document.getElementById("csv-filename");

	input.addEventListener("change", async (event) => {
		const file = event.target.files[0];
		if (!file) {
			return;
		}

		filenameEl.textContent = `Uploading: ${file.name}...`;

		const formData = new FormData();
		formData.append("file", file);

		try {
			const response = await fetch(`${API_BASE}/api/upload-csv`, {
				method: "POST",
				body: formData,
			});

			if (!response.ok) {
				const error = await response.json();
				throw new Error(error.detail || "Upload failed");
			}

			const data = await response.json();
			setDataset(data, {
				source: "csv",
				name: file.name,
				default_algorithm: "ga",
				available_algorithms: ALL_ALGORITHM_KEYS,
			});

			filenameEl.textContent = `Loaded ${file.name} — ${data.courses.length} courses, ${data.students.length} students, ${data.rooms.length} rooms`;
			await runStrategy(dataset.meta.defaultAlgorithm);
		} catch (error) {
			filenameEl.textContent = `Upload error: ${error.message}`;
			console.error("CSV upload error:", error);
		}
	});
}

async function initBenchmarkLibrary() {
	const select = document.getElementById("benchmark-select");
	const button = document.getElementById("load-benchmark-btn");
	const status = document.getElementById("benchmark-status");
	const note = document.getElementById("benchmark-note");

	try {
		const benchmarks = await fetchBenchmarkCatalog();

		select.innerHTML = "";
		if (benchmarks.length === 0) {
			select.innerHTML = '<option value="">No benchmarks found</option>';
			button.disabled = true;
			status.textContent = "No local benchmark datasets were found.";
			return;
		}

		for (const benchmark of benchmarks) {
			const option = document.createElement("option");
			option.value = benchmark.id;
			option.textContent = `${benchmark.name} (${benchmark.id})`;
			select.appendChild(option);
		}

		status.textContent = `${benchmarks.length} benchmark dataset(s) available.`;
		note.textContent = "Load large datasets from the local benchmark folder and run the recommended solver directly from the website.";

		button.addEventListener("click", async () => {
			if (!select.value) {
				return;
			}

			button.disabled = true;
			status.textContent = `Loading ${select.value}...`;

			try {
				const data = await loadBenchmark(select.value);
				setDataset(data, data.meta || {});
				button.disabled = false;
				await runStrategy(dataset.meta.defaultAlgorithm);
			} catch (error) {
				status.textContent = `Benchmark load error: ${error.message}`;
				console.error("Benchmark load error:", error);
			} finally {
				button.disabled = false;
			}
		});
	} catch (error) {
		select.innerHTML = '<option value="">Benchmarks unavailable</option>';
		button.disabled = true;
		status.textContent = "Benchmark catalog could not be loaded.";
		note.textContent = error.message;
		console.error("Benchmark catalog error:", error);
	}
}

async function runStrategy(key) {
	if (!dataset) {
		return;
	}

	if (!dataset.meta.availableAlgorithms.includes(key)) {
		document.getElementById("algo-note").textContent =
			`${algorithms[key].label} is not available for ${dataset.meta.name}. ${dataset.meta.runNote}`.trim();
		return;
	}

	if (currentAbort) {
		currentAbort.abort();
	}
	currentAbort = new AbortController();

	setActiveAlgorithmButton(key);
	document.getElementById("algo-note").textContent = describeAlgorithm(key);
	showProgress(0, "Sending request to backend...");

	try {
		const response = await fetch(`${API_BASE}/api/schedule/${key}`, {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify(buildRequestPayload()),
			signal: currentAbort.signal,
		});

		if (!response.ok) {
			throw new Error(`Server error: ${response.status}`);
		}

		const reader = response.body.getReader();
		const decoder = new TextDecoder();
		let buffer = "";
		let eventType = null;
		let dataLines = [];

		const dispatchEvent = () => {
			if (!eventType || dataLines.length === 0) {
				eventType = null;
				dataLines = [];
				return;
			}

			const data = JSON.parse(dataLines.join("\n"));

			if (eventType === "progress") {
				showProgress(data.percent, data.message);
			} else if (eventType === "result") {
				handleResult(data, key);
			} else if (eventType === "error") {
				document.getElementById("algo-note").textContent = `Algorithm error: ${data.error}`;
				hideProgress();
			}

			eventType = null;
			dataLines = [];
		};

		const processLine = (line) => {
			const normalized = line.endsWith("\r") ? line.slice(0, -1) : line;

			if (normalized === "") {
				dispatchEvent();
			} else if (normalized.startsWith("event:")) {
				eventType = normalized.slice(6).trim();
			} else if (normalized.startsWith("data:")) {
				dataLines.push(normalized.slice(5).trimStart());
			}
		};

		while (true) {
			const { done, value } = await reader.read();
			if (done) {
				break;
			}

			buffer += decoder.decode(value, { stream: true });
			const lines = buffer.split("\n");
			buffer = lines.pop();

			for (const line of lines) {
				processLine(line);
			}
		}

		buffer += decoder.decode();
		if (buffer) {
			processLine(buffer);
		}
		dispatchEvent();
	} catch (error) {
		if (error.name !== "AbortError") {
			console.error("Schedule request error:", error);
			document.getElementById("algo-note").textContent =
				`Error: ${error.message}. Make sure the FastAPI server is running.`;
		}
		hideProgress();
	}
}

function handleResult(result, key) {
	hideProgress();

	const courseByCode = new Map(dataset.courses.map((course) => [course.code, course]));
	const slotByDate = new Map(dataset.timeSlots.map((slot) => [slot.date, slot]));

	const assignments = result.assignments.map((assignment) => {
		const course = courseByCode.get(assignment.course_code) || {};
		const slot = slotByDate.get(assignment.timeslot_date);

		return {
			course: {
				code: assignment.course_code,
				name: assignment.course_name,
				enrollment: assignment.enrollment,
				durationMins: course.durationMins || 120,
			},
			room: { name: assignment.room_name, capacity: assignment.room_capacity },
			slot: slot || {
				id: `${assignment.timeslot_date.split(" ")[0]}-${(assignment.timeslot_date.split(" ")[1] || "0900").replace(":", "")}`,
				day: assignment.timeslot_date.split(" ")[0],
				label: assignment.timeslot_date,
				durationMins: 120,
				index: dataset.timeslotStrings.indexOf(assignment.timeslot_date),
				date: assignment.timeslot_date,
			},
		};
	});

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

	const scheduledCount = assignments.length;
	const totalCount = dataset.courses.length;
	document.getElementById("score-note").textContent =
		`${scheduledCount}/${totalCount} exams scheduled • Fitness: ${result.fitness} • Server time: ${result.elapsed_seconds}s • Algorithm: ${result.algorithm}`;
}

function computePenalties(assignments) {
	let hardViolations = 0;
	let softViolations = 0;
	const seen = new Set();

	assignments.forEach((assignment) => {
		const key = `${assignment.slot.id}-${assignment.room.name}`;
		if (seen.has(key)) {
			hardViolations += 1;
		}
		seen.add(key);
	});

	for (const student of dataset.students || []) {
		const slots = assignments
			.filter((assignment) => student.courses.includes(assignment.course.code))
			.map((assignment) => assignment.slot.index)
			.sort((a, b) => a - b);

		for (let index = 0; index < slots.length - 1; index += 1) {
			if (slots[index + 1] - slots[index] === 1) {
				softViolations += 1;
			}
		}
	}

	return {
		total: hardViolations * 50 + softViolations * 3,
		hardViolations,
		softViolations,
	};
}

function buildAlgorithmButtons() {
	const controlBar = document.getElementById("strategy-controls");
	controlBar.innerHTML = "";

	for (const [key, config] of Object.entries(algorithms)) {
		const button = document.createElement("button");
		button.className = "algo-btn";
		button.textContent = config.label;
		button.addEventListener("click", () => runStrategy(key));
		controlBar.appendChild(button);
		algorithmButtons.set(key, button);
	}
}

async function init() {
	buildAlgorithmButtons();
	initThemeToggle();
	await initCSVUpload();
	await initBenchmarkLibrary();

	const raw = await fetch("data/fake-data.json").then((response) => response.json());
	setDataset(raw, {
		source: "default",
		name: "Default dataset",
		default_algorithm: "ga",
		available_algorithms: ALL_ALGORITHM_KEYS,
	});

	await runStrategy(dataset.meta.defaultAlgorithm);
}

init();
