#!/usr/bin/env Rscript
# fig01_agg_compact_server — COPY of the canonical generator local_agents/kit/plot/plot_paper_agg_compact_server.R
# (single source of truth; edit THERE). Runs from the repo root against the banked
# data trees and writes into local_agents/JVMbench/plots/paper_v1/.
# plot_paper_agg_compact_server.R -- the 12-panel grid with THREE violins per panel:
#   SPEC     26 SPEC CPU 2026 benchmarks
#   Server   the mentor's JVM server set (2026-09-14): Renaissance finagle-http, finagle-chirper
#            (web), page-rank, naive-bayes (Spark), neo4j-analytics (database); DaCapo Chopin
#            cassandra, tomcat, kafka  -- 8 benchmarks
#   Agentic  the 36 SWE-bench Multilingual tasks
#
# Unit rule: a violin is a distribution over WORKLOADS, one value per workload. n = 26 / 10 / 36.
# VOTE=runtime (default, mentor's rule 2026-09-15): the value is the metric computed over the
#   workload's WHOLE RUNTIME -- raw counters summed over every window, ratio taken once (IPC =
#   total instructions / total cycles, ...), read from runtime_votes.csv
#   (export_runtime_votes.py, one implementation for all four families).
# VOTE=median: the value is the median of the workload's per-window values (the rule before
#   2026-09-15, kept for comparison).
# SERVER_MODE=windows draws the Server violin over every 100 ms window of the server benchmarks
#   instead (fixed-length captures, ~1 500 windows per metric each, so pooling is equal-weighted).
# Server set = DCPerf FeedSim + VideoTranscodeBench, Renaissance finagle-http, finagle-chirper,
# page-rank, naive-bayes, neo4j-analytics, DaCapo Chopin cassandra, tomcat, kafka (10; the mentor
# confirmed DCPerf belongs in it, 2026-09-15). EXT_ROWS = their <suite>_rows_long.csv files.
suppressPackageStartupMessages({
  library(ggplot2); library(dplyr); library(ragg); library(scales); library(patchwork)
})
repo <- path.expand("~/InferSuite")
source(file.path(repo, "local_agents/kit/plot/theme_paper.R"))
ADJ <- as.numeric(Sys.getenv("ADJ", "1.0"))
SERVER_MODE <- Sys.getenv("SERVER_MODE", "votes")
stopifnot(SERVER_MODE %in% c("votes", "windows"))
VOTE <- Sys.getenv("VOTE", "runtime")
stopifnot(VOTE %in% c("runtime", "median"))
RV_FILE <- file.path(repo, Sys.getenv("RUNTIME_VOTES", "local_agents/JVMbench/data/l3_study/runtime_votes.csv"))
EXT_FILES <- strsplit(Sys.getenv("EXT_ROWS",
  paste(file.path(repo, "local_agents/DCPerf/data/l3_study/dcperf_rows_long.csv"),
        file.path(repo, "local_agents/JVMbench/data/l3_study/renaissance_rows_long.csv"),
        file.path(repo, "local_agents/JVMbench/data/l3_study/dacapo_rows_long.csv"), sep = ":")),
  ":")[[1]]
EXT_FILES <- EXT_FILES[file.exists(EXT_FILES)]
stopifnot(length(EXT_FILES) > 0)
OUT <- file.path(repo, Sys.getenv("EXT_OUT", "local_agents/JVMbench/plots/paper_v1"))
dir.create(OUT, showWarnings = FALSE, recursive = TRUE)
STEM <- Sys.getenv("EXT_STEM", paste0("multi_server_compact",
                                      if (SERVER_MODE == "windows") "_windows" else "",
                                      if (VOTE == "median") "_medianvote" else ""))

SIDES <- c("SPEC", "Server", "Agentic")
COLS <- c(SPEC = unname(PAPER_PAIR["blue_dark"]), Server = "#1a9850",
          Agentic = unname(PAPER_PAIR["red_dark"]))
langs <- c("C", "C++", "Rust", "Go", "Java", "PHP", "Ruby", "JavaScript", "TypeScript")
METRICS <- c("IPC",
             "Branch MPKI", "Branch-direction MPKI", "BTB MPKI (BAClears)",
             "L1I MPKI (code-read)", "uop-cache (DSB) MPKI", "DSB coverage (%)",
             "L1D-load MPKI", "L2-load MPKI", "LLC MPKI", "DRAM read (GB/s)",
             "Context switches (/CPU-s)")
logm <- "Context switches (/CPU-s)"

d <- read.csv(file.path(repo, "local_agents/ML_iso36/data/l3_study/agg_rows_long.csv"),
              stringsAsFactors = FALSE) |> filter(fence == "both")
srv <- bind_rows(lapply(EXT_FILES, read.csv, stringsAsFactors = FALSE)) |> filter(fence == "both")
# within-workload spread of each server benchmark (its window IQR) -- reported in the numbers
srv_iqr <- srv |> group_by(metric, wl = col, suite = grp) |>
  summarise(q25 = quantile(value, .25), q75 = quantile(value, .75), nwin = n(), .groups = "drop")
if (VOTE == "runtime") {
  rv <- read.csv(RV_FILE, stringsAsFactors = FALSE)
  side_of <- c(spec26 = "SPEC", agentic36 = "Agentic", dcperf = "Server",
               renaissance = "Server", dacapo = "Server")
  votes <- rv |> transmute(metric, wl = workload, v = value, side = unname(side_of[family])) |>
    filter(!is.na(side))
  srv_votes <- votes |> filter(side == "Server") |> select(metric, wl, v) |>
    inner_join(srv_iqr, by = c("metric", "wl"))
  server_pts <- if (SERVER_MODE == "votes") srv_votes |> transmute(metric, wl, v, side = "Server") else
    srv |> transmute(metric, wl = col, v = value, side = "Server")
  per_workload <- bind_rows(votes |> filter(side != "Server"), server_pts)
} else {
  srv_votes <- srv |> group_by(metric, wl = col) |> summarise(v = median(value), .groups = "drop") |>
    inner_join(srv_iqr, by = c("metric", "wl"))
  server_pts <- if (SERVER_MODE == "votes") srv_votes |> transmute(metric, wl, v, side = "Server") else
    srv |> transmute(metric, wl = col, v = value, side = "Server")
  per_workload <- bind_rows(
    d |> filter(grp %in% c("SPEC-int", "SPEC-fp")) |>
      group_by(metric, wl = paste(grp, ave(value, metric, grp, FUN = seq_along))) |>
      summarise(v = first(value), .groups = "drop") |> mutate(side = "SPEC"),
    d |> filter(grp %in% langs) |>
      group_by(metric, wl = col) |>
      summarise(v = median(value), .groups = "drop") |> mutate(side = "Agentic"),
    server_pts)
}
per_workload$side <- factor(per_workload$side, levels = SIDES)

# numbers: one summary row per (metric, side) + one row per server benchmark (its vote and
# window IQR), so the reader can see which benchmark sits where inside the Server violin
num <- bind_rows(
  per_workload |> group_by(metric, side) |>
    summarise(n = n(), min = min(v), max = max(v), median = median(v), mean = mean(v),
              sd = sd(v), .groups = "drop") |> mutate(side = as.character(side), workload = NA_character_),
  srv_votes |> transmute(metric, side = paste0("Server:", suite), workload = wl, n = nwin,
                         min = q25, max = q75, median = v, mean = v, sd = NA_real_))
write.csv(num, file.path(OUT, paste0(STEM, "_numbers.csv")), row.names = FALSE)

n_side <- sapply(SIDES, function(s) length(unique(per_workload$wl[per_workload$side == s & per_workload$metric == "IPC"])))

panel <- function(m) {
  dm <- per_workload |> filter(metric == m)
  use_log <- m %in% logm
  is_pct <- grepl("\\(%\\)", m)
  pooled <- dm$v
  vis_max <- max(pooled, na.rm = TRUE)
  qual <- !use_log && !is_pct && paper_break_qualifies(pooled)
  meds <- sapply(SIDES, function(s) median(dm$v[dm$side == s]))
  med_lab <- ifelse(meds == 0 & use_log, "0†", sprintf("%.3g", meds))
  xlabs <- setNames(sprintf("%s\nmed %s", SIDES, med_lab), SIDES)
  th <- theme_paper(base_size = 8) +
    theme(plot.title = element_text(size = 7.4, hjust = 0.5, face = "plain",
                                    margin = margin(b = 2)),
          axis.text.x = element_text(size = 5.6, lineheight = 0.9),
          axis.text.y = element_text(size = 5.8),
          panel.grid.major.x = element_blank())
  base <- function(dd, lo = NULL) {
    if (!is.null(lo)) dd$v <- pmax(dd$v, lo)
    ggplot(dd, aes(x = side, y = v, fill = side)) +
      geom_violin(scale = "width", width = 0.72, linewidth = PAPER_VIOLIN_LW,
                  colour = "black", adjust = ADJ, trim = TRUE, alpha = 0.75) +
      paper_inner_box(width = 0.08, lw = 0.28, diamond = 1.5) +
      scale_fill_manual(values = COLS, guide = "none", limits = SIDES) +
      scale_x_discrete(limits = SIDES, labels = xlabs, expand = expansion(add = 0.6),
                       drop = FALSE) +
      labs(x = NULL, y = NULL) + th
  }
  if (use_log) {
    pos <- pooled[pooled > 0]
    lo <- 10^floor(log10(max(min(pos), 1e-2)))
    hi <- 10^ceiling(log10(vis_max))
    return(base(dm, lo) + ggtitle(m) +
      scale_y_log10(limits = c(lo, hi), breaks = 10^seq(log10(lo), log10(hi)),
                    labels = label_number(drop0trailing = TRUE), expand = expansion(0, 0)))
  }
  if (is_pct) return(base(dm) + ggtitle(m) + paper_scale_y(0, 100, 25))
  if (!qual) {
    br <- pretty(c(0, vis_max * 1.03), 5)
    return(base(dm) + ggtitle(m) + paper_scale_y(0, max(br), br[2] - br[1]))
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
  lower <- base(dm) +
    scale_y_continuous(limits = c(0, brk_lo), breaks = brk, expand = expansion(0, 0),
                       oob = scales::oob_squish) +
    annotate("text", x = 0.47, y = brk_lo * 0.985, label = "∕∕", size = 2.3,
             hjust = 0.5, family = PAPER_SERIF, fontface = "bold") +
    theme(plot.margin = margin(0.6, 8, 6, 6))
  up_pts <- dm |> filter(v > thr) |> transmute(side = as.character(side), v)
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
  n_suite <- sapply(c("DCPerf", "Renaissance", "DaCapo"), function(f) sum(srv_iqr$suite[srv_iqr$metric == "IPC"] == f))
  srv_lab <- if (SERVER_MODE == "votes")
    sprintf("Server (%d: DCPerf %d · Renaissance %d · DaCapo %d)", n_side[["Server"]], n_suite[["DCPerf"]], n_suite[["Renaissance"]], n_suite[["DaCapo"]]) else
    sprintf("Server (%d benchmarks, every 100 ms window pooled)", length(unique(srv$col)))
  rule <- if (VOTE == "runtime") "one value per workload = metric over its whole runtime" else
    "one value per workload = median of its 100 ms windows"
  items <- list(list(kind = "rect", col = COLS[["SPEC"]], lab = sprintf("SPEC (%d)", n_side[["SPEC"]])),
                list(kind = "rect", col = COLS[["Server"]], lab = srv_lab),
                list(kind = "rect", col = COLS[["Agentic"]], lab = sprintf("Agentic (%d)", n_side[["Agentic"]])),
                list(kind = "bar", col = "black", lab = "median"),
                list(kind = "diamond", col = "white", lab = "mean"),
                list(kind = "none", col = NA, lab = rule))
  cw <- 0.0052; gap <- 0.028
  widths <- sapply(items, function(it) (if (it$kind == "none") 0.0 else 0.03) + nchar(it$lab) * cw)
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
    g <- g + annotate("text", x = x + (if (it$kind == "none") 0 else 0.028), y = 0.5, label = it$lab,
                      hjust = 0, size = 2.35, family = PAPER_SERIF,
                      fontface = if (it$kind == "none") "italic" else "plain")
    x <- x + widths[i] + gap
  }
  g
}

ps <- lapply(METRICS, panel)
grid <- wrap_plots(ps, ncol = 4)
fig <- (legend_strip() / grid) + plot_layout(heights = c(0.04, 1))
paper_save(fig, file.path(OUT, STEM), width = 10.4, height = 8.3)
