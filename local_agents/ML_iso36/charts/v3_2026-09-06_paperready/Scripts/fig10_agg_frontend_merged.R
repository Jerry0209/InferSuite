#!/usr/bin/env Rscript
# fig10_agg_frontend_merged — COPY of the canonical generator local_agents/kit/plot/plot_paper_agg_groups.R
# (single source of truth; edit THERE). Runs from the repo root against the
# banked data tree and writes into plots/paper_v2/.
# Regenerate: see charts/README.md.
# plot_paper_agg_groups.R -- the aggregated per-window comparison, MERGED agent fence
# (tool+harness summed at the raw-count level per window -- fence "both" from
# analyze_l3_windows.py), rendered in the paper style (theme_paper.R; mentor 2026-08-31).
#
#   group 1  ipc       : IPC
#   group 2  frontend  : Branch MPKI, Branch-direction MPKI, BTB MPKI, L1I MPKI,
#                        DSB MPKI (uop-cache miss), DSB hit rate -- exact order
#   group 3  memory    : L1D-load MPKI, L2-load MPKI, LLC MPKI, DRAM read GB/s
#   group 4  system    : context switches (/CPU-s)
#
# Columns: SPEC-int, SPEC-fp (grey band + solid black boundary = the reference group),
# then the 9 languages x 4 tasks separated by DOTTED language lines. Every column carries
# a rotated median label at the panel top. Python pilots are excluded (their replays were
# not re-derived with the merged fence). Violin + box + median bar + mean diamond, black
# edges everywhere, axis caps with off-scale triangles (stats always on full data).
#
# Inputs : local_agents/ML_iso36/data/l3_study/agg_rows_long.csv (fence == "both")
# Outputs: local_agents/ML_iso36/plots/paper_v1/iso36_agg_<group>_merged.{png,pdf}
#          local_agents/ML_iso36/plots/paper_v1/iso36_agg_merged_numbers.csv
suppressPackageStartupMessages({
  library(ggplot2); library(dplyr); library(tidyr); library(ragg); library(scales)
  library(patchwork)
})
repo <- path.expand("~/InferSuite")
source(file.path(repo, "local_agents/kit/plot/theme_paper.R"))
OUT <- file.path(repo, "local_agents/ML_iso36/plots/paper_v2")
dir.create(OUT, showWarnings = FALSE, recursive = TRUE)

d <- read.csv(file.path(repo, "local_agents/ML_iso36/data/l3_study/agg_rows_long.csv"),
              stringsAsFactors = FALSE) |> filter(fence == "both", grp != "Python")

langs <- c("C", "C++", "Rust", "Go", "Java", "PHP", "Ruby", "JavaScript", "TypeScript")
lcol <- c("SPEC-int" = "#4d4d4d", "SPEC-fp" = "#b3b3b3",
          "C" = "#0072B2", "C++" = "#56B4E9", "Rust" = "#D55E00", "Go" = "#009E73",
          "Java" = "#E69F00", "PHP" = "#CC79A7", "Ruby" = "#6b4fa0",
          "JavaScript" = "#F0E442", "TypeScript" = "#111111")
GROUPS <- list(
  ipc      = c("IPC"),
  frontend = c("Branch MPKI", "Branch-direction MPKI", "BTB MPKI (BAClears)",
               "L1I MPKI (code-read)", "uop-cache (DSB) MPKI", "DSB coverage (%)"),
  memory   = c("L1D-load MPKI", "L2-load MPKI", "LLC MPKI", "DRAM read (GB/s)"),
  system   = c("Context switches (/CPU-s)"))
logm <- "Context switches (/CPU-s)"

# column order: SPEC-int, SPEC-fp, then each language's tasks (no spacer columns --
# dotted separators demarcate the groups instead)
ord <- c("SPEC-int", "SPEC-fp"); grp_of <- c("SPEC-int" = "SPEC-int", "SPEC-fp" = "SPEC-fp")
lang_span <- list()
for (lg in langs) {
  cols <- unique(d$col[d$grp == lg])
  lang_span[[lg]] <- c(length(ord) + 1, length(ord) + length(cols))
  ord <- c(ord, cols)
  for (cc in cols) grp_of[cc] <- lg
}
d$col_f <- factor(d$col, levels = ord)
d$fillg <- grp_of[d$col]
SEP_AGG <- 2.5                                       # after SPEC-fp: the aggregate boundary
SEP_LANG <- sapply(lang_span, function(s) s[2] + 0.5)
SEP_LANG <- SEP_LANG[-length(SEP_LANG)]              # none after the last language

med_tab <- d |> group_by(metric, col_f, fillg) |>
  summarise(med = median(value), mean = mean(value), n = n(), .groups = "drop")
write.csv(med_tab |> rename(column = col_f, language = fillg),
          file.path(OUT, "iso36_agg_merged_numbers.csv"), row.names = FALSE)

panel <- function(m, show_x) {
  dm <- d |> filter(metric == m)
  use_log <- m %in% logm
  TRIM <- c("BTB MPKI (BAClears)", "L1D-load MPKI", "L2-load MPKI", "LLC MPKI")
  p97 <- dm |> group_by(col_f) |> summarise(q97 = quantile(value, .97),
                                            q95 = quantile(value, .95), .groups = "drop")
  cap <- if (m %in% TRIM) quantile(p97$q95, .85) * 1.2 else max(p97$q97) * 1.15
  if (grepl("\\(%\\)", m)) cap <- min(cap, 100)
  p <- ggplot(dm, aes(x = col_f, y = value, fill = fillg)) +
    paper_band(0.4, SEP_AGG) +
    geom_violin(scale = "width", width = 0.85, linewidth = PAPER_VIOLIN_LW,
                colour = "black", adjust = 1.2, trim = TRUE, alpha = 0.75) +
    paper_inner_stats(scale = 0.42) +
    paper_agg_sep(SEP_AGG) + paper_lang_sep(SEP_LANG) +
    scale_fill_manual(values = lcol, guide = "none") +
    paper_x_discrete() +
    labs(y = m, x = NULL) +
    theme_paper(base_size = 8) +
    theme(axis.title.y = element_text(size = 7),
          axis.text.y = element_text(size = 6),
          panel.grid.major.x = element_blank())
  if (use_log) {
    lo <- 10^floor(log10(max(min(dm$value[dm$value > 0]), 1e-2)))
    hi <- 10^ceiling(log10(max(dm$value)))
    p <- p + scale_y_log10(limits = c(lo, hi),
                           breaks = 10^seq(log10(lo), log10(hi)),
                           labels = label_number(drop0trailing = TRUE),
                           expand = expansion(0, 0))
  } else {
    br <- pretty(c(0, cap), 5); hi <- max(br)
    mx <- dm |> group_by(col_f) |> summarise(mx = max(value), .groups = "drop") |>
      filter(mx > hi)
    p <- p + paper_scale_y(0, hi, br[2] - br[1])
    # paper-ready (PI 2026-09-06): the triangle alone marks an off-scale column max
    # (axis capped; stats always on full data) -- no on-figure text, the caption carries it
    if (nrow(mx) > 0) {
      p <- p +
        geom_point(data = mx, aes(x = col_f, y = hi * 0.995), shape = 17, size = 0.8,
                   colour = "#b2182b", inherit.aes = FALSE)
    }
  }
  if (show_x) {
    p <- p + theme(axis.text.x = element_text(angle = 90, hjust = 1, vjust = 0.5,
                                              size = 5.4))
  } else {
    p <- p + theme(axis.text.x = element_blank())
  }
  p
}

add_headers <- function(p) {
  p <- p + coord_cartesian(clip = "off") +
    annotate("text", x = 1.5, y = Inf, vjust = -0.7, label = "SPEC CPU 2026",
             size = 2.0, fontface = "bold", colour = "#4d4d4d", family = PAPER_SERIF)
  for (lg in langs) {
    p <- p + annotate("text", x = mean(lang_span[[lg]]), y = Inf, vjust = -0.7,
                      label = lg, size = 2.0, fontface = "bold", colour = lcol[[lg]],
                      family = PAPER_SERIF)
  }
  p + theme(plot.margin = margin(14, 8, 6, 6))
}

# paper-ready (PI 2026-09-06): no title / subtitle / caption / per-column median labels --
# the filename and the paper caption carry them; column medians stay banked in the CSV
for (gname in names(GROUPS)) {
  ms <- GROUPS[[gname]]
  ps <- lapply(seq_along(ms), function(k) panel(ms[k], show_x = (k == length(ms))))
  ps[[1]] <- add_headers(ps[[1]])
  h <- 2.45 * length(ms) + 0.9
  fig <- wrap_plots(ps, ncol = 1)
  paper_save(fig, file.path(OUT, sprintf("iso36_agg_%s_merged", gname)), width = 14, height = h)
}
