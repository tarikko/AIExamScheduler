import { timeSlots } from "./time-slots.js";
import { assessPenalties } from "./utils.js";
import {
	renderDataOverview,
	renderSchedule,
	buildMasterGrid,
	buildHeatmap,
} from "./ui.js";
import { loadBenchmark } from "./benchmarks.js";

const algorithms = {
	greedy: {
		label: "Greedy Search (Largest Enrollment + Degree)",
		note: "Assigns the busiest exam to the first available non-conflicting slot. Penalties reward compact days.",
	},
	csp: {
		label: "CSP (MRV + Forward Checking)",
		note: "Backtracking with Minimum Remaining Values and forward checking to prune conflicts early.",
	},
	ga: {
		label: "Genetic Algorithm (Week Swap Crossover)",
		note: "Evolves schedule strings with heavy fitness penalty for hard violations, light for soft.",
	},
	a_star: {
		label: "A* Search (Conflict Density Heuristic)",
		note: "Explores partial states, prioritizing boards that leave fewer high-conflict exams unscheduled.",
	},
};

let dataset;
let bestCompare = {};
let schedulerWorker = null;

function updateProgressBar(percent) {
	const container = document.getElementById("progress-container");
	const bar = document.getElementById("progress-bar");
	container.style.display = "block";
	bar.style.width = percent + "%";
}

function runStrategy(key) {
	if (!dataset) return;
	
	// UI Feedback
	Array.from(document.querySelectorAll(".algo-btn")).forEach((btn) =>
		btn.classList.remove("active")
	);
	const buttons = Array.from(document.querySelectorAll("button.algo-btn"));
	const button = buttons.find((btn) => btn.textContent === algorithms[key].label);
	button?.classList.add("active");

	document.getElementById("algo-note").textContent = algorithms[key].note;
	updateProgressBar(0);

	// Start Background Worker
	const start = performance.now();

	if (schedulerWorker) {
		schedulerWorker.terminate();
	}
	schedulerWorker = new Worker("./js/worker.js", { type: "module" });

	schedulerWorker.onmessage = (e) => {
		const { type, percent, result, error } = e.data;
		
		if (type === "progress") {
			updateProgressBar(percent);
		} else if (type === "result") {
			const end = performance.now();
			const { penalty, softViolations } = assessPenalties(result, dataset.students);
			
			renderSchedule(result, {
				label: algorithms[key].label,
				time: end - start,
				penalty,
				softViolations,
				students: dataset.students,
			});

			buildMasterGrid(result, dataset.rooms, timeSlots);
			buildHeatmap(result, dataset.students);
			updateComparison(key, {
				label: algorithms[key].label,
				penalty,
				time: end - start,
			});

			document.getElementById("progress-container").style.display = "none";
		} else if (type === "error") {
			console.error("Worker error:", error);
			document.getElementById("progress-container").style.display = "none";
		}
	};

	schedulerWorker.postMessage({ key, dataset });
}

init();
