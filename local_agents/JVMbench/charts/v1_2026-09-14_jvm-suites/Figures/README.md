# Figures — how to read them (v1, superseded)

This version predates the reinstatement of DaCapo `cassandra` (excluded here on a
steady-state gate that was later found defective — `../../../README.md` §8) and predates the
three-violin layout the mentor asked for; both are in `../../v2_2026-09-14_cassandra-reinstated/`.
Kept so that anything already circulated from v1 can be traced.

PDF for the paper, PNG (300 dpi) for slides; identical content. Colours: SPEC blue, Agentic
red, DCPerf green diamonds, Renaissance gold diamonds, DaCapo purple diamonds; each agentic
language has its own colour in fig02–05.

**Inside every violin:** white box = 25th–75th percentile of the points the violin is drawn
over, black bar = their median, white diamond = their mean. **Broken axes** (`∕∕`): a panel
whose largest value exceeds 3× its 95th percentile is cut; outliers sit in the upper strip as
grey dots, nothing is dropped. **Red triangles** in fig02–05: that column's maximum lies above
the axis cap; the violin's statistics still use the full data.

| Fig | What one point is | What the shape means |
|---|---|---|
| fig01, SPEC and Agentic violins | one workload's vote (median over its 100 ms windows) | across-workload variation within the family |
| fig01, coloured diamonds | one external benchmark at its vote; thin bar = p25–p75 of ITS OWN windows | where each benchmark sits; the bar is a within-workload spread, not comparable to a violin's width |
| fig02–05, SPEC-int / SPEC-fp columns | one benchmark's vote (14 int, 12 fp) | across-benchmark spread of the reference group |
| fig02–05, every other column | one 100 ms window of that workload | how the metric varies OVER TIME within one workload |
