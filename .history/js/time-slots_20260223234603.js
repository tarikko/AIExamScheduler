/**
 * Generates a clean set of non-overlapping exam time slots for the fake dataset.
 * Each day has three slots: a 3-hour morning block and two 2-hour afternoon blocks.
 * Slots are self-contained in `data.timeSlots` — no algorithm needs to import this file directly.
 */
export function generateTimeSlots() {
	const schedule = [
		{
			day: "Monday",
			short: "Mon",
			slots: [
				{ start: "09:00", end: "12:00", mins: 180 },
				{ start: "13:00", end: "15:00", mins: 120 },
				{ start: "15:00", end: "17:00", mins: 120 },
			],
		},
		{
			day: "Tuesday",
			short: "Tue",
			slots: [
				{ start: "09:00", end: "12:00", mins: 180 },
				{ start: "13:00", end: "15:00", mins: 120 },
				{ start: "15:00", end: "17:00", mins: 120 },
			],
		},
		{
			day: "Wednesday",
			short: "Wed",
			slots: [
				{ start: "09:00", end: "12:00", mins: 180 },
				{ start: "13:00", end: "15:00", mins: 120 },
				{ start: "15:00", end: "17:00", mins: 120 },
			],
		},
	];

	const timeSlots = [];
	let index = 0;

	schedule.forEach(({ day, short, slots }) => {
		slots.forEach(({ start, end, mins }) => {
			const startH = start.replace(":", "");
			const endH = end.replace(":", "");
			timeSlots.push({
				id: `${short}-${startH}-${endH}`,
				day,
				label: `${short} • ${start} - ${end} (${mins / 60}h)`,
				durationMins: mins,
				index: index++,
			});
		});
	});

	return timeSlots;
}
