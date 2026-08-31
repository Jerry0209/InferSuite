#!/usr/bin/env Rscript
# plot_paper_agg_compact.R -- the completely compacted view in the PAPER style, MERGED
# agent fence (mentor 2026-08-31): per metric exactly TWO violins -- SPEC (26 benchmarks,
# one vote per benchmark = its per-window median) vs Agentic (the 36 count-view tasks, one
# vote per task = its per-window median with tool+harness raw counts summed). Each violin
# carries its median value as a label beside the median bar.
#
# Inputs : local_agents/ML_iso36/data/l3_study/agg_rows_long.csv (fence == "both")
# Outputs: local_agents/ML_iso36/plots/paper_v1/iso36_agg_compact_merged.{png,pdf}
#          local_agents/ML_iso36/plots/paper_v1/iso36_agg_compact_merged_numbers.csv
suppressPackageStartupMessages({
  library(ggplot2); library(dplyr); library(ragg); library(scales); library(patchwork)
})
repo <- path.expand("~/InferSuite")
source(file.path(repo, "local_agents/kit/plot/theme_paper.R"))
OUT <- file.path(repo, "local_agents/ML_iso36/plots/paper_v1")

d <- read.csv(file.path(repo, "local_agents/ML_iso36/data/l3_study/agg_rows_long.csv"),
              stringsAsFactors = FALSE) |> filter(fence == "both")
langs <- c("C", "C++", "Rust", "Go", "Java", "PHP", "Ruby", "JavaScript", "TypeScript")
METRICS <- c("IPC",
             "Branch MPKI", "Branch-direction MPKI", "BTB MPKI (BAClears)",
             "L1I MPKI (code-read)", "uop-cache (DSB) MPKI", "DSB coverage (%)",
             "L1D-load MPKI", "L2-load MPKI", "LLC MPKI", "DRAM read (GB/s)",
             "Context switches (/CPU-s)")
logm <- "Context switches (/CPU-s)"
C_SPEC <- "#4d4d4d"; C_AG <- "#159f77"

per_workload <- bind_rows(
  d |> filter(grp %in% c("SPEC-int", "SPEC-fp")) |>
    group_by(metric, wl = paste(grp, ave(value, metric, grp, FUN = seq_along))) |>
    summarise(v = first(value), .groups = "drop") |> mutate(side = "SPEC"),
  d |> filter(grp %in% langs) |>
    group_by(metric, wl = col) |>
    summarise(v = median(value), .groups = "drop") |> mutate(side = "Agentic"))
per_workload$side <- factor(per_workload$side, levels = c("SPEC", "Agentic"))

num <- per_workload |> group_by(metric, side) |>
  summarise(n = n(), median = median(v), mean = mean(v),
            p5 = quantile(v, .05), p95 = quantile(v, .95), max = max(v), .groups = "drop")
write.csv(num, file.path(OUT, "iso36_agg_compact_merged_numbers.csv"), row.names = FALSE)

panel <- function(m) {
  dm <- per_workload |> filter(metric == m)
  nm <- num |> filter(metric == m)
  use_log <- m %in% logm
  # keep the median label inside the panel even when the median hugs an axis end
  if (use_log) {
    lo0 <- 10^floor(log10(max(min(dm$v[dm$v > 0]), 1e-2)))
    hi0 <- 10^ceiling(log10(max(dm$v)))
    nm$lab_y <- pmax(pmin(nm$median, hi0 / 1.4), lo0 * 1.4)
  } else {
    hi0 <- if (grepl("\\(%\\)", m)) 100 else max(pretty(c(0, max(dm$v) * 1.06), 5))
    nm$lab_y <- pmax(pmin(nm$median, hi0 * 0.965), hi0 * 0.035)
  }
  p <- ggplot(dm, aes(x = side, y = v, fill = side)) +
    geom_violin(scale = "width", width = 0.72, linewidth = PAPER_EDGE_LW,
                colour = PAPER_EDGE, adjust = 1.1, trim = TRUE, alpha = 0.8) +
    geom_boxplot(width = 0.18, outlier.shape = NA, linewidth = 0.3,
                 colour = "grey15", fill = "white", alpha = 0.9, coef = 0) +
    stat_summary(fun = median, geom = "crossbar", width = 0.18, linewidth = 0.35,
                 colour = "black") +
    stat_summary(fun = mean, geom = "point", shape = 23, size = 1.6,
                 fill = "white", colour = "black", stroke = 0.4) +
    geom_text(data = nm, aes(x = side, y = lab_y, label = sprintf("%.3g", median)),
              nudge_x = 0.47, size = 2.15, colour = "black", family = PAPER_SERIF,
              inherit.aes = FALSE) +
    scale_fill_manual(values = c(SPEC = C_SPEC, Agentic = C_AG), guide = "none") +
    paper_x_discrete() +
    labs(title = m, x = NULL, y = NULL) +
    theme_paper(base_size = 8) +
    theme(plot.title = element_text(size = 7.4, hjust = 0.5, face = "plain",
                                    margin = margin(b = 2)),
          axis.text.x = element_text(size = 6.6),
          axis.text.y = element_text(size = 5.8),
          panel.grid.major.x = element_blank())
  if (use_log) {
    lo <- 10^floor(log10(max(min(dm$v[dm$v > 0]), 1e-2)))
    hi <- 10^ceiling(log10(max(dm$v)))
    p <- p + scale_y_log10(limits = c(lo, hi), breaks = 10^seq(log10(lo), log10(hi)),
                           labels = label_number(drop0trailing = TRUE),
                           expand = expansion(0, 0))
  } else if (grepl("\\(%\\)", m)) {
    p <- p + paper_scale_y(0, 100, 25)
  } else {
    br <- pretty(c(0, max(dm$v) * 1.06), 5); hi <- max(br)
    p <- p + paper_scale_y(0, hi, br[2] - br[1])
  }
  p
}

fig <- wrap_plots(lapply(METRICS, panel), ncol = 4) + plot_annotation(
  title = "SPEC vs Agentic, one vote per workload — combined agent fence (tool + harness)",
  subtitle = paste("SPEC = 26 benchmarks, Agentic = the revised all-resolved 36; each workload",
                   "contributes its per-window MEDIAN once (agent windows: the two fences' raw",
                   "counts summed) · label = group median · black bar = median, white diamond = mean"),
  caption = "100 ms windows, matched configuration · metric order follows the group pictures (IPC · frontend · memory · system)",
  theme = theme(plot.title = element_text(size = 11.5, face = "bold", family = PAPER_SERIF),
                plot.subtitle = element_text(size = 6.6, colour = "grey35", family = PAPER_SERIF),
                plot.caption = element_text(size = 5.8, colour = "grey45", family = PAPER_SERIF)))
paper_save(fig, file.path(OUT, "iso36_agg_compact_merged"), width = 10.5, height = 8.2)
