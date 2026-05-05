export async function fetchBenchmarkCatalog() {
	const response = await fetch("/api/benchmarks");
	if (!response.ok) {
		throw new Error(`Unable to list benchmarks (${response.status})`);
	}

	const data = await response.json();
	return data.benchmarks || [];
}

export async function loadBenchmark(benchmarkId) {
	const response = await fetch(`/api/benchmarks/${encodeURIComponent(benchmarkId)}`);
	if (!response.ok) {
		const error = await response.json().catch(() => ({}));
		throw new Error(error.detail || `Unable to load benchmark ${benchmarkId}`);
	}

	return response.json();
}
