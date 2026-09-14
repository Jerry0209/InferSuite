# Figures — how to read them

PDF for the paper, PNG (300 dpi) for slides; identical content. Colours: SPEC blue,
Server green, Agentic red; in the per-benchmark companions DCPerf is green, Renaissance
gold, DaCapo purple, and each agentic language keeps its own colour.

**Inside every violin:** white box = 25th–75th percentile of the points the violin is
drawn over, black bar = their median, white diamond = their mean. The `med` label under
each violin in the compact grid is that median.

**Broken axes** (`∕∕` marks): a panel whose largest value is more than 3× its 95th
percentile is cut; the upper strip shows the outliers as grey dots, the lower part keeps a
readable scale. Nothing is dropped. **Red triangles** at the top of a per-window column:
that column's maximum lies above the cap; the statistics inside the violin still use the
full data.

| Fig | What one point is | What the shape means |
|---|---|---|
| fig01 | one workload's vote (median over its windows) | how the metric varies ACROSS workloads within a family |
| fig02–05, SPEC-int / SPEC-fp / Server columns | one benchmark's vote | across-benchmark spread of the reference group |
| fig02–05, agentic columns | one 100 ms window of that task | how the metric varies OVER TIME within one task |
| fig06 | SPEC/Agentic: a vote; external suites: one diamond per benchmark at its vote, bar = its window IQR | per-benchmark placement |
| fig07–10 external columns | one 100 ms window of that benchmark | within-benchmark time variation |

The Server violin in fig01 is drawn over 8 votes; that is few for a kernel density, so
read its width as a rough envelope and take the exact eight values from
`../Raw data/multi_server_compact_numbers.csv` (rows `Server:Renaissance`, `Server:DaCapo`).
