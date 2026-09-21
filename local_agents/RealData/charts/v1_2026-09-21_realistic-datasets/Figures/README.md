# Figures — how to read them

PDF for the paper, PNG (300 dpi) for slides. fig01: in every panel the open circle is the suite
benchmark's value and the green circle is the same software on the realistic dataset. The line
between them is a CONNECTOR with an arrowhead at the realistic end — it shows which way the
workload moved and by how much. It is not an error bar, a range or a distribution: each end is
a single number, that workload's metric over its whole runtime. Dashed vertical lines: the MEDIAN of the 26 SPEC
per-benchmark values (blue) and of the 36 agentic per-task values (red) — the same whole-runtime
statistic as every circle, taken across the workloads of those two families, and the same number
the SPEC and Agentic violins are centred on in fig02/fig03. They are drawn as reference so a
reader can see where a server sits relative to the two families in the main comparison, and
whether changing the dataset moved it across one of them (it does: Cassandra crosses the agentic
DRAM line, Naive Bayes crosses both on the cache metrics). fig02/fig03: violins over per-workload values (white box = IQR,
black bar = median, white diamond = mean); fig02 uses the realistic versions in the Server set,
fig03 the suite versions, so the two Server violins differ by exactly the five (six with video)
re-characterised workloads.
