#!/usr/bin/env Rscript
# plot_paper_agg_compact_ext.R -- the 12-panel grid over SPEC, the agentic 36, and EVERY
# external benchmark suite profiled with kit/dcperf (DCPerf, Renaissance, DaCapo ...).
#
# Unit rule (unchanged): a violin is a distribution over WORKLOADS, one vote each -- SPEC 26,
# agentic 36. External suites have 2-5 profiled benchmarks each, far too few for a violin, so
# every benchmark is a MARKER at its vote (median of its steady-state windows, the same
# statistic every SPEC/agentic vote uses), grouped under its suite's x position and coloured by
# suite; the thin bar is that benchmark's own window p25-p75 (a within-workload spread, a
# different quantity from a violin's width, and labelled as such). Which marker is which
# benchmark is answered by the per-window companion figures (one column per benchmark) and by
# the numbers CSV; the compact grid's job is the family-level picture.
#
# EXT_ROWS = colon-separated list of <suite>_rows_long.csv files (export_dcperf_rows.py).
suppressPackageStartupMessages({
  library(ggplot2); library(dplyr); library(ragg); library(scales); library(patchwork)
})
repo <- path.expand("~/InferSuite")
source(file.path(repo, "local_agents/kit/plot/theme_paper.R"))
ADJ <- as.numeric(Sys.getenv("ADJ", "1.0"))
EXT_FILES <- strsplit(Sys.getenv("EXT_ROWS",
  paste(file.path(repo, "local_agents/DCPerf/data/l3_study/dcperf_rows_long.csv"),
        file.path(repo, "local_agents/JVMbench/data/l3_study/renaissance_rows_long.csv"),
        file.path(repo, "local_agents/JVMbench/data/l3_study/dacapo_rows_long.csv"), sep = ":")),
  ":")[[1]]
EXT_FILES <- EXT_FILES[file.exists(EXT_FILES)]
stopifnot(length(EXT_FILES) > 0)
OUT <- file.path(repo, Sys.getenv("EXT_OUT", "local_agents/JVMbench/plots/paper_v1"))
dir.create(OUT, showWarnings = FALSE, recursive = TRUE)
STEM <- Sys.getenv("EXT_STEM", "multi_agg_compact")

FAM_COL <- c(DCPerf = "#1b7837", Renaissance = "#e6ab02", DaCapo = "#7570b3")
langs <- c("C", "C++", "Rust", "Go", "Java", "PHP", "Ruby", "JavaScript", "TypeScript")
METRICS <- c("IPC",
             "Branch MPKI", "Branch-direction MPKI", "BTB MPKI (BAClears)",
             "L1I MPKI (code-read)", "uop-cache (DSB) MPKI", "DSB coverage (%)",
             "L1D-load MPKI", "L2-load MPKI", "LLC MPKI", "DRAM read (GB/s)",
             "Context switches (/CPU-s)")
logm <- "Context switches (/CPU-s)"

d <- read.csv(file.path(repo, "local_agents/ML_iso36/data/l3_study/agg_rows_long.csv"),
              stringsAsFactors = FALSE) |> filter(fence == "both")
per_workload <- bind_rows(
  d |> filter(grp %in% c("SPEC-int", "SPEC-fp")) |>
    group_by(metric, wl = paste(grp, ave(value, metric, grp, FUN = seq_along))) |>
    summarise(v = first(value), .groups = "drop") |> mutate(side = "SPEC"),
  d |> filter(grp %in% langs) |>
    group_by(metric, wl = col) |>
    summarise(v = median(value), .groups = "drop") |> mutate(side = "Agentic"))

ext <- bind_rows(lapply(EXT_FILES, read.csv, stringsAsFactors = FALSE)) |> filter(fence == "both")
FAMS <- intersect(names(FAM_COL), unique(ext$grp))
ext_vote <- ext |> group_by(metric, fam = grp, wl = col) |>
  summarise(v = median(value), q25 = quantile(value, .25), q75 = quantile(value, .75),
            nwin = n(), .groups = "drop")
SIDES <- c("SPEC", "Agentic", FAMS)
COLS <- c(SPEC = unname(PAPER_PAIR["blue_dark"]), Agentic = unname(PAPER_PAIR["red_dark"]),
          FAM_COL[FAMS])
per_workload$side <- factor(per_workload$side, levels = SIDES)
ext_vote$fam <- factor(ext_vote$fam, levels = SIDES)

num <- bind_rows(
  per_workload |> group_by(metric, side) |>
    summarise(n = n(), min = min(v), max = max(v), median = median(v), mean = mean(v),
              sd = sd(v), .groups = "drop") |> mutate(workload = NA_character_),
  ext_vote |> transmute(metric, side = as.character(fam), workload = wl, n = nwin,
                        min = q25, max = q75, median = v, mean = v, sd = NA_real_))
write.csv(num, file.path(OUT, paste0(STEM, "_numbers.csv")), row.names = FALSE)

panel <- function(m) {
  dm <- per_workload |> filter(metric == m)
  em <- ext_vote |> filter(metric == m)
  use_log <- m %in% logm
  is_pct <- grepl("\\(%\\)", m)
  pooled <- c(dm$v, em$v)
  vis_max <- max(c(pooled, em$q75), na.rm = TRUE)
  qual <- !use_log && !is_pct && paper_break_qualifies(pooled)
  fam_med <- sapply(FAMS, function(f) median(em$v[em$fam == f]))
  fam_n   <- sapply(FAMS, function(f) sum(em$fam == f))
  meds <- c(sapply(c("SPEC", "Agentic"), function(s) median(dm$v[dm$side == s])), fam_med)
  med_lab <- ifelse(meds == 0 & use_log, "0†", sprintf("%.3g", meds))
  xlabs <- setNames(sprintf("%s\nmed %s", SIDES, med_lab), SIDES)
  th <- theme_paper(base_size = 8) +
    theme(plot.title = element_text(size = 7.4, hjust = 0.5, face = "plain",
                                    margin = margin(b = 2)),
          axis.text.x = element_text(size = 5.6, lineheight = 0.9),
          axis.text.y = element_text(size = 5.8),
          panel.grid.major.x = element_blank())
  base <- function(dd, ee, lo = NULL) {
    if (!is.null(lo)) { dd$v <- pmax(dd$v, lo); ee$v <- pmax(ee$v, lo)
                        ee$q25 <- pmax(ee$q25, lo); ee$q75 <- pmax(ee$q75, lo) }
    dodge <- position_dodge(width = 0.62)
    ggplot(dd, aes(x = side, y = v, fill = side)) +
      geom_violin(scale = "width", width = 0.72, linewidth = PAPER_VIOLIN_LW,
                  colour = "black", adjust = ADJ, trim = TRUE, alpha = 0.75) +
      paper_inner_box(width = 0.08, lw = 0.28, diamond = 1.5) +
      geom_linerange(data = ee, aes(x = fam, ymin = q25, ymax = q75, group = wl),
                     inherit.aes = FALSE, position = dodge, linewidth = 0.45, colour = "grey30") +
      geom_point(data = ee, aes(x = fam, y = v, group = wl, fill = fam), inherit.aes = FALSE,
                 position = dodge, shape = 23, size = 2.0, colour = "black", stroke = 0.4) +
      scale_fill_manual(values = COLS, guide = "none", limits = SIDES) +
      scale_x_discrete(limits = SIDES, labels = xlabs, expand = expansion(add = 0.6),
                       drop = FALSE) +
      labs(x = NULL, y = NULL) + th
  }
  if (use_log) {
    pos <- pooled[pooled > 0]
    lo <- 10^floor(log10(max(min(pos), 1e-2)))
    hi <- 10^ceiling(log10(vis_max))
    return(base(dm, em, lo) + ggtitle(m) +
      scale_y_log10(limits = c(lo, hi), breaks = 10^seq(log10(lo), log10(hi)),
                    labels = label_number(drop0trailing = TRUE), expand = expansion(0, 0)))
  }
  if (is_pct) return(base(dm, em) + ggtitle(m) + paper_scale_y(0, 100, 25))
  if (!qual) {
    br <- pretty(c(0, vis_max * 1.03), 5)
    return(base(dm, em) + ggtitle(m) + paper_scale_y(0, max(br), br[2] - br[1]))
  }
  thr <- 3 * quantile(pooled, .95)
  body_max <- max(pooled[pooled <= thr]); out_min <- min(pooled[pooled > thr])
  brk <- pretty(c(0, body_max * 1.12), 5); brk_lo <- max(brk)
  ub <- pretty(c(out_min, vis_max * 1.02), 2)
  step <- if (length(ub) > 1) ub[2] - ub[1] else out_min * 0.1
  up_lo <- floor(out_min / step) * step
  if (up_lo <= brk_lo) up_lo <- signif(out_min * 0.95, 2)
  up_hi <- max(ub)
  stopifnot(up_lo <= out_min, up_lo > brk_lo, brk_lo >= body_max)
  lower <- base(dm, em) +
    scale_y_continuous(limits = c(0, brk_lo), breaks = brk, expand = expansion(0, 0),
                       oob = scales::oob_squish) +
    annotate("text", x = 0.47, y = brk_lo * 0.985, label = "∕∕", size = 2.3,
             hjust = 0.5, family = PAPER_SERIF, fontface = "bold") +
    theme(plot.margin = margin(0.6, 8, 6, 6))
  up_pts <- bind_rows(dm |> filter(v > thr) |> transmute(side = as.character(side), v),
                      em |> filter(v > thr) |> transmute(side = as.character(fam), v))
  upper <- ggplot(up_pts, aes(x = side, y = v)) +
    geom_point(shape = 21, size = 1.2, fill = "grey35", colour = "black", stroke = 0.3) +
    scale_x_discrete(limits = SIDES, expand = expansion(add = 0.6), drop = FALSE) +
    scale_y_continuous(limits = c(up_lo, up_hi), breaks = c(up_lo, up_hi),
                       expand = expansion(0, 0)) +
    labs(x = NULL, y = NULL) + ggtitle(m) + th +
    theme(axis.text.x = element_blank(), axis.ticks.x = element_blank(),
          plot.margin = margin(6, 8, 0.6, 6)) +
    annotate("text", x = 0.47, y = up_lo + (up_hi - up_lo) * 0.03, label = "∕∕",
             size = 2.3, hjust = 0.5, family = PAPER_SERIF, fontface = "bold")
  (upper / lower) + plot_layout(heights = c(0.2, 0.8))
}

# legend strip: items laid out left-to-right and centred as a group
legend_strip <- function() {
  items <- list(list(kind = "rect", col = COLS[["SPEC"]], lab = "SPEC (26 benchmarks)"),
                list(kind = "rect", col = COLS[["Agentic"]], lab = "Agentic (36 tasks)"))
  for (f in FAMS) {
    nb <- length(unique(ext_vote$wl[ext_vote$fam == f]))
    items[[length(items) + 1]] <- list(kind = "diamond", col = FAM_COL[[f]],
                                       lab = sprintf("%s (%d benchmarks, 1 marker each)", f, nb))
  }
  items[[length(items) + 1]] <- list(kind = "bar", col = "black", lab = "median")
  items[[length(items) + 1]] <- list(kind = "diamond", col = "white", lab = "mean")
  items[[length(items) + 1]] <- list(kind = "iqr", col = "grey30", lab = "marker bar = window IQR (within-workload)")
  cw <- 0.0052; gap <- 0.028
  widths <- sapply(items, function(it) 0.03 + nchar(it$lab) * cw)
  x0 <- (1 - (sum(widths) + gap * (length(items) - 1))) / 2
  g <- ggplot() + xlim(0, 1) + ylim(0, 1) + theme_void() + theme(plot.margin = margin(2, 8, 4, 8))
  x <- x0
  for (i in seq_along(items)) {
    it <- items[[i]]
    if (it$kind == "rect") g <- g + annotate("rect", xmin = x, xmax = x + 0.02, ymin = 0.28, ymax = 0.72,
                                             fill = it$col, colour = "black", linewidth = 0.3)
    if (it$kind == "diamond") g <- g + annotate("point", x = x + 0.01, y = 0.5, shape = 23, size = 2.2,
                                                fill = it$col, colour = "black", stroke = 0.45)
    if (it$kind == "bar") g <- g + annotate("segment", x = x, xend = x + 0.02, y = 0.5, yend = 0.5,
                                            colour = "black", linewidth = 1.0)
    if (it$kind == "iqr") g <- g + annotate("segment", x = x + 0.01, xend = x + 0.01, y = 0.25, yend = 0.75,
                                            colour = it$col, linewidth = 0.55)
    g <- g + annotate("text", x = x + 0.028, y = 0.5, label = it$lab, hjust = 0, size = 2.35,
                      family = PAPER_SERIF)
    x <- x + widths[i] + gap
  }
  g
}

ps <- lapply(METRICS, panel)
grid <- wrap_plots(ps, ncol = 4)
fig <- (legend_strip() / grid) + plot_layout(heights = c(0.04, 1))
paper_save(fig, file.path(OUT, STEM), width = 10.4 + 1.25 * length(FAMS), height = 8.3)
