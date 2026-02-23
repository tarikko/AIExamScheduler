export async function loadBenchmark() {
	try {
		const [examsRes, enRes, dataRes] = await Promise.all([
			fetch("benchmark/1/exams"),
			fetch("benchmark/1/enrolements"),
			fetch("benchmark/1/data"),
		]);

		if (!examsRes.ok || !enRes.ok || !dataRes.ok) {
			throw new Error("Missing benchmark files");
		}

		const examsText = await examsRes.text();
		const enText = await enRes.text();
		const dataText = await dataRes.text();

		// Parse Exams + Durations
		const courses = examsText
			.split("\n")
			.filter((line) => line.trim())
			.map((line) => {
				const code = line.substring(0, 8).trim();
				const name = line.substring(8, 48).trim();
				const durText = line.substring(48, 52).trim();
				let durationMins = 120; // default
				if (durText.includes(":")) {
					const [h, m] = durText.split(":");
					durationMins = parseInt(h) * 60 + parseInt(m);
				} else if (durText) {
					// Handle cases like "2 00" (some formats use spaces)
					const parts = durText.split(/\s+/);
					if (parts.length === 2)
						durationMins =
							parseInt(parts[0]) * 60 + parseInt(parts[1]);
				}
				return { code, name, durationMins, enrollment: 0 };
			});

		// Parse Enrolements
		const studentCourseMap = new Map();
		enText
			.split("\n")
			.filter((line) => line.trim())
			.forEach((line) => {
				const parts = line.trim().split(/\s+/);
				if (parts.length >= 2) {
					const sId = parts[0];
					const eId = parts[1];
					if (!studentCourseMap.has(sId))
						studentCourseMap.set(sId, []);
					studentCourseMap.get(sId).push(eId);

					const course = courses.find((c) => c.code === eId);
					if (course) course.enrollment++;
				}
			});

		// Create dynamic time slots based on data/README
		const slots = [];
		const days = [
			"Monday",
			"Tuesday",
			"Wednesday",
			"Thursday",
			"Friday",
			"Saturday",
		];
		const weeks = [1, 2];
		let slotIndex = 0;

		weeks.forEach((week) => {
			days.forEach((day) => {
				if (day === "Saturday") {
					slots.push({
						id: `W${week}-${day}-9`,
						day: day,
						label: `Week ${week} ${day} • 09:00 (3h)`,
						durationMins: 180,
						index: slotIndex++,
					});
				} else {
					// Mon-Fri: 9:00 (3h), 13:30 (2h), 16:30 (2h)
					slots.push({
						id: `W${week}-${day}-9`,
						day: day,
						label: `Week ${week} ${day} • 09:00 (3h)`,
						durationMins: 180,
						index: slotIndex++,
					});
					slots.push({
						id: `W${week}-${day}-13`,
						day: day,
						label: `Week ${week} ${day} • 13:30 (2h)`,
						durationMins: 120,
						index: slotIndex++,
					});
					slots.push({
						id: `W${week}-${day}-16`,
						day: day,
						label: `Week ${week} ${day} • 16:30 (2h)`,
						durationMins: 120,
						index: slotIndex++,
					});
				}
			});
		});

		// Parse Rooms from data file
		const rooms = [];
		const roomLines = dataText
			.split("ROOMS")[1]
			?.split("ROOM ASSIGNMENTS")[0];
		if (roomLines) {
			const roomMatches = roomLines.matchAll(/([A-Z0-9-]{3,})\s+(\d+)/g);
			for (const match of roomMatches) {
				rooms.push({ name: match[1], capacity: parseInt(match[2]) });
			}
		}

		if (rooms.length === 0) {
			rooms.push({ name: "Hall-1", capacity: 500 });
			rooms.push({ name: "Hall-2", capacity: 400 });
		}

		const students = Array.from(studentCourseMap.entries()).map(
			([id, courseList]) => ({
				id,
				courses: courseList,
			})
		);

		return {
			courses: courses.filter((c) => c.enrollment > 0),
			students: students,
			rooms: rooms,
			timeSlots: slots,
		};
	} catch (error) {
		console.error("Benchmark load error:", error);
		return null;
	}
}
