export const benchmarks = [
	{ name: "EAR-F-83 (24 courses, 1108 students)", key: "ear-f-83-2" },
	{ name: "HEC-S-92 (81 courses, 2750 students)", key: "hec-s-92-2" },
	{ name: "PUR-S-93 (30 courses, 1360 students)", key: "pur-s-93-2" },
	{ name: "STA-F-83 (139 courses, 2750 students)", key: "sta-f-83-2" },
	{ name: "UTA-S-92 (35 courses, 2750 students)", key: "uta-s-92-2" },
	{ name: "YOR-F-83 (48 courses, 2750 students)", key: "yor-f-83-2" },
];

export async function loadBenchmark(key) {
	try {
		const crsRes = await fetch(`benchmark/1/${key}.crs`);
		const stuRes = await fetch(`benchmark/1/${key}.stu`);

		if (!crsRes.ok || !stuRes.ok) throw new Error("Benchmark files not found");

		const crsText = await crsRes.text();
		const stuText = await stuRes.text();

		const courseLines = crsText.trim().split("\n");
		const studentLines = stuText.trim().split("\n");

		const courses = courseLines.map((line, idx) => {
			const [code, enrollment] = line.trim().split(/\s+/);
			return {
				code: code || `C${idx + 1}`,
				name: `Course ${code}`,
				enrollment: parseInt(enrollment) || 1,
			};
		});

		const students = studentLines.map((line, idx) => {
			const courseCodes = line
				.trim()
				.split(/\s+/)
				.filter((c) => c && c.match(/^\d+$/));
			return {
				id: `S${idx + 1}`,
				courses: courseCodes.map((codeNum) => {
					const courseIdx = parseInt(codeNum) - 1;
					return courses[courseIdx]?.code || `C${codeNum}`;
				}),
			};
		});

		const rooms = [
			{ name: "Room A", capacity: 500 },
			{ name: "Room B", capacity: 400 },
			{ name: "Room C", capacity: 300 },
			{ name: "Room D", capacity: 250 },
			{ name: "Room E", capacity: 200 },
		];

		return {
			courses: courses.filter((c) => c.code),
			students: students.filter((s) => s.courses.length > 0),
			rooms: rooms,
		};
	} catch (error) {
		console.error("Failed to load benchmark:", error);
		return null;
	}
}
