#!/usr/bin/env Rscript
# fig07_agg_compact_merged — COPY of the canonical generator local_agents/kit/plot/plot_paper_agg_compact.R
# (single source of truth; edit THERE). Runs from the repo root against the
# banked data tree and writes into plots/paper_v2/.
# Regenerate: see charts/README.md.
# plot_paper_agg_compact.R -- the 12-panel SPEC-vs-Agentic grid, revision v4
# (PI 2026-09-06, paper-ready: figure title removed -- the filename/caption carries it --
#  legend strip unboxed and centred at the top; earlier v3 feedback 2026-09-02):
#   - short CENTRED title, all grey subtitle/caption text removed
#   - a FORMAL legend panel beside the grid (fills + glyphs + break mark + dagger note)
#   - inner glyph back to the paper_v1 style -- thin WHITE IQR box + black median bar +
#     white diamond mean -- narrowed so it never exceeds the violin outline
#   - no raw-point overlay (removed on PI request)
#   - broken-axis gap tightened (the two pieces nearly touch; the double-slash marks
#     remain the break signal)
# Kept from v2: paired dark-blue/dark-red palette, thin black violin outlines, breaks only
# where pooled max > 3x pooled p95, log ctx panel with the 0-dagger convention, medians in
# the x tick labels, exact axis-break/border discipline, dotted grids, outward ticks.
#
# ADJ=0.8|1.0|1.2 sets the KDE bandwidth multiplier (default 1.0; variants for review).
# Inputs : local_agents/ML_iso36/data/l3_study/agg_rows_long.csv (fence == "both")
# Outputs: plots/paper_v2/iso36_agg_compact_merged[_adjNN].{png,pdf} + _numbers.csv
suppressPackageStartupMessages({
  library(ggplot2); library(dplyr); library(ragg); library(scales); library(patchwork)
})
repo <- path.expand("~/InferSuite")
source(file.path(repo, "local_agents/kit/plot/theme_paper.R"))
ADJ <- as.numeric(Sys.getenv("ADJ", "1.0"))
OUT <- file.path(repo, "local_agents/ML_iso36/plots/paper_v2")
dir.create(OUT, showWarnings = FALSE, recursive = TRUE)
suffix <- if (ADJ == 1.0) "" else sprintf("_adj%02.0f", ADJ * 10)

d <- read.csv(file.path(repo, "local_agents/ML_iso36/data/l3_study/agg_rows_long.csv"),
              stringsAsFactors = FALSE) |> filter(fence == "both")
langs <- c("C", "C++", "Rust", "Go", "Java", "PHP", "Ruby", "JavaScript", "TypeScript")
METRICS <- c("IPC",
             "Branch MPKI", "Branch-direction MPKI", "BTB MPKI (BAClears)",
             "L1I MPKI (code-read)", "uop-cache (DSB) MPKI", "DSB coverage (%)",
             "L1D-load MPKI", "L2-load MPKI", "LLC MPKI", "DRAM read (GB/s)",
             "Context switches (/CPU-s)")
logm <- "Context switches (/CPU-s)"

per_workload <- bind_rows(
  d |> filter(grp %in% c("SPEC-int", "SPEC-fp")) |>
    group_by(metric, wl = paste(grp, ave(value, metric, grp, FUN = seq_along))) |>
    summarise(v = first(value), .groups = "drop") |> mutate(side = "SPEC"),
  d |> filter(grp %in% langs) |>
    group_by(metric, wl = col) |>
    summarise(v = median(value), .groups = "drop") |> mutate(side = "Agentic"))
per_workload$side <- factor(per_workload$side, levels = c("SPEC", "Agentic"))

num <- per_workload |> group_by(metric, side) |>
  summarise(n = n(), min = min(v), max = max(v), median = median(v), mean = mean(v),
            sd = sd(v), p5 = quantile(v, .05), p95 = quantile(v, .95),
            bw_nrd0 = stats::bw.nrd0(v), .groups = "drop")
write.csv(num, file.path(OUT, "iso36_agg_compact_merged_numbers.csv"), row.names = FALSE)

# the paper_v1 inner glyph, narrowed so it stays inside the violin outline
inner_v1 <- function() list(
  geom_boxplot(width = 0.08, outlier.shape = NA, linewidth = 0.28,
               colour = "grey15", fill = "white", alpha = 0.95, coef = 0),
  stat_summary(fun = median, geom = "crossbar", width = 0.08, linewidth = 0.3,
               colour = "black"),
  stat_summary(fun = mean, geom = "point", shape = 23, size = 1.5,
               fill = "white", colour = "black", stroke = 0.4))

panel <- function(m) {
  dm <- per_workload |> filter(metric == m)
  nm <- num |> filter(metric == m) |> arrange(side)
  use_log <- m %in% logm
  is_pct <- grepl("\\(%\\)", m)
  pooled <- dm$v
  qual <- !use_log && !is_pct && paper_break_qualifies(pooled)
  cat(sprintf("panel %-28s max=%.4g 3x_p95=%.4g -> break=%s\n",
              m, max(pooled), 3 * quantile(pooled, .95), ifelse(qual, "YES",
              ifelse(use_log, "no (log panel)", "no"))))
  med_lab <- ifelse(nm$median == 0 & use_log, "0†", sprintf("%.3g", nm$median))
  xlabs <- setNames(sprintf("%s\nmed %s", nm$side, med_lab), nm$side)
  th <- theme_paper(base_size = 8) +
    theme(plot.title = element_text(size = 7.4, hjust = 0.5, face = "plain",
                                    margin = margin(b = 2)),
          axis.text.x = element_text(size = 6.2, lineheight = 0.9),
          axis.text.y = element_text(size = 5.8),
          panel.grid.major.x = element_blank())
  base <- function(dd) ggplot(dd, aes(x = side, y = v, fill = side)) +
    geom_violin(scale = "width", width = 0.72, linewidth = PAPER_VIOLIN_LW,
                colour = "black", adjust = ADJ, trim = TRUE, alpha = 0.75) +
    inner_v1() +
    scale_fill_manual(values = PAPER_TWO, guide = "none") +
    labs(x = NULL, y = NULL) + th
  if (use_log) {
    lo <- 10^floor(log10(max(min(pooled[pooled > 0]), 1e-2)))
    hi <- 10^ceiling(log10(max(pooled)))
    dm$v <- pmax(dm$v, lo)                       # 0 has no position on a log axis
    return(base(dm) + ggtitle(m) +
      scale_x_discrete(labels = xlabs, expand = expansion(add = 0.6)) +
      scale_y_log10(limits = c(lo, hi), breaks = 10^seq(log10(lo), log10(hi)),
                    labels = label_number(drop0trailing = TRUE), expand = expansion(0, 0)))
  }
  if (is_pct) {
    return(base(dm) + ggtitle(m) +
      scale_x_discrete(labels = xlabs, expand = expansion(add = 0.6)) +
      paper_scale_y(0, 100, 25))
  }
  if (!qual) {
    br <- pretty(c(0, max(pooled) * 1.03), 5)
    return(base(dm) + ggtitle(m) +
      scale_x_discrete(labels = xlabs, expand = expansion(add = 0.6)) +
      paper_scale_y(0, max(br), br[2] - br[1]))
  }
  # manual broken axis: body piece + outlier piece; TIGHT gap (pieces nearly touch)
  thr <- 3 * quantile(pooled, .95)
  body_max <- max(pooled[pooled <= thr]); out_min <- min(pooled[pooled > thr])
  brk <- pretty(c(0, body_max * 1.12), 5)
  brk_lo <- max(brk)
  ub <- pretty(c(out_min, max(pooled) * 1.02), 2)
  step <- if (length(ub) > 1) ub[2] - ub[1] else out_min * 0.1
  up_lo <- floor(out_min / step) * step
  if (up_lo <= brk_lo) up_lo <- signif(out_min * 0.95, 2)  # upper zone must sit ABOVE the gap
  up_hi <- max(ub)
  stopifnot(up_lo <= out_min, up_lo > brk_lo, brk_lo >= body_max)
  lower <- base(dm) +
    scale_x_discrete(labels = xlabs, expand = expansion(add = 0.6)) +
    scale_y_continuous(limits = c(0, brk_lo), breaks = brk, expand = expansion(0, 0),
                       oob = scales::oob_squish) +
    annotate("text", x = 0.47, y = brk_lo * 0.985, label = "∕∕", size = 2.3,
             hjust = 0.5, family = PAPER_SERIF, fontface = "bold") +
    theme(plot.margin = margin(0.6, 8, 6, 6))
  upper <- ggplot(dm |> filter(v > thr), aes(x = side, y = v, fill = side)) +
    geom_point(shape = 21, size = 1.2, fill = "grey35", colour = "black", stroke = 0.3) +
    scale_fill_manual(values = PAPER_TWO, guide = "none") +
    scale_x_discrete(limits = levels(dm$side), expand = expansion(add = 0.6)) +
    scale_y_continuous(limits = c(up_lo, up_hi), breaks = c(up_lo, up_hi),
                       expand = expansion(0, 0)) +
    labs(x = NULL, y = NULL) + ggtitle(m) + th +
    theme(axis.text.x = element_blank(), axis.ticks.x = element_blank(),
          plot.margin = margin(6, 8, 0.6, 6)) +
    annotate("text", x = 0.47, y = up_lo + (up_hi - up_lo) * 0.03, label = "∕∕",
             size = 2.3, hjust = 0.5, family = PAPER_SERIF, fontface = "bold")
  (upper / lower) + plot_layout(heights = c(0.2, 0.8))
}

# ---- the legend strip (top of the figure; paper-ready PI 2026-09-06: no title, no box,
# entries centred as a group) ----
legend_strip <- function() {
  tx <- function(xx, lab, size = 2.5) annotate("text", x = xx, y = 0.5, label = lab,
                                               hjust = 0, size = size,
                                               family = PAPER_SERIF)
  ggplot() + xlim(0, 1) + ylim(0, 1) + theme_void() +
    theme(plot.margin = margin(2, 10, 4, 10)) +
    annotate("rect", xmin = 0.155, xmax = 0.177, ymin = 0.28, ymax = 0.72,
             fill = PAPER_TWO[["SPEC"]], colour = "black", linewidth = 0.3) +
    tx(0.187, "SPEC (26 benchmarks)") +
    annotate("rect", xmin = 0.322, xmax = 0.344, ymin = 0.28, ymax = 0.72,
             fill = PAPER_TWO[["Agentic"]], colour = "black", linewidth = 0.3) +
    tx(0.354, "Agentic (36 tasks)") +
    annotate("segment", x = 0.474, xend = 0.504, y = 0.5, yend = 0.5,
             colour = "black", linewidth = 1.0) +
    tx(0.514, "median") +
    annotate("point", x = 0.586, y = 0.5, shape = 23, size = 2.1, fill = "white",
             colour = "black", stroke = 0.45) +
    tx(0.601, "mean") +
    tx(0.656, "† median 0 — no position on a log axis", 2.2)
}

ps <- lapply(METRICS, panel)
grid <- wrap_plots(ps, ncol = 4)
fig <- (legend_strip() / grid) + plot_layout(heights = c(0.04, 1))
paper_save(fig, file.path(OUT, paste0("iso36_agg_compact_merged", suffix)),
           width = 10.6, height = 8.3)
