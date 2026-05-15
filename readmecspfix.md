

### 1. Updating the CSP Backend
I noticed the server's `csp.py` was super outdated and was still using the old `common.fitness` function instead of the new weighted penalty system.
- **Moved the new logic over:** I copied the updated CSP class from the notebook (the one with the `exam_overlap` graph, node consistency pruning, and the `solution_evaluation` method).
- **Added `first_find`:** Ported the `first_find` feature so we can tell the algorithm to stop as soon as it finds the first valid schedule, rather than exhaustively searching.
- **Fixed `main.py`:** Adjusted the API route so it properly passes the `Exam` objects to the CSP instead of just student IDs, just like we do for the Genetic Algorithm.
- **Kept the server stuff intact:** I made sure to keep the timeout limit, the greedy fallback, and the progress reporting so the demo website doesn't just hang while it calculates.

### 2. Frontend UI Tweaks
Since the CSP has different settings than the GA, the website UI needed some adjustments so the options wouldn't clash.
- **Cleaned up the settings panel:** Merged everything into one dynamic settings box. Now, if you click "Genetic Algorithm," you see the Generations/Population inputs. If you click "CSP", those hide and you get a checkbox for "Stop at first solution".
- **Custom toggle switch:** I swapped out the boring default checkbox for the `first_find` option with a custom animated switch slider (grabbed from Uiverse.io) that matches our theme. It looks way better!
- **Grid fix:** I noticed the timeslots column in the Master Schedule Grid was getting squished whenever we had a lot of rooms and had to scroll horizontally. I fixed it by giving that column a fixed `min-width` of 200px and adding `white-space: nowrap` so the text stays perfectly readable.
