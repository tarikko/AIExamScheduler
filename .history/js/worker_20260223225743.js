// Web Worker for running scheduling algorithms in the background
import { greedySchedule } from "./algorithms/greedy.js";
import { cspSchedule } from "./algorithms/csp.js";
import { gaSchedule } from "./algorithms/ga.js";
import { aStarSchedule } from "./algorithms/astar.js";

const algos = {
	greedy: greedySchedule,
	csp: (data, onProgress) => cspSchedule(data), // Simple CSP doesn't support progress easily
	ga: gaSchedule,
	a_star: (data, onProgress) => aStarSchedule(data), // A* search
};

onmessage = async (e) => {
	const { key, dataset } = e.data;
	const algoFn = algos[key];

	if (!algoFn) {
		postMessage({ type: "error", error: "Algorithm not found" });
		return;
	}

	const onProgress = (percent) => {
		postMessage({ type: "progress", percent });
	};

	try {
		const result = algoFn(dataset, onProgress);
		postMessage({ type: "result", result });
	} catch (err) {
		postMessage({ type: "error", error: err.message });
	}
};
