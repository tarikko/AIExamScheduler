import { timeSlots } from "../time-slots.js";

export function gaSchedule(data, onProgress) {
	const populationSize = 40;
	const generations = 90;
	const rooms = data.rooms;
	const combos = timeSlots.flatMap((slot) =>
		rooms.map((room) => ({ slot, room }))
	);

	function randomIndividual() {
		return data.courses.map((course) => {
			const domain = combos.filter(
				(combo) => combo.room.capacity >= course.enrollment
			);
			return domain[Math.floor(Math.random() * domain.length)];
		});
	}

	// Helper for checking student overlaps
	const studentsTakingCourse = new Map();
	data.courses.forEach(c => {
		studentsTakingCourse.set(c.code, data.students.filter(s => s.courses.includes(c.code)));
	});

	function computeFitness(individual) {
		let hard = 0;
		let soft = 0;
		for (let i = 0; i < individual.length; i++) {
			for (let j = i + 1; j < individual.length; j++) {
				const courseA = individual[i];
				const courseB = individual[j];
				if (courseA.slot.id === courseB.slot.id) {
					if (courseA.room.name === courseB.room.name) {
						hard += 3;
					}
					const codeA = data.courses[i].code;
					const codeB = data.courses[j].code;
					const studentsA = studentsTakingCourse.get(codeA);
					const studentsB = studentsTakingCourse.get(codeB);
					const conflict = studentsA.some(sA => studentsB.some(sB => sB.id === sA.id));
					
					if (conflict) hard += 5;
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
