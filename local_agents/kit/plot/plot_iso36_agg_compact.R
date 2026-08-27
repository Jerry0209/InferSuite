#!/usr/bin/env Rscript
# plot_iso36_agg_compact.R -- the COMPLETELY COMPACTED view (mentor 2026-08-28): per
# metric exactly TWO distributions, SPEC vs Agentic.
#
#   SPEC    = the metric across all 26 SPEC workloads -- one value per benchmark (its
#             per-window median), so every workload votes once.
#   Agentic = the same across the 36 count-view tasks -- one value per task (its
#             per-window median). Python pilots excluded to keep the population crisp.
#
# 12 metrics (the four group pictures' metrics, in the same order), each a small
# bounding-boxed panel with violin + box + median bar + mean diamond. One picture per
# fence, PNG + PDF.
#
# Inputs : local_agents/ML_iso36/data/l3_study/agg_rows_long.csv
# Outputs: local_agents/ML_iso36/plots/iso36_agg_compact_{tool,harness}.{png,pdf}
#          local_agents/ML_iso36/plots/iso36_agg_compact_numbers.csv
suppressPackageStartupMessages({
  library(ggplot2); library(hrbrthemes); library(dplyr); library(tidyr)
  library(yaml); library(ragg); library(scales); library(patchwork)
})
repo <- path.expand("~/InferSuite")
source(file.path(repo, "local_agents/kit/plot/iso36_style.R"))

d <- read.csv(file.path(repo, "local_agents/ML_iso36/data/l3_study/agg_rows_long.csv"),
              stringsAsFactors = FALSE)
langs <- c("C", "C++", "Rust", "Go", "Java", "PHP", "Ruby", "JavaScript", "TypeScript")
METRICS <- c("IPC",
             "Branch MPKI", "Branch-direction MPKI", "BTB MPKI (BAClears)",
             "L1I MPKI (code-read)", "uop-cache (DSB) MPKI", "DSB coverage (%)",
             "L1D-load MPKI", "L2-load MPKI", "LLC MPKI", "DRAM read (GB/s)",
             "Context switches (/CPU-s)")
logm <- "Context switches (/CPU-s)"
C_SPEC <- "#4d4d4d"; C_AG <- "#159f77"

# one vote per workload on both sides
per_workload <- bind_rows(
  d |> filter(grp %in% c("SPEC-int", "SPEC-fp")) |>
    group_by(fence, metric, wl = paste(grp, ave(value, fence, metric, grp, FUN = seq_along))) |>
    summarise(v = first(value), .groups = "drop") |> mutate(side = "SPEC"),
  d |> filter(grp %in% langs) |>
    group_by(fence, metric, wl = col) |>
    summarise(v = median(value), .groups = "drop") |> mutate(side = "Agentic"))
per_workload$side <- factor(per_workload$side, levels = c("SPEC", "Agentic"))

num <- per_workload |> group_by(fence, metric, side) |>
  summarise(n = n(), median = median(v), mean = mean(v),
            p5 = quantile(v, .05), p95 = quantile(v, .95), max = max(v), .groups = "drop")
write.csv(num, file.path(repo, "local_agents/ML_iso36/plots/iso36_agg_compact_numbers.csv"),
          row.names = FALSE)

panel <- function(dd, m) {
  dm <- dd |> filter(metric == m)
  use_log <- m %in% logm
  p <- ggplot(dm, aes(x = side, y = v, fill = side)) +
    geom_violin(scale = "width", width = 0.75, linewidth = 0.2, colour = "grey40",
                adjust = 1.1, trim = TRUE, alpha = 0.75) +
    geom_boxplot(width = 0.2, outlier.shape = NA, linewidth = 0.3,
                 colour = "grey15", fill = "white", alpha = 0.9, coef = 0) +
    stat_summary(fun = median, geom = "crossbar", width = 0.2, linewidth = 0.35,
                 colour = "black") +
    stat_summary(fun = mean, geom = "point", shape = 23, size = 1.6,
                 fill = "white", colour = "black", stroke = 0.4) +
    scale_fill_manual(values = c(SPEC = C_SPEC, Agentic = C_AG), guide = "none") +
    labs(title = m, x = NULL, y = NULL) +
    theme_house(base_size = 8, axis_title_size = 8) +
    theme(plot.title = element_text(size = 7.4, hjust = 0.5, face = "plain",
                                    margin = margin(b = 2)),
          axis.text.x = element_text(size = 6.6),
          axis.text.y = element_text(size = 5.8),
          panel.grid.major.x = element_blank(),
          panel.border = element_rect(colour = "black", fill = NA, linewidth = 0.55),
          plot.margin = margin(8, 10, 8, 6))
  if (use_log) {
    p <- p + scale_y_log10(labels = label_number(drop0trailing = TRUE))
  } else if (grepl("\\(%\\)", m)) {
    p <- p + coord_cartesian(ylim = c(0, 100))
  }
  p
}

for (fence in c("tool", "harness")) {
  dd <- per_workload |> filter(fence == !!fence)
  ps <- lapply(METRICS, function(m) panel(dd, m))
  fig <- wrap_plots(ps, ncol = 4) + plot_annotation(
    title = sprintf("SPEC vs Agentic, one vote per workload — %s fence", fence),
    subtitle = paste("SPEC = 26 benchmarks, Agentic = the 36 count-view tasks; each workload contributes its",
                     "per-window MEDIAN once · violin + box, black bar = median of workloads, white diamond = mean"),
    caption = "100 ms windows, matched configuration · metric order follows the group pictures (IPC · frontend · memory · system)",
    theme = theme(plot.title = element_text(size = 11.5, face = "bold"),
                  plot.subtitle = element_text(size = 6.6, colour = "grey35"),
                  plot.caption = element_text(size = 5.8, colour = "grey45")))
  house_save(fig, file.path(repo, sprintf("local_agents/ML_iso36/plots/iso36_agg_compact_%s", fence)),
             width = 10.5, height = 8.2)
}
