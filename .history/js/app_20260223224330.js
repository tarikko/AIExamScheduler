import { timeSlots } from "./time-slots.js";
import { assessPenalties } from "./utils.js";
import {
	renderDataOverview,
	renderSchedule,
	buildMasterGrid,
	buildHeatmap,
} from "./ui.js";
import { greedySchedule } from "./algorithms/greedy.js";
import { cspSchedule } from "./algorithms/csp.js";
import { gaSchedule } from "./algorithms/ga.js";
import { aStarSchedule } from "./algorithms/astar.js";
import { benchmarks, loadBenchmark } from "./benchmarks.js";

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
	const { penalty, softViolations } = assessPenalties(
		result,
		dataset.students
	);

	document.getElementById("algo-note").textContent = algorithms[key].note;

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
}

init();
