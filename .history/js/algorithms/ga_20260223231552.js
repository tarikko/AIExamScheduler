import { timeSlots } from "../time-slots.js";
import { buildConflicts } from "../utils.js";

export function gaSchedule(data, onProgress) {
	const populationSize = 40;
	const generations = 90;
	const rooms = data.rooms;
	const slots = data.timeSlots || timeSlots;
	const combos = slots.flatMap((slot) =>
		rooms.map((room) => ({ slot, room }))
	);
	const conflicts = buildConflicts(data);

	function randomIndividual() {
		return data.courses.map((course) => {
			const domain = combos.filter(
				(combo) => combo.room.capacity >= course.enrollment && combo.slot.durationMins >= course.durationMins
			);
			return domain[Math.floor(Math.random() * domain.length)];
		});
	}

	function computeFitness(individual) {
		let hard = 0;
		let soft = 0;
		for (let i = 0; i < individual.length; i++) {
			const assignA = individual[i];
			const courseA = data.courses[i];
			
			if (courseA.durationMins > assignA.slot.durationMins) hard += 10;

			for (let j = i + 1; j < individual.length; j++) {
				const assignB = individual[j];
				const courseB = data.courses[j];
				
				if (assignA.slot.id === assignB.slot.id) {
					if (assignA.room.name === assignB.room.name) {
						hard += 3;
					}
					if (conflicts[courseA.code].has(courseB.code)) {
						hard += 5;
					}
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

	let population = Array.from({ length: populationSize }, randomIndividual);
	for (let generation = 0; generation < generations; generation++) {
		if (onProgress && generation % 5 === 0) onProgress((generation / generations) * 100);
		population.sort((a, b) => computeFitness(b) - computeFitness(a));
		if (Math.random() < 0.4) {
			const [childA, childB] = crossover(population[0], population[1]);
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
	if (onProgress) onProgress(100);
	return best.map((assignment, index) => ({
		course: data.courses[index],
		slot: assignment.slot,
		room: assignment.room,
	}));
}
