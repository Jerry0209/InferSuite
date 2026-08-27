#!/usr/bin/env Rscript
# plot_iso36_rows_agg.R -- house-style rendering of the aggregated per-window rows
# (mentor revision 2026-08-27): 16 metrics (MLP and AMAT dropped), one full-width row
# each; columns = SPEC-int | SPEC-fp (box over per-benchmark window-medians) | Python
# (3 tasks + reserved 4th) | 9 languages x 4 tasks. Violin + box (median line INSIDE the
# box, mean = white diamond). Outlier-heavy panels are AXIS-CAPPED, never data-trimmed:
# stats are computed on the full distributions and coord_cartesian cuts the view; a
# triangle marker + text names the off-scale maximum and its column.
#
# Inputs : local_agents/ML_iso36/data/l3_study/agg_rows_long.csv
# Outputs: local_agents/ML_iso36/plots/iso36_rows_agg_gg_{tool,harness}.{png,pdf}
#          local_agents/ML_iso36/plots/iso36_rows_agg_gg_numbers.csv
suppressPackageStartupMessages({
  library(ggplot2); library(hrbrthemes); library(dplyr); library(tidyr)
  library(yaml); library(ragg); library(scales); library(patchwork)
})
repo <- path.expand("~/InferSuite")
source(file.path(repo, "local_agents/kit/plot/iso36_style.R"))

d <- read.csv(file.path(repo, "local_agents/ML_iso36/data/l3_study/agg_rows_long.csv"),
              stringsAsFactors = FALSE)

langs <- c("C", "C++", "Rust", "Go", "Java", "PHP", "Ruby", "JavaScript", "TypeScript")
lcol <- c("SPEC-int" = "#4d4d4d", "SPEC-fp" = "#b3b3b3", "Python" = "#8c510a",
          "C" = "#0072B2", "C++" = "#56B4E9", "Rust" = "#D55E00", "Go" = "#009E73",
          "Java" = "#E69F00", "PHP" = "#CC79A7", "Ruby" = "#6b4fa0",
          "JavaScript" = "#F0E442", "TypeScript" = "#111111")
metrics <- c("IPC", "Branch MPKI", "Branch-direction MPKI", "BTB MPKI (BAClears)",
             "DSB coverage (%)", "uop-cache (DSB) MPKI", "L1I MPKI (code-read)",
             "L1D-load MPKI", "L2-load MPKI", "LLC MPKI", "L1I stall (% cycles)",
             "L1D miss rate (%)", "L2-load miss rate (%)", "LLC miss rate (%)",
             "DRAM read (GB/s)", "Context switches (/CPU-s)")
logm <- "Context switches (/CPU-s)"

# column order with spacer levels between groups; Python keeps a reserved 4th slot
ord <- c("SPEC-int", "SPEC-fp", ".s1",
         "scikit-learn", "astropy", "sympy", "(4th: to fill)", ".s2")
grp_of <- c("SPEC-int" = "SPEC-int", "SPEC-fp" = "SPEC-fp",
            "scikit-learn" = "Python", "astropy" = "Python", "sympy" = "Python",
            "(4th: to fill)" = "Python")
i <- 3
for (lg in langs) {
  cols <- unique(d$col[d$grp == lg])
  ord <- c(ord, cols, paste0(".s", i)); i <- i + 1
  for (cc in cols) grp_of[cc] <- lg
}
ord <- head(ord, -1)
d$col_f <- factor(d$col, levels = ord)
d$fillg <- grp_of[d$col]

num <- d |> group_by(fence, metric, grp, col) |>
  summarise(n = n(), median = median(value), mean = mean(value),
            p5 = quantile(value, .05), p95 = quantile(value, .95),
            max = max(value), .groups = "drop")
write.csv(num, file.path(repo, "local_agents/ML_iso36/plots/iso36_rows_agg_gg_numbers.csv"),
          row.names = FALSE)

groups_span <- function() {
  gs <- list()
  for (g in c("SPEC-int", "SPEC-fp", "Python", langs)) {
    idx <- which(ord %in% names(grp_of)[grp_of == g])
    if (length(idx)) gs[[g]] <- c(min(idx), max(idx))
  }
  gs
}
GS <- groups_span()

panel <- function(dd, m, show_x, fence, hdr = FALSE) {
  dm <- dd |> filter(metric == m)
  use_log <- m %in% logm
  # axis cap: default 1.15x the largest column p97 (whiskers always fit; extreme tails cut
  # from VIEW only, stats remain full-data). For the metrics where a WHOLE COLUMN is the
  # outlier (mentor 2026-08-27: BTB, the load-MPKI ladder), key the cap off the 90th
  # percentile of the columns' p95s instead, so the outlier columns cannot set the axis --
  # they go off-scale and are named by the red-triangle note.
  TRIM <- c("BTB MPKI (BAClears)", "L1D-load MPKI", "L2-load MPKI", "LLC MPKI")
  p97 <- dm |> group_by(col_f) |> summarise(q97 = quantile(value, .97),
                                            q95 = quantile(value, .95), .groups = "drop")
  cap <- if (m %in% TRIM) quantile(p97$q95, .90) * 1.2 else max(p97$q97) * 1.15
  mx <- dm |> group_by(col_f, fillg) |> summarise(mx = max(value), .groups = "drop") |>
    filter(mx > cap)
  p <- ggplot(dm, aes(x = col_f, y = value, fill = fillg)) +
    geom_violin(scale = "width", width = 0.85, linewidth = 0.15, colour = "grey40",
                adjust = 1.2, trim = TRUE, alpha = 0.75) +
    geom_boxplot(width = 0.28, outlier.shape = NA, linewidth = 0.25,
                 colour = "grey15", fill = "white", alpha = 0.9,
                 coef = 0) +
    stat_summary(fun = median, geom = "crossbar", width = 0.28, linewidth = 0.3,
                 colour = "black") +
    stat_summary(fun = mean, geom = "point", shape = 23, size = 1.1,
                 fill = "white", colour = "black", stroke = 0.35) +
    scale_fill_manual(values = lcol, guide = "none") +
    scale_x_discrete(drop = FALSE, labels = function(x) ifelse(grepl("^\\.s", x), "", x)) +
    labs(y = m, x = NULL) +
    theme_house(base_size = 8, axis_title_size = 8) +
    theme(axis.title.y = element_text(size = 6.6),
          axis.text.y = element_text(size = 5.8),
          panel.grid.major.x = element_blank(),
          plot.margin = margin(1, 4, 1, 2))
  if (use_log) {
    p <- p + scale_y_log10(labels = label_number(drop0trailing = TRUE))
  } else {
    p <- p + coord_cartesian(ylim = c(0, cap), clip = if (hdr) "off" else "on")
    if (nrow(mx) > 0) {
      mx <- mx |> arrange(desc(mx))
      lab3 <- paste(sprintf("%s %.3g", head(mx$col_f, 3), head(mx$mx, 3)), collapse = " · ")
      if (nrow(mx) > 3) lab3 <- paste0(lab3, sprintf("  (+%d more)", nrow(mx) - 3))
      p <- p +
        geom_point(data = mx, aes(x = col_f, y = cap * 0.985), shape = 17, size = 0.9,
                   colour = "#b2182b", inherit.aes = FALSE) +
        annotate("text", x = length(ord) - 0.5, y = cap * 0.93, hjust = 1, vjust = 1,
                 size = 1.7, colour = "#b2182b",
                 label = paste0("axis capped; off-scale max: ", lab3))
    }
  }
  if (show_x) {
    p <- p + theme(axis.text.x = element_text(angle = 90, hjust = 1, vjust = 0.5, size = 5.2))
  } else {
    p <- p + theme(axis.text.x = element_blank(), axis.ticks.x = element_blank())
  }
  p
}

for (fence in c("tool", "harness")) {
  dd <- d |> filter(fence == !!fence)
  ps <- lapply(seq_along(metrics), function(k)
    panel(dd, metrics[k], show_x = (k == length(metrics)), fence, hdr = (k == 1)))
  # group headers on the first panel (SPEC-int and SPEC-fp are one column each —
  # separate headers collide, so they share one combined header)
  hdr <- ps[[1]] + annotate("text", x = 1.5, y = Inf, vjust = -0.55,
                            label = "SPEC CPU 2026", size = 2.0, fontface = "bold",
                            colour = "#4d4d4d")
  for (g in setdiff(names(GS), c("SPEC-int", "SPEC-fp"))) {
    hcol <- if (g == "TypeScript") "#111111" else lcol[[g]]
    hdr <- hdr + annotate("text", x = mean(GS[[g]]), y = Inf, vjust = -0.55,
                          label = g, size = 2.0, fontface = "bold", colour = hcol)
  }
  ps[[1]] <- hdr + theme(plot.margin = margin(9, 4, 1, 2))
  fig <- wrap_plots(ps, ncol = 1) + plot_annotation(
    title = sprintf("Per-window distributions, aggregated SPEC — %s fence", fence),
    subtitle = paste("SPEC-int / SPEC-fp = violin over per-benchmark window-medians (one vote per benchmark)",
                     "· violin + box, black bar = median, white diamond = mean",
                     "· red triangle = off-scale outlier (axis capped at 1.15x the largest column p97; stats use full data)"),
    caption = "Python: matched-configuration replays; the fe_miss trio and some rates are not banked for Python (empty slots) · 100 ms windows",
    theme = theme(plot.title = element_text(size = 11, face = "bold"),
                  plot.subtitle = element_text(size = 6.4, colour = "grey35"),
                  plot.caption = element_text(size = 5.4, colour = "grey45")))
  house_save(fig, file.path(repo, sprintf("local_agents/ML_iso36/plots/iso36_rows_agg_gg_%s", fence)),
             width = 14, height = 22)
}
