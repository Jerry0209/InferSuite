#!/usr/bin/env Rscript
# plot_paper_agg_compact3.R -- the 12-panel grid extended to THREE workload families:
# SPEC CPU 2026, the agentic 36 (SWE-bench Multilingual), and DCPerf.
#
# HONESTY RULE (the reason this is not simply a third violin): a violin is a distribution
# OVER WORKLOADS -- SPEC contributes 26 benchmarks, the agentic family 36 tasks, one vote
# each. DCPerf currently contributes ONE profiled benchmark, so it has no across-workload
# distribution to draw. It is therefore rendered as a MARKER at its vote (the median of its
# steady-state windows, the same statistic every SPEC/agentic vote uses), with a thin bar
# showing the p25-p75 of its own windows -- explicitly a WITHIN-workload spread, a different
# quantity from the violins' across-workload spread. When more DCPerf benchmarks are
# profiled, set DCPERF_VIOLIN=1 to draw them as a real violin instead.
#
# Everything else is inherited from the paper contract (theme_paper.R) and matches the
# v3 paper-ready pack: no title, centred legend strip, exact axis termination, dotted grids,
# outward ticks, black edges, broken axes only where pooled max > 3x pooled p95.
#
# Inputs : ML_iso36/data/l3_study/agg_rows_long.csv   (fence == "both")
#          DCPerf/data/l3_study/dcperf_rows_long.csv  (fence == "both")
# Outputs: DCPerf/plots/paper_v1/dcperf_agg_compact3[_adjNN].{png,pdf} + _numbers.csv
suppressPackageStartupMessages({
  library(ggplot2); library(dplyr); library(ragg); library(scales); library(patchwork)
})
repo <- path.expand("~/InferSuite")
source(file.path(repo, "local_agents/kit/plot/theme_paper.R"))
ADJ <- as.numeric(Sys.getenv("ADJ", "1.0"))
DCPERF_VIOLIN <- Sys.getenv("DCPERF_VIOLIN", "0") == "1"
OUT <- file.path(repo, "local_agents/DCPerf/plots/paper_v1")
dir.create(OUT, showWarnings = FALSE, recursive = TRUE)
suffix <- if (ADJ == 1.0) "" else sprintf("_adj%02.0f", ADJ * 10)

PAPER_THREE <- c(SPEC = unname(PAPER_PAIR["blue_dark"]),
                 Agentic = unname(PAPER_PAIR["red_dark"]),
                 DCPerf = "#1b7837")

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

# ---- DCPerf: per-window rows -> one vote per benchmark + its own window spread ----
dcf <- file.path(repo, "local_agents/DCPerf/data/l3_study/dcperf_rows_long.csv")
dc <- read.csv(dcf, stringsAsFactors = FALSE) |> filter(fence == "both")
dc_vote <- dc |> group_by(metric, wl = col) |>
  summarise(v = median(value), q25 = quantile(value, .25), q75 = quantile(value, .75),
            nwin = n(), .groups = "drop") |> mutate(side = "DCPerf")
DC_BENCHES <- sort(unique(dc_vote$wl))
if (DCPERF_VIOLIN) per_workload <- bind_rows(per_workload, dc_vote |> select(metric, wl, v, side))
per_workload$side <- factor(per_workload$side, levels = c("SPEC", "Agentic", "DCPerf"))
SIDES <- if (DCPERF_VIOLIN) c("SPEC", "Agentic", "DCPerf") else c("SPEC", "Agentic", "DCPerf")

num <- per_workload |> group_by(metric, side) |>
  summarise(n = n(), min = min(v), max = max(v), median = median(v), mean = mean(v),
            sd = sd(v), .groups = "drop")
write.csv(bind_rows(num, dc_vote |> transmute(metric, side = paste0("DCPerf:", wl),
                                              n = nwin, min = q25, max = q75,
                                              median = v, mean = v, sd = NA)),
          file.path(OUT, "dcperf_agg_compact3_numbers.csv"), row.names = FALSE)

inner_v1 <- function() list(
  geom_boxplot(width = 0.08, outlier.shape = NA, linewidth = 0.28,
               colour = "grey15", fill = "white", alpha = 0.95, coef = 0),
  stat_summary(fun = median, geom = "crossbar", width = 0.08, linewidth = 0.3,
               colour = "black"),
  stat_summary(fun = mean, geom = "point", shape = 23, size = 1.5,
               fill = "white", colour = "black", stroke = 0.4))

panel <- function(m) {
  dm <- per_workload |> filter(metric == m)
  dcm <- dc_vote |> filter(metric == m)
  use_log <- m %in% logm
  is_pct <- grepl("\\(%\\)", m)
  # the DCPerf marker must always fit on the axis, so its vote joins the pooled range
  pooled <- c(dm$v, dcm$v)
  qual <- !use_log && !is_pct && paper_break_qualifies(pooled)
  cat(sprintf("panel %-28s max=%.4g 3x_p95=%.4g -> break=%s | dcperf med=%s\n",
              m, max(pooled), 3 * quantile(pooled, .95),
              ifelse(qual, "YES", ifelse(use_log, "no (log)", "no")),
              paste(sprintf("%.3g", dcm$v), collapse = ",")))

  meds <- c(sapply(c("SPEC", "Agentic"),
                   function(s) median(dm$v[dm$side == s])), setNames(dcm$v[1], "DCPerf"))
  med_lab <- ifelse(meds == 0 & use_log, "0†", sprintf("%.3g", meds))
  xlabs <- setNames(sprintf("%s\nmed %s", names(meds), med_lab), names(meds))
  th <- theme_paper(base_size = 8) +
    theme(plot.title = element_text(size = 7.4, hjust = 0.5, face = "plain",
                                    margin = margin(b = 2)),
          axis.text.x = element_text(size = 6.2, lineheight = 0.9),
          axis.text.y = element_text(size = 5.8),
          panel.grid.major.x = element_blank())

  base <- function(dd, ddc, lo = NULL) {
    if (!is.null(lo)) { dd$v <- pmax(dd$v, lo); ddc$v <- pmax(ddc$v, lo)
                        ddc$q25 <- pmax(ddc$q25, lo); ddc$q75 <- pmax(ddc$q75, lo) }
    p <- ggplot(dd, aes(x = side, y = v, fill = side)) +
      geom_violin(scale = "width", width = 0.72, linewidth = PAPER_VIOLIN_LW,
                  colour = "black", adjust = ADJ, trim = TRUE, alpha = 0.75) +
      inner_v1()
    if (!DCPERF_VIOLIN) {
      # single-workload marker: window IQR bar + the vote as a filled diamond
      p <- p +
        geom_linerange(data = ddc, aes(x = "DCPerf", ymin = q25, ymax = q75),
                       inherit.aes = FALSE, linewidth = 0.55, colour = "grey25") +
        geom_point(data = ddc, aes(x = "DCPerf", y = v), inherit.aes = FALSE,
                   shape = 23, size = 2.3, fill = PAPER_THREE[["DCPerf"]],
                   colour = "black", stroke = 0.45)
    }
    p + scale_fill_manual(values = PAPER_THREE, guide = "none",
                          limits = c("SPEC", "Agentic", "DCPerf")) +
      scale_x_discrete(limits = SIDES, labels = xlabs, expand = expansion(add = 0.6),
                       drop = FALSE) +
      labs(x = NULL, y = NULL) + th
  }

  if (use_log) {
    pos <- pooled[pooled > 0]
    lo <- 10^floor(log10(max(min(pos), 1e-2)))
    hi <- 10^ceiling(log10(max(pooled)))
    return(base(dm, dcm, lo) + ggtitle(m) +
      scale_y_log10(limits = c(lo, hi), breaks = 10^seq(log10(lo), log10(hi)),
                    labels = label_number(drop0trailing = TRUE), expand = expansion(0, 0)))
  }
  if (is_pct) return(base(dm, dcm) + ggtitle(m) + paper_scale_y(0, 100, 25))
  if (!qual) {
    br <- pretty(c(0, max(pooled) * 1.03), 5)
    return(base(dm, dcm) + ggtitle(m) + paper_scale_y(0, max(br), br[2] - br[1]))
  }
  thr <- 3 * quantile(pooled, .95)
  body_max <- max(pooled[pooled <= thr]); out_min <- min(pooled[pooled > thr])
  brk <- pretty(c(0, body_max * 1.12), 5); brk_lo <- max(brk)
  ub <- pretty(c(out_min, max(pooled) * 1.02), 2)
  step <- if (length(ub) > 1) ub[2] - ub[1] else out_min * 0.1
  up_lo <- floor(out_min / step) * step
  if (up_lo <= brk_lo) up_lo <- signif(out_min * 0.95, 2)
  up_hi <- max(ub)
  stopifnot(up_lo <= out_min, up_lo > brk_lo, brk_lo >= body_max)
  lower <- base(dm, dcm) +
    scale_y_continuous(limits = c(0, brk_lo), breaks = brk, expand = expansion(0, 0),
                       oob = scales::oob_squish) +
    annotate("text", x = 0.47, y = brk_lo * 0.985, label = "∕∕", size = 2.3,
             hjust = 0.5, family = PAPER_SERIF, fontface = "bold") +
    theme(plot.margin = margin(0.6, 8, 6, 6))
  up_pts <- bind_rows(
    dm |> filter(v > thr) |> transmute(side, v),
    dcm |> filter(v > thr) |> transmute(side = "DCPerf", v))
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

legend_strip <- function() {
  tx <- function(xx, lab, size = 2.5) annotate("text", x = xx, y = 0.5, label = lab,
                                               hjust = 0, size = size, family = PAPER_SERIF)
  dcl <- sprintf("DCPerf %s (1 workload)", paste(DC_BENCHES, collapse = "+"))
  g <- ggplot() + xlim(0, 1) + ylim(0, 1) + theme_void() +
    theme(plot.margin = margin(2, 10, 4, 10)) +
    annotate("rect", xmin = 0.045, xmax = 0.067, ymin = 0.28, ymax = 0.72,
             fill = PAPER_THREE[["SPEC"]], colour = "black", linewidth = 0.3) +
    tx(0.077, "SPEC (26 benchmarks)") +
    annotate("rect", xmin = 0.212, xmax = 0.234, ymin = 0.28, ymax = 0.72,
             fill = PAPER_THREE[["Agentic"]], colour = "black", linewidth = 0.3) +
    tx(0.244, "Agentic (36 tasks)") +
    annotate("point", x = 0.372, y = 0.5, shape = 23, size = 2.3,
             fill = PAPER_THREE[["DCPerf"]], colour = "black", stroke = 0.45) +
    tx(0.386, dcl) +
    annotate("segment", x = 0.606, xend = 0.636, y = 0.5, yend = 0.5,
             colour = "black", linewidth = 1.0) +
    tx(0.646, "median") +
    annotate("point", x = 0.716, y = 0.5, shape = 23, size = 2.1, fill = "white",
             colour = "black", stroke = 0.45) +
    tx(0.731, "mean") +
    annotate("segment", x = 0.800, xend = 0.800, y = 0.25, yend = 0.75,
             colour = "grey25", linewidth = 0.55) +
    tx(0.812, "DCPerf window IQR (within-workload)", 2.2)
  g
}

ps <- lapply(METRICS, panel)
grid <- wrap_plots(ps, ncol = 4)
fig <- (legend_strip() / grid) + plot_layout(heights = c(0.04, 1))
paper_save(fig, file.path(OUT, paste0("dcperf_agg_compact3", suffix)),
           width = 11.4, height = 8.3)
