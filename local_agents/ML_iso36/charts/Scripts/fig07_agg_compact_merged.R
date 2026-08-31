#!/usr/bin/env Rscript
# fig07_agg_compact_merged — COPY of the canonical generator local_agents/kit/plot/plot_paper_agg_compact.R
# (single source of truth; edit THERE). Runs from the repo root against the
# banked data tree and writes into plots/paper_v2/.
# Regenerate: see charts/README.md.
# plot_paper_agg_compact.R -- the 12-panel SPEC-vs-Agentic grid, violin revision v2
# (mentor spec 2026-09-01), MERGED agent fence. Components from theme_paper.R:
#   - paired hue/lightness palette: the two DARK hues (SPEC = dark blue, Agentic = dark
#     red); thin black violin outlines
#   - the inner-statistics glyph: p5-p95 whisker, THICK black IQR bar, white square =
#     median, black circle = mean (one encoding everywhere, stated in the subtitle)
#   - raw workloads overlaid as jittered points (n = 26 / 36 -- the KDE alone is mostly
#     bandwidth at this n; the points are the evidence)
#   - broken y-axis ONLY where pooled max > 3x pooled p95 (printed per panel).
#     NOTE deviation from the spec: ggbreak + as.ggplot silently DROPS the break when the
#     wrapped grob is composed (verified 2026-09-01 -- the four panels rendered with flat
#     full axes), so the break is built manually as a two-piece patchwork cell: lower
#     piece = the body, upper piece = the outlier zone, double-slash marks at the seam
#   - the context-switches panel stays log (NEVER break + log): SPEC's median is exactly
#     0, which has no position on a log axis -- glyph clamped to the floor, labeled 0+dagger
#   - per the spec, the 12-panel grid keeps ONE compact median label per violin (a stats
#     strip per panel would be 24 strips); the hero figure carries the strip instead
#
# ADJ=0.8|1.0|1.2 sets the KDE bandwidth multiplier (default 1.0; variants for review).
# Inputs : local_agents/ML_iso36/data/l3_study/agg_rows_long.csv (fence == "both")
# Outputs: plots/paper_v2/iso36_agg_compact_merged[.adj]. {png,pdf} + _numbers.csv
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
  med_lab <- ifelse(nm$median == 0 & use_log, "0\u2020", sprintf("%.3g", nm$median))
  xlabs <- setNames(sprintf("%s\nmed %s", nm$side, med_lab), nm$side)
  th <- theme_paper(base_size = 8) +
    theme(plot.title = element_text(size = 7.4, hjust = 0.5, face = "plain",
                                    margin = margin(b = 2)),
          axis.text.x = element_text(size = 6.2, lineheight = 0.9),
          axis.text.y = element_text(size = 5.8),
          panel.grid.major.x = element_blank())
  base <- function(dd) ggplot(dd, aes(x = side, y = v, fill = side)) +
    geom_violin(scale = "width", width = 0.72, linewidth = PAPER_VIOLIN_LW,
                colour = "black", adjust = ADJ, trim = TRUE, alpha = 0.65) +
    paper_jitter() +
    paper_inner_stats(scale = 0.9) +
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
  # manual broken axis: body piece + outlier piece, double-slash marks at the seam
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
  slash <- function(frac) annotate("text", x = 0.47, y = frac, label = "\u2215\u2215",
                                    size = 2.3, hjust = 0.5, family = PAPER_SERIF,
                                    fontface = "bold")
  lower <- base(dm) +
    scale_x_discrete(labels = xlabs, expand = expansion(add = 0.6)) +
    scale_y_continuous(limits = c(0, brk_lo), breaks = brk, expand = expansion(0, 0),
                       oob = scales::oob_squish) +
    annotate("text", x = 0.47, y = brk_lo * 0.985, label = "\u2215\u2215", size = 2.3,
             hjust = 0.5, family = PAPER_SERIF, fontface = "bold")
  upper <- ggplot(dm |> filter(v > thr), aes(x = side, y = v, fill = side)) +
    geom_point(position = position_jitter(width = 0.05, height = 0, seed = 7),
               alpha = 0.6, size = 0.8, colour = "black", shape = 16) +
    scale_fill_manual(values = PAPER_TWO, guide = "none") +
    scale_x_discrete(limits = levels(dm$side), expand = expansion(add = 0.6)) +
    scale_y_continuous(limits = c(up_lo, up_hi), breaks = c(up_lo, up_hi),
                       expand = expansion(0, 0)) +
    labs(x = NULL, y = NULL) + ggtitle(m) + th +
    theme(axis.text.x = element_blank(), axis.ticks.x = element_blank()) +
    annotate("text", x = 0.47, y = up_lo + (up_hi - up_lo) * 0.03, label = "\u2215\u2215",
             size = 2.3, hjust = 0.5, family = PAPER_SERIF, fontface = "bold")
  (upper / lower) + plot_layout(heights = c(0.22, 0.78))
}

ps <- lapply(METRICS, panel)
fig <- wrap_plots(ps, ncol = 4) + plot_annotation(
  title = "SPEC vs Agentic, one vote per workload — combined agent fence (tool + harness)",
  subtitle = paste("SPEC = 26 benchmarks (dark blue), Agentic = the revised all-resolved 36",
                   "(dark red); points = the actual workloads ·", PAPER_STATS_SUBTITLE,
                   "· med = group median (in the x labels)"),
  caption = paste("100 ms windows, matched configuration · axis breaks (∕∕) only where max > 3× pooled p95",
                  "· context-switches panel is LOG while the others are linear — do not compare shapes across panels",
                  "· † SPEC's median is exactly 0: no position on a log axis, glyph clamped to the floor",
                  sprintf("· KDE bandwidth: nrd0 × adjust=%.1f (per-side nrd0 in the numbers CSV)", ADJ)),
  theme = theme(plot.title = element_text(size = 11.5, face = "bold", family = PAPER_SERIF),
                plot.subtitle = element_text(size = 6.4, colour = "grey35", family = PAPER_SERIF),
                plot.caption = element_text(size = 5.6, colour = "grey45", family = PAPER_SERIF)))
paper_save(fig, file.path(OUT, paste0("iso36_agg_compact_merged", suffix)),
           width = 10.5, height = 8.6)
