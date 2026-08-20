**Progress update: I built a second version of the type matrix, based on command counts instead of CPU time**

Following the suggestion to try count-weighted classification, I built it for all 300 tasks and compared it with the current one. Two figures attached: the first is the current matrix (weighted by CPU time), the second is the new one (weighted by how many commands ran).

**1. The two matrices really do disagree**

```
                 B     T     S     M    no evidence
CPU time        55   162     0     8        75
command count   61   109    60    42        28
```

They agree on only 112 of the 225 tasks that both can label, so the difference is not something we can ignore. The search column, which is empty under CPU time, suddenly has 60 tasks in it.

But when I looked at why, the reason turned out to be the toolchain, not the task:

- **Java** moves from 32 "test" to 24 "search". A JVM test run is a single `java` process that burns several minutes of CPU, while the agent typed a few dozen cheap `grep`s next to it. By headcount the greps win, but nobody would call that task a search task.
- **Rust** moves the opposite way, 16 to 31 "build", because `cargo test` starts thousands of small `rustc` processes.
- On average, one counted search command costs 2.2 ms, a test command 13 ms, and a build command 36 ms. Counting treats one `wc` as equal to one `cc1`.

So counting is not biased towards search. It is biased towards whichever toolchain creates the most processes, which is a property of the build system rather than of the work being done. I have kept the count numbers as extra columns in the results file for comparison, but the label stays based on CPU time.

**2. A bug I found while doing this**

Our process log comes from a kernel interface called taskstats, which writes into a fixed-size buffer. When a build forks thousands of short-lived processes in a few seconds, the buffer fills up, the kernel drops records, and our listener was then killed by the resulting error. It happened in **23 of the 300 tasks**, mostly in Go, JavaScript and TypeScript, which fork the most. Those tasks recorded nothing after the crash point.

**3. The fix, and where it stands now**

Three changes: a 64 MB buffer instead of the default; the overflow error is now recorded as a `LOST` line and no longer kills the listener; and receiving is separated from parsing, so the buffer is drained as fast as possible.

I tested it with a deliberate storm of 72,000 short-lived processes: 72,127 records captured, zero drops. I then shrank the buffer to 8 KB on purpose to force the failure, and the listener stayed alive and wrote 2,128 loss markers instead of dying.

The 23 tasks are being re-measured right now with the fixed listener (no API cost, since we replay saved runs). About 9 of 23 are done.

**4. Does this change the classification or the 30 chosen tasks?**

Mostly no, with one exception worth knowing:

- For the **count-based matrix**, no. If I drop all 23 affected tasks, the search column moves from 60 to 59. The missing data shifts build/test/mixed a little, but it is not what creates the search column.
- For the **main matrix and the 30 chosen tasks**, mostly no — but **4 of the 30 picks are affected tasks**, so I would rather not send those to the profiling machine until the re-run finishes later today.
- The conclusion itself is unchanged: tasks where search really does lead in CPU are all tiny (a few CPU-seconds) and would be rejected by the 20 CPU-second floor anyway. The empty search column is a fact about size, not a side effect of how we weight things.

I will post the rebuilt matrix once the 23 re-runs finish.
