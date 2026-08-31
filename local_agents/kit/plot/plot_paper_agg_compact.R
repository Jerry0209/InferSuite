#!/usr/bin/env Rscript
# plot_paper_agg_compact.R -- the 12-panel SPEC-vs-Agentic grid, revision v3
# (PI feedback 2026-09-02 on the v2 violin spec):
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
  geom_boxplot(width = 0.12, outlier.shape = NA, linewidth = 0.28,
               colour = "grey15", fill = "white", alpha = 0.95, coef = 0),
  stat_summary(fun = median, geom = "crossbar", width = 0.12, linewidth = 0.3,
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

# ---- the formal legend panel (beside the grid) ----
legend_panel <- function() {
  y <- c(SPEC = 0.95, AG = 0.88, BOX = 0.76, MED = 0.65, MEAN = 0.54,
         OUT = 0.42, BRK = 0.30, DAG = 0.17)
  tx <- function(yy, lab, size = 2.1) annotate("text", x = 0.28, y = yy, label = lab,
                                               hjust = 0, size = size,
                                               family = PAPER_SERIF)
  ggplot() + xlim(0, 1) + ylim(0, 1) + theme_void() +
    theme(panel.border = element_rect(colour = "black", fill = NA, linewidth = 0.4),
          plot.margin = margin(6, 4, 6, 2)) +
    annotate("rect", xmin = 0.06, xmax = 0.22, ymin = y["SPEC"] - 0.02,
             ymax = y["SPEC"] + 0.02, fill = PAPER_TWO[["SPEC"]], colour = "black",
             linewidth = 0.3) + tx(y["SPEC"], "SPEC\n(26 benchmarks)", 2.0) +
    annotate("rect", xmin = 0.06, xmax = 0.22, ymin = y["AG"] - 0.02,
             ymax = y["AG"] + 0.02, fill = PAPER_TWO[["Agentic"]], colour = "black",
             linewidth = 0.3) + tx(y["AG"], "Agentic\n(36 tasks)", 2.0) +
    annotate("rect", xmin = 0.10, xmax = 0.18, ymin = y["BOX"] - 0.028,
             ymax = y["BOX"] + 0.028, fill = "white", colour = "grey15",
             linewidth = 0.35) + tx(y["BOX"], "white box =\nIQR (25–75%)", 2.0) +
    annotate("segment", x = 0.08, xend = 0.20, y = y["MED"], yend = y["MED"],
             colour = "black", linewidth = 0.9) + tx(y["MED"], "black bar =\nmedian", 2.0) +
    annotate("point", x = 0.14, y = y["MEAN"], shape = 23, size = 2.0, fill = "white",
             colour = "black", stroke = 0.45) + tx(y["MEAN"], "diamond =\nmean", 2.0) +
    annotate("point", x = 0.14, y = y["OUT"], shape = 21, size = 1.4, fill = "grey35",
             colour = "black", stroke = 0.3) +
    tx(y["OUT"], "point = outlier\nabove the break", 2.0) +
    annotate("text", x = 0.14, y = y["BRK"], label = "∕∕", size = 2.6,
             family = PAPER_SERIF, fontface = "bold") + tx(y["BRK"], "axis break", 2.0) +
    tx(y["DAG"], "† median 0 —\nno position on\na log axis", 1.9)
}

ps <- lapply(METRICS, panel)
grid <- wrap_plots(ps, ncol = 4)
fig <- (grid | legend_panel()) + plot_layout(widths = c(1, 0.11)) + plot_annotation(
  title = "SPEC vs Agentic",
  theme = theme(plot.title = element_text(size = 13, face = "bold", hjust = 0.5,
                                          family = PAPER_SERIF)))
paper_save(fig, file.path(OUT, paste0("iso36_agg_compact_merged", suffix)),
           width = 11.6, height = 8.4)
