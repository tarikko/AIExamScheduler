import {
	renderDataOverview,
	renderSchedule,
	buildMasterGrid,
	buildHeatmap,
} from "./ui.js";

const API_BASE = window.location.protocol === "file:" ? "http://127.0.0.1:8000" : "";

const algorithms = {
	greedy: {
		label: "Greedy Search",
		note: "Places high-conflict, high-enrollment exams first using the best local room-timeslot.",
	},
	csp: {
		label: "CSP",
		note: "Backtracking with MRV and forward checking, time-limited on the backend.",
	},
	ga: {
		label: "Genetic Algorithm",
		note: "Evolves schedules with elitism, crossover, mutation, and a greedy feasible seed.",
	},
	a_star: {
		label: "A* Search",
		note: "Explores partial schedules using soft-cost and remaining-conflict heuristics.",
	},
};

let dataset = null;
let currentAbort = null;
let latestSolution = null;

function showProgress(percent, message) {
	const container = document.getElementById("progress-container");
	const bar = document.getElementById("progress-bar");
	const msg = document.getElementById("progress-message");
	container.style.display = "block";
	bar.style.width = `${percent}%`;
	if (msg && message) msg.textContent = message;
}

function hideProgress() {
	document.getElementById("progress-container").style.display = "none";
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

async function loadJson(url, options = {}) {
	const res = await fetch(url, options);
	if (!res.ok) {
		const err = await res.json().catch(() => ({}));
		throw new Error(err.detail || `Request failed: ${res.status}`);
	}
	return res.json();
}

function reshapeDataset(raw) {
	const timeslotStrings = raw.timeslots || [];
	const timeSlots = timeslotStrings.map((dateStr, index) => {
		const [datePart, timePart = "09:00"] = dateStr.split(" ");
		const d = new Date(`${datePart}T${timePart}`);
		const dayNames = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
		const dayShort = Number.isNaN(d.getTime()) ? datePart : dayNames[d.getDay()];
		return {
			id: `${datePart}-${timePart.replace(":", "")}`,
			day: datePart,
			label: `${dayShort} ${datePart} - ${timePart}`,
			durationMins: 120,
			index,
			date: dateStr,
		};
	});

	return {
		courses: (raw.courses || []).map((course) => ({
			code: course.code,
			name: course.name,
			enrollment: Number(course.enrollment || 0),
			durationMins: Number(course.duration_minutes || course.durationMins || 120),
		})),
		students: raw.students || [],
		rooms: (raw.rooms || []).map((room) => ({
			name: room.name,
			capacity: Number(room.capacity || 0),
		})),
		timeSlots,
		timeslotStrings,
		metadata: raw.metadata || {},
	};
}

function setDataset(raw, statusText) {
	dataset = reshapeDataset(raw);
	latestSolution = null;
	document.getElementById("export-controls").hidden = true;
	renderDataOverview(dataset);
	buildMasterGrid([], dataset.rooms, dataset.timeSlots);
	buildHeatmap([], dataset.students, []);
	document.getElementById("schedule-results").innerHTML = "";
	document.getElementById("score-note").textContent = statusText;
}

function setBenchmarkDataset(benchmark, statusText) {
	dataset = {
		kind: "benchmark",
		benchmarkName: benchmark.folder || benchmark.name,
		courses: [],
		students: [],
		rooms: [],
		timeSlots: [],
		timeslotStrings: [],
		metadata: {
			source: benchmark.name,
			exam_count: benchmark.exams || 0,
			student_count: benchmark.students || 0,
			room_count: benchmark.rooms || 0,
			timeslot_count: benchmark.timeslots || 0,
			enrolment_rows: benchmark.enrolment_rows || 0,
		},
	};
	latestSolution = null;
	document.getElementById("export-controls").hidden = true;
	renderDataOverview(dataset);
	buildMasterGrid([], [], []);
	buildHeatmap([], [], []);
	document.getElementById("schedule-results").innerHTML = "";
	document.getElementById("score-note").textContent = statusText;
}

function getActiveAlgorithm() {
	return document.querySelector(".algo-btn[data-algo].active")?.dataset.algo || "greedy";
}

async function initBenchmarkSelector() {
	const select = document.getElementById("benchmark-select");
	const data = await loadJson(`${API_BASE}/api/benchmarks`);
	select.innerHTML = "";
	let defaultBenchmark = null;
	data.benchmarks.forEach((benchmark) => {
		const option = document.createElement("option");
		option.value = benchmark.folder || benchmark.name;
		option.textContent = `${benchmark.name} (${benchmark.exams || "?"} exams, ${benchmark.students || "?"} students)`;
		option.dataset.benchmark = JSON.stringify(benchmark);
		if (benchmark.name === "random_sp_06_synthetic") {
			option.selected = true;
			defaultBenchmark = benchmark;
		}
		select.appendChild(option);
	});
	if (!defaultBenchmark) defaultBenchmark = data.benchmarks[0];

	document.getElementById("load-benchmark-btn").addEventListener("click", async () => {
		const benchmark = JSON.parse(select.selectedOptions[0].dataset.benchmark);
		setBenchmarkDataset(benchmark, `Selected benchmark ${benchmark.name}.`);
		runStrategy(getActiveAlgorithm());
	});

	return defaultBenchmark;
}

function initCSVUpload() {
	const input = document.getElementById("csv-file-input");
	const filenameEl = document.getElementById("csv-filename");

	input.addEventListener("change", async (event) => {
		const files = Array.from(event.target.files || []);
		if (!files.length) return;

		const names = new Set(files.map((file) => file.name.toLowerCase()));
		const required = ["rooms.csv", "timeslots.csv", "exams.csv", "enrollements.csv"];
		const missing = required.filter((name) => !names.has(name));
		if (files.length !== 4 || missing.length) {
			filenameEl.textContent = `Select exactly: ${required.join(", ")}`;
			return;
		}

		filenameEl.textContent = "Uploading dataset...";
		const formData = new FormData();
		files.forEach((file) => formData.append("files", file));

		try {
			const raw = await loadJson(`${API_BASE}/api/upload-dataset`, {
				method: "POST",
				body: formData,
			});
			setDataset(raw, "Uploaded dataset loaded.");
			filenameEl.textContent = `Loaded ${raw.metadata.exam_count} exams, ${raw.metadata.student_count} students, ${raw.metadata.room_count} rooms.`;
			runStrategy(getActiveAlgorithm());
		} catch (err) {
			filenameEl.textContent = `Error: ${err.message}`;
		}
	});
}

function buildRequestPayload() {
	return {
		courses: dataset.courses.map((course) => ({
			code: course.code,
			name: course.name,
			enrollment: course.enrollment,
			duration_minutes: course.durationMins,
		})),
		students: dataset.students.map((student) => ({
			id: student.id,
			courses: student.courses,
		})),
		rooms: dataset.rooms,
		timeslots: dataset.timeslotStrings.map((date) => ({ date })),
	};
}

async function runStrategy(key) {
	if (!dataset) return;
	if (currentAbort) currentAbort.abort();
	currentAbort = new AbortController();

	document.querySelectorAll(".algo-btn[data-algo]").forEach((btn) => btn.classList.remove("active"));
	document.querySelector(`.algo-btn[data-algo="${key}"]`)?.classList.add("active");
	document.getElementById("algo-note").textContent = algorithms[key].note;
	showProgress(0, "Sending request to backend...");

	try {
		const response = dataset.kind === "benchmark"
			? await fetch(`${API_BASE}/api/schedule-benchmark/${key}/${encodeURIComponent(dataset.benchmarkName)}`, {
				method: "POST",
				signal: currentAbort.signal,
			})
			: await fetch(`${API_BASE}/api/schedule/${key}`, {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify(buildRequestPayload()),
				signal: currentAbort.signal,
			});

		if (!response.ok) throw new Error(`Server error: ${response.status}`);

		const reader = response.body.getReader();
		const decoder = new TextDecoder();
		let buffer = "";
		let eventType = null;

		while (true) {
			const { done, value } = await reader.read();
			if (done) break;
			buffer += decoder.decode(value, { stream: true });
			const lines = buffer.split("\n");
			buffer = lines.pop();

			for (const line of lines) {
				if (line.startsWith("event: ")) {
					eventType = line.slice(7).trim();
				} else if (line.startsWith("data: ") && eventType) {
					const data = JSON.parse(line.slice(6));
					if (eventType === "progress") showProgress(data.percent, data.message);
					if (eventType === "result") handleResult(data, key);
					if (eventType === "error") throw new Error(data.error);
					eventType = null;
				}
			}
		}
	} catch (err) {
		if (err.name !== "AbortError") {
			document.getElementById("algo-note").textContent = `Error: ${err.message}`;
		}
		hideProgress();
	}
}

function handleResult(result, key) {
	hideProgress();
	if (result.dataset) {
		dataset = {
			...reshapeDataset(result.dataset),
			kind: "benchmark",
			benchmarkName: result.dataset.metadata?.source || dataset?.benchmarkName,
		};
		renderDataOverview(dataset);
	}
	const assignments = result.assignments.map((assignment) => {
		const [datePart, timePart = "09:00"] = assignment.timeslot_date.split(" ");
		return {
			course: {
				code: assignment.course_code,
				name: assignment.course_name,
				enrollment: assignment.enrollment,
				durationMins: assignment.duration_minutes || 120,
			},
			room: { name: assignment.room_name, capacity: assignment.room_capacity },
			slot: {
				id: `${datePart}-${timePart.replace(":", "")}`,
				day: datePart,
				label: assignment.timeslot_date,
				durationMins: 120,
				index: dataset.timeslotStrings.indexOf(assignment.timeslot_date),
			},
		};
	});

	latestSolution = { result, assignments, dataset, algorithm: key };
	renderSchedule(assignments, {
		label: algorithms[key].label,
		metrics: result.metrics || {},
		students: dataset.students,
	});
	buildMasterGrid(assignments, dataset.rooms, dataset.timeSlots);
	buildHeatmap(assignments, dataset.students, result.metrics?.room_daily_load || []);
	document.getElementById("export-controls").hidden = false;
	document.getElementById("score-note").textContent =
		`${assignments.length} assignments | Fitness ${result.fitness} | Server time ${result.elapsed_seconds}s | ${result.algorithm}`;
}

function csvEscape(value) {
	const text = String(value ?? "");
	return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function downloadText(filename, mime, text) {
	const blob = new Blob([text], { type: mime });
	const url = URL.createObjectURL(blob);
	const link = document.createElement("a");
	link.href = url;
	link.download = filename;
	link.click();
	URL.revokeObjectURL(url);
}

function exportCSV() {
	if (!latestSolution) return;
	const rows = [
		["exam code", "exam name", "enrollment", "duration minutes", "room name", "room capacity", "timeslot"],
		...latestSolution.assignments.map((assignment) => [
			assignment.course.code,
			assignment.course.name,
			assignment.course.enrollment,
			assignment.course.durationMins,
			assignment.room.name,
			assignment.room.capacity,
			assignment.slot.label,
		]),
	];
	downloadText("exam-schedule.csv", "text/csv", rows.map((row) => row.map(csvEscape).join(",")).join("\n"));
}

function exportJSON() {
	if (!latestSolution) return;
	downloadText("exam-schedule.json", "application/json", JSON.stringify(latestSolution.result, null, 2));
}

async function init() {
	initThemeToggle();
	initCSVUpload();
	const defaultBenchmark = await initBenchmarkSelector();

	document.getElementById("export-csv-btn").addEventListener("click", exportCSV);
	document.getElementById("export-json-btn").addEventListener("click", exportJSON);

	const controlBar = document.getElementById("strategy-controls");
	Object.entries(algorithms).forEach(([key, config], index) => {
		const button = document.createElement("button");
		button.className = "algo-btn";
		button.dataset.algo = key;
		button.textContent = config.label;
		button.addEventListener("click", () => runStrategy(key));
		if (index === 0) button.classList.add("active");
		controlBar.appendChild(button);
	});

	setBenchmarkDataset(defaultBenchmark, `Selected benchmark ${defaultBenchmark.name}.`);
	runStrategy("greedy");
}

init().catch((err) => {
	document.getElementById("score-note").textContent = `Initialization error: ${err.message}`;
});
