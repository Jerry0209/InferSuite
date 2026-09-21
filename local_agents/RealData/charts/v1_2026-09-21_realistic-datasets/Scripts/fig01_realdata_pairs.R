#!/usr/bin/env Rscript
# fig01_realdata_pairs — COPY of the canonical generator local_agents/kit/plot/plot_paper_realdata_pairs.R
# (single source of truth; edit THERE). Runs from the repo root against the banked data trees.
# plot_paper_realdata_pairs.R -- does the DATASET change the characterisation? One panel per
# metric; in each, the five re-characterised server workloads as PAIRS: the suite benchmark's
# value (open circle) and the realistic-dataset value (filled circle) joined by a segment, with
# the SPEC (26) and Agentic (36) medians as reference lines. Values are whole-runtime per
# workload (runtime_votes.csv, mentor's rule 2026-09-15).
#
# Pairs (toy -> realistic), 2026-09-21:
#   neo4j-analytics (70 MB movie graph)      -> neo4j-livejournal (69 M-edge social graph server)
#   cassandra (DaCapo, 10 k rows)            -> cassandra-ycsb20m (20 M rows, client outside)
#   kafka (DaCapo, 1 M-message bursts)       -> kafka-20g (21 GB retention window, sustained)
#   page-rank (7.6 M-edge crawl)             -> pagerank-livejournal (69 M edges)
#   naive-bayes (100-row sample x 8000)      -> naivebayes-rcv1 (518 k documents)
#   video_transcode (2 s 1080p shots)        -> video-4k (Netflix 4K sequences)   [when profiled]
suppressPackageStartupMessages({ library(ggplot2); library(dplyr); library(ragg); library(scales); library(patchwork) })
repo <- path.expand("~/InferSuite")
source(file.path(repo, "local_agents/kit/plot/theme_paper.R"))
OUT <- file.path(repo, Sys.getenv("EXT_OUT", "local_agents/RealData/plots/paper_v1")); dir.create(OUT, showWarnings = FALSE, recursive = TRUE)
rv <- read.csv(file.path(repo, Sys.getenv("RUNTIME_VOTES", "local_agents/JVMbench/data/l3_study/runtime_votes.csv")), stringsAsFactors = FALSE)

PAIRS <- data.frame(
  label = c("Neo4j", "Cassandra", "Kafka", "PageRank", "Naive Bayes", "Video"),
  toy   = c("neo4j-analytics", "cassandra", "kafka", "page-rank", "naive-bayes", "video_transcode"),
  real  = c("neo4j-livejournal", "cassandra-ycsb20m", "kafka-20g", "pagerank-livejournal", "naivebayes-rcv1", "video-4k"),
  stringsAsFactors = FALSE)
PAIRS <- PAIRS[PAIRS$real %in% rv$workload & PAIRS$toy %in% rv$workload, ]
stopifnot(nrow(PAIRS) > 0)
METRICS <- c("IPC", "Branch MPKI", "Branch-direction MPKI", "BTB MPKI (BAClears)",
             "L1I MPKI (code-read)", "uop-cache (DSB) MPKI", "DSB coverage (%)",
             "L1D-load MPKI", "L2-load MPKI", "LLC MPKI", "DRAM read (GB/s)", "Context switches (/CPU-s)")
logm <- c("Context switches (/CPU-s)")
val <- function(w, m) { x <- rv$value[rv$workload == w & rv$metric == m]; if (length(x)) x[1] else NA_real_ }
d <- bind_rows(lapply(seq_len(nrow(PAIRS)), function(i) bind_rows(lapply(METRICS, function(m)
  data.frame(label = PAIRS$label[i], metric = m, toy = val(PAIRS$toy[i], m), real = val(PAIRS$real[i], m))))))
ref <- bind_rows(lapply(METRICS, function(m) data.frame(metric = m,
  spec = median(rv$value[rv$family == "spec26" & rv$metric == m]),
  agentic = median(rv$value[rv$family == "agentic36" & rv$metric == m]))))
d$label <- factor(d$label, levels = PAIRS$label)
write.csv(d |> left_join(ref, by = "metric") |> mutate(ratio = real / toy), file.path(OUT, "realdata_pairs_numbers.csv"), row.names = FALSE)

COL_TOY <- "white"; COL_REAL <- "#1a9850"
panel <- function(m) {
  dm <- d |> filter(metric == m); rm <- ref |> filter(metric == m)
  use_log <- m %in% logm; is_pct <- grepl("\\(%\\)", m)
  lo_all <- c(dm$toy, dm$real, rm$spec, rm$agentic)
  p <- ggplot(dm, aes(y = label)) +
    geom_hline(yintercept = seq_len(nrow(PAIRS)), colour = PAPER_GRID, linewidth = 0.25) +
    geom_vline(aes(xintercept = spec), data = rm, colour = PAPER_PAIR[["blue_dark"]], linewidth = 0.5, linetype = "22") +
    geom_vline(aes(xintercept = agentic), data = rm, colour = PAPER_PAIR[["red_dark"]], linewidth = 0.5, linetype = "22") +
    geom_segment(aes(x = toy, xend = real, yend = label), colour = "grey35", linewidth = 0.6,
                 arrow = arrow(length = unit(0.10, "cm"), type = "closed")) +
    geom_point(aes(x = toy), shape = 21, size = 2.0, fill = COL_TOY, colour = "black", stroke = 0.45) +
    geom_point(aes(x = real), shape = 21, size = 2.0, fill = COL_REAL, colour = "black", stroke = 0.45) +
    scale_y_discrete(limits = rev(levels(d$label))) +
    labs(x = NULL, y = NULL) + ggtitle(m) +
    theme_paper(base_size = 8) +
    theme(plot.title = element_text(size = 7.4, hjust = 0.5, face = "plain", margin = margin(b = 2)),
          axis.text.y = element_text(size = 6), axis.text.x = element_text(size = 5.8),
          panel.grid.major.y = element_blank())
  if (use_log) {
    lo <- 10^floor(log10(max(min(lo_all[lo_all > 0]), 1e-2))); hi <- 10^ceiling(log10(max(lo_all)))
    p <- p + scale_x_log10(limits = c(lo, hi), breaks = 10^seq(log10(lo), log10(hi)), labels = label_number(drop0trailing = TRUE))
  } else if (is_pct) {
    p <- p + scale_x_continuous(limits = c(0, 100), breaks = seq(0, 100, 25))
  } else {
    br <- pretty(c(0, max(lo_all, na.rm = TRUE) * 1.05), 5)
    p <- p + scale_x_continuous(limits = c(0, max(br)), breaks = br)
  }
  p
}
# Legend, laid out over TWO centred rows. One row overflowed the panel (2026-09-21: the five
# entries measured 1.03 of the available 1.0, so the centred row started at x = -0.016 and the
# first marker -- the white "suite benchmark" circle -- was clipped away entirely). Rows are
# centred independently and each is checked against the panel width.
legend_rows <- function(rows) {
  cw <- 0.0052; gap <- 0.028
  g <- ggplot() + xlim(0, 1) + ylim(0, 1) + theme_void() + theme(plot.margin = margin(2, 8, 2, 8))
  for (r in seq_along(rows)) {
    items <- rows[[r]]
    y <- 1 - (r - 0.5) / length(rows)
    widths <- sapply(items, function(it) (if (it$kind == "none") 0 else 0.035) + nchar(it$lab) * cw)
    total <- sum(widths) + gap * (length(items) - 1)
    stopifnot(total <= 1)                       # never silently clip a legend entry again
    x <- (1 - total) / 2
    for (i in seq_along(items)) {
      it <- items[[i]]
      if (it$kind == "pt")
        g <- g + annotate("point", x = x + 0.012, y = y, shape = 21, size = 2.2, fill = it$col,
                          colour = "black", stroke = 0.45)
      if (it$kind == "ln")
        g <- g + annotate("segment", x = x, xend = x + 0.024, y = y, yend = y, colour = it$col,
                          linewidth = 0.6, linetype = "22")
      if (it$kind == "arrow")
        g <- g + annotate("segment", x = x, xend = x + 0.024, y = y, yend = y, colour = "grey35",
                          linewidth = 0.6, arrow = arrow(length = unit(0.08, "cm"), type = "closed"))
      g <- g + annotate("text", x = x + (if (it$kind == "none") 0 else 0.033), y = y, label = it$lab,
                        hjust = 0, size = 2.35, family = PAPER_SERIF,
                        fontface = if (it$kind == "none") "italic" else "plain")
      x <- x + widths[i] + gap
    }
  }
  g
}
legend_strip <- function() legend_rows(list(
  list(list(kind = "pt", col = COL_TOY, lab = "suite benchmark, as shipped"),
       list(kind = "pt", col = COL_REAL, lab = "same software, realistic dataset"),
       list(kind = "arrow", col = NA, lab = "the move (connector, not a range)")),
  list(list(kind = "ln", col = PAPER_PAIR[["blue_dark"]], lab = "median of the 26 SPEC workloads"),
       list(kind = "ln", col = PAPER_PAIR[["red_dark"]], lab = "median of the 36 agentic tasks"),
       list(kind = "none", col = NA, lab = "every point = that workload's metric over its whole runtime"))))

fig <- (legend_strip() / wrap_plots(lapply(METRICS, panel), ncol = 4)) + plot_layout(heights = c(0.075, 1))
paper_save(fig, file.path(OUT, "realdata_pairs"), width = 10.4, height = 7.8)
