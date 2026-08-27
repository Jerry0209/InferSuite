#!/usr/bin/env Rscript
# plot_iso36_agg_groups.R -- the aggregated per-window comparison SPLIT INTO GROUP
# pictures (mentor feedback 2026-08-28). NEW files beside the all-in-one figures, which
# stay untouched.
#
#   group 1  ipc       : IPC
#   group 2  frontend  : Branch MPKI, Branch-direction MPKI, BTB MPKI, L1I MPKI,
#                        DSB MPKI (uop-cache miss), DSB hit rate (coverage %) -- exact order
#   group 3  memory    : L1D-load MPKI, L2-load MPKI, LLC MPKI, DRAM read GB/s
#   group 4  system    : context switches (/CPU-s)
#   (miss rates and L1I stall deliberately omitted per the mentor)
#
# Each metric chart carries a BLACK BOUNDING BOX around its plotting area and generous
# spacing from its neighbours; every picture exports PNG + PDF (house_save). Columns,
# violin+box+mean and the outlier axis caps are identical to plot_iso36_rows_agg.R.
#
# Inputs : local_agents/ML_iso36/data_live/../data/l3_study/agg_rows_long.csv (via export_agg_rows_long.py)
# Outputs: local_agents/ML_iso36/plots/iso36_agg_<group>_<fence>.{png,pdf} (8 pictures)
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
GROUPS <- list(
  ipc      = c("IPC"),
  frontend = c("Branch MPKI", "Branch-direction MPKI", "BTB MPKI (BAClears)",
               "L1I MPKI (code-read)", "uop-cache (DSB) MPKI", "DSB coverage (%)"),
  memory   = c("L1D-load MPKI", "L2-load MPKI", "LLC MPKI", "DRAM read (GB/s)"),
  system   = c("Context switches (/CPU-s)"))
logm <- "Context switches (/CPU-s)"

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

groups_span <- function() {
  gs <- list()
  for (g in c("SPEC-int", "SPEC-fp", "Python", langs)) {
    idx <- which(ord %in% names(grp_of)[grp_of == g])
    if (length(idx)) gs[[g]] <- c(min(idx), max(idx))
  }
  gs
}
GS <- groups_span()

# black bounding box around every chart area + breathing room between charts
box_th <- theme(panel.border = element_rect(colour = "black", fill = NA, linewidth = 0.55),
                plot.margin = margin(14, 10, 14, 6))

panel <- function(dd, m, show_x, hdr = FALSE) {
  dm <- dd |> filter(metric == m)
  use_log <- m %in% logm
  TRIM <- c("BTB MPKI (BAClears)", "L1D-load MPKI", "L2-load MPKI", "LLC MPKI")
  p97 <- dm |> group_by(col_f) |> summarise(q97 = quantile(value, .97),
                                            q95 = quantile(value, .95), .groups = "drop")
  cap <- if (m %in% TRIM) quantile(p97$q95, .85) * 1.2 else max(p97$q97) * 1.15
  if (grepl("\\(%\\)", m)) cap <- min(cap, 102)   # a percentage axis never exceeds 100
  mx <- dm |> group_by(col_f, fillg) |> summarise(mx = max(value), .groups = "drop") |>
    filter(mx > cap)
  p <- ggplot(dm, aes(x = col_f, y = value, fill = fillg)) +
    geom_violin(scale = "width", width = 0.85, linewidth = 0.15, colour = "grey40",
                adjust = 1.2, trim = TRUE, alpha = 0.75) +
    geom_boxplot(width = 0.28, outlier.shape = NA, linewidth = 0.25,
                 colour = "grey15", fill = "white", alpha = 0.9, coef = 0) +
    stat_summary(fun = median, geom = "crossbar", width = 0.28, linewidth = 0.3,
                 colour = "black") +
    stat_summary(fun = mean, geom = "point", shape = 23, size = 1.1,
                 fill = "white", colour = "black", stroke = 0.35) +
    scale_fill_manual(values = lcol, guide = "none") +
    scale_x_discrete(drop = FALSE, labels = function(x) ifelse(grepl("^\\.s", x), "", x)) +
    labs(y = m, x = NULL) +
    theme_house(base_size = 8, axis_title_size = 8) +
    theme(axis.title.y = element_text(size = 7),
          axis.text.y = element_text(size = 6),
          panel.grid.major.x = element_blank()) +
    box_th
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
                 size = 1.8, colour = "#b2182b",
                 label = paste0("axis capped; off-scale max: ", lab3))
    }
  }
  if (show_x) {
    p <- p + theme(axis.text.x = element_text(angle = 90, hjust = 1, vjust = 0.5, size = 5.4))
  } else {
    p <- p + theme(axis.text.x = element_blank(), axis.ticks.x = element_blank())
  }
  p
}

add_headers <- function(p, log_panel = FALSE) {
  p <- p + annotate("text", x = 1.5, y = Inf, vjust = -0.6, label = "SPEC CPU 2026",
                    size = 2.0, fontface = "bold", colour = "#4d4d4d")
  for (g in setdiff(names(GS), c("SPEC-int", "SPEC-fp"))) {
    hcol <- if (g == "TypeScript") "#111111" else lcol[[g]]
    p <- p + annotate("text", x = mean(GS[[g]]), y = Inf, vjust = -0.6,
                      label = g, size = 2.0, fontface = "bold", colour = hcol)
  }
  p + theme(plot.margin = margin(16, 10, 14, 6))
}

for (fence in c("tool", "harness")) {
  dd <- d |> filter(fence == !!fence)
  for (gname in names(GROUPS)) {
    ms <- GROUPS[[gname]]
    ps <- lapply(seq_along(ms), function(k)
      panel(dd, ms[k], show_x = (k == length(ms)), hdr = (k == 1)))
    ps[[1]] <- add_headers(ps[[1]], log_panel = (ms[1] %in% logm))
    h <- 2.55 * length(ms) + 1.6
    fig <- wrap_plots(ps, ncol = 1) + plot_annotation(
      title = sprintf("%s — %s fence",
                      c(ipc = "IPC", frontend = "Frontend metrics",
                        memory = "Memory metrics", system = "System-level metrics")[gname], fence),
      subtitle = paste("SPEC-int / SPEC-fp = violin over per-benchmark window-medians (one vote per benchmark)",
                       "· violin + box, black bar = median, white diamond = mean",
                       "· red triangle = off-scale outlier (axis capped; stats use full data)"),
      caption = "100 ms windows · Python = matched-configuration replays (metrics not banked for Python appear empty)",
      theme = theme(plot.title = element_text(size = 11.5, face = "bold"),
                    plot.subtitle = element_text(size = 6.4, colour = "grey35"),
                    plot.caption = element_text(size = 5.6, colour = "grey45")))
    house_save(fig, file.path(repo, sprintf("local_agents/ML_iso36/plots/iso36_agg_%s_%s", gname, fence)),
               width = 14, height = h)
  }
}
