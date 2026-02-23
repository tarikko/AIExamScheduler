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

		// Parse Exams
		const courses = examsText
			.split("\n")
			.filter((line) => line.trim())
			.map((line) => {
				const code = line.substring(0, 8).trim();
				const name = line.substring(8, 48).trim();
				return { code, name, enrollment: 0 };
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
					if (!studentCourseMap.has(sId)) studentCourseMap.set(sId, []);
					studentCourseMap.get(sId).push(eId);

					// Increment course enrollment count
					const course = courses.find((c) => c.code === eId);
					if (course) course.enrollment++;
				}
			});

		// Parse Rooms from data file
		const rooms = [];
		const roomLines = dataText.split("ROOMS")[1]?.split("ROOM ASSIGNMENTS")[0];
		if (roomLines) {
			const roomMatches = roomLines.matchAll(/([A-Z0-9-]{3,})\s+(\d+)/g);
			for (const match of roomMatches) {
				rooms.push({ name: match[1], capacity: parseInt(match[2]) });
			}
		}

		// Fallback if no rooms found
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
		};
	} catch (error) {
		console.error("Benchmark load error:", error);
		return null;
	}
}
