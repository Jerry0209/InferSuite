#!/usr/bin/env Rscript
# fig05_agg_system_server — COPY of the canonical generator local_agents/kit/plot/plot_paper_agg_groups_server.R
# (single source of truth; edit THERE). Runs from the repo root against the banked
# data trees and writes into local_agents/JVMbench/plots/paper_v1/.
# plot_paper_agg_groups_server.R -- the per-window group pictures with the mentor's SERVER set
# aggregated into ONE column (2026-09-14): columns are SPEC-int, SPEC-fp, Server, then the 36
# agentic tasks grouped by language. Server = Renaissance finagle-http, finagle-chirper,
# page-rank, naive-bayes, neo4j-analytics + DaCapo Chopin cassandra, tomcat, kafka.
#
# What a column is:
#   SPEC-int / SPEC-fp   one value per BENCHMARK: 14 and 12. VOTE=runtime (default, mentor's rule
#                        2026-09-15) = the metric over the benchmark's whole runtime (counters
#                        summed over all windows, ratio once; runtime_votes.csv); VOTE=median =
#                        the median of its windows (the rule before 2026-09-15)
#   Server               SERVER_MODE=votes (default): one value per benchmark, 10 (DCPerf 2 +
#                        Renaissance 5 + DaCapo 3), the same statistic as the SPEC columns and
#                        as the compact grid's violin; SERVER_MODE=windows: every 100 ms window
#                        of the 10 benchmarks pooled (equal capture lengths, equal weight each)
#   each agentic task    every 100 ms window of that task (~115-2 270 per metric)
# So the three reference columns are distributions over benchmarks and the agentic columns are
# distributions over windows -- the asymmetry the pack README states.
#
# Groups (one figure each): ipc | frontend | memory | system. Inputs: agg_rows_long.csv (SPEC +
# agentic) and EXT_ROWS (the Server suites' rows_long files). Outputs multi_server_<group>.
suppressPackageStartupMessages({
  library(ggplot2); library(dplyr); library(tidyr); library(ragg); library(scales)
  library(patchwork)
})
repo <- path.expand("~/InferSuite")
source(file.path(repo, "local_agents/kit/plot/theme_paper.R"))
OUT <- file.path(repo, Sys.getenv("EXT_OUT", "local_agents/JVMbench/plots/paper_v1"))
dir.create(OUT, showWarnings = FALSE, recursive = TRUE)
SERVER_MODE <- Sys.getenv("SERVER_MODE", "votes")
stopifnot(SERVER_MODE %in% c("votes", "windows"))
VOTE <- Sys.getenv("VOTE", "runtime")
stopifnot(VOTE %in% c("runtime", "median"))
SUFFIX <- paste0(if (SERVER_MODE == "windows") "_windows" else "", if (VOTE == "median") "_medianvote" else "")
RV_FILE <- file.path(repo, Sys.getenv("RUNTIME_VOTES", "local_agents/JVMbench/data/l3_study/runtime_votes.csv"))

d <- read.csv(file.path(repo, "local_agents/ML_iso36/data/l3_study/agg_rows_long.csv"),
              stringsAsFactors = FALSE) |> filter(fence == "both", grp != "Python")
EXT_FILES <- strsplit(Sys.getenv("EXT_ROWS",
  paste(file.path(repo, "local_agents/DCPerf/data/l3_study/dcperf_rows_long.csv"),
        file.path(repo, "local_agents/JVMbench/data/l3_study/renaissance_rows_long.csv"),
        file.path(repo, "local_agents/JVMbench/data/l3_study/dacapo_rows_long.csv"), sep = ":")),
  ":")[[1]]
EXT_FILES <- EXT_FILES[file.exists(EXT_FILES)]
stopifnot(length(EXT_FILES) > 0)
srv <- bind_rows(lapply(EXT_FILES, read.csv, stringsAsFactors = FALSE)) |> filter(fence == "both")
SERVER_BENCHES <- sort(unique(srv$col))
if (VOTE == "runtime") {
  rv <- read.csv(RV_FILE, stringsAsFactors = FALSE)
  # the reference columns take the whole-runtime value per benchmark; SPEC rows of the
  # medians file are replaced, the agentic per-window rows stay
  d <- d |> filter(!grp %in% c("SPEC-int", "SPEC-fp"))
  spec_rows <- rv |> filter(family == "spec26") |>
    transmute(fence = "both", metric, grp = subgroup, col = subgroup, value)
  srv_rows <- if (SERVER_MODE == "votes") {
    rv |> filter(family %in% c("dcperf", "renaissance", "dacapo")) |>
      transmute(fence = "both", metric, grp = "Server", col = "Server", value)
  } else {
    srv |> transmute(fence = "both", metric, grp = "Server", col = "Server", value)
  }
  d <- bind_rows(spec_rows, d, srv_rows)
} else {
  srv_rows <- if (SERVER_MODE == "votes") {
    srv |> group_by(metric, col) |> summarise(value = median(value), .groups = "drop") |>
      transmute(fence = "both", metric, grp = "Server", col = "Server", value)
  } else {
    srv |> transmute(fence = "both", metric, grp = "Server", col = "Server", value)
  }
  d <- bind_rows(d, srv_rows)
}

langs <- c("C", "C++", "Rust", "Go", "Java", "PHP", "Ruby", "JavaScript", "TypeScript")
lcol <- c("SPEC-int" = "#4d4d4d", "SPEC-fp" = "#b3b3b3", "Server" = "#1a9850",
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

# column order: SPEC-int, SPEC-fp, Server, then each language's tasks
ord <- c("SPEC-int", "SPEC-fp", "Server")
grp_of <- c("SPEC-int" = "SPEC-int", "SPEC-fp" = "SPEC-fp", "Server" = "Server")
lang_span <- list()
for (lg in langs) {
  cols <- unique(d$col[d$grp == lg])
  lang_span[[lg]] <- c(length(ord) + 1, length(ord) + length(cols))
  ord <- c(ord, cols)
  for (cc in cols) grp_of[cc] <- lg
}
d$col_f <- factor(d$col, levels = ord)
d$fillg <- grp_of[d$col]
SEP_SPEC <- 2.5                                      # SPEC | Server
SEP_SRV  <- 3.5                                      # Server | agentic
SEP_LANG <- sapply(lang_span, function(s) s[2] + 0.5)
SEP_LANG <- SEP_LANG[-length(SEP_LANG)]

med_tab <- d |> group_by(metric, col_f, fillg) |>
  summarise(med = median(value), mean = mean(value), n = n(), .groups = "drop")
write.csv(med_tab |> rename(column = col_f, language = fillg),
          file.path(OUT, sprintf("multi_server%s_numbers.csv", SUFFIX)), row.names = FALSE)

panel <- function(m, show_x) {
  dm <- d |> filter(metric == m)
  use_log <- m %in% logm
  TRIM <- c("BTB MPKI (BAClears)", "L1D-load MPKI", "L2-load MPKI", "LLC MPKI")
  p97 <- dm |> group_by(col_f) |> summarise(q97 = quantile(value, .97),
                                            q95 = quantile(value, .95), .groups = "drop")
  cap <- if (m %in% TRIM) quantile(p97$q95, .85) * 1.2 else max(p97$q97) * 1.15
  if (grepl("\\(%\\)", m)) cap <- min(cap, 100)
  p <- ggplot(dm, aes(x = col_f, y = value, fill = fillg)) +
    paper_band(0.4, SEP_SPEC) +
    paper_band(SEP_SPEC, SEP_SRV) +
    geom_violin(scale = "width", width = 0.85, linewidth = PAPER_VIOLIN_LW,
                colour = "black", adjust = 1.2, trim = TRUE, alpha = 0.75) +
    paper_inner_box(width = 0.3, lw = 0.25, diamond = 1.1) +
    paper_agg_sep(c(SEP_SPEC, SEP_SRV)) + paper_lang_sep(SEP_LANG) +
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
             size = 2.0, fontface = "bold", colour = "#4d4d4d", family = PAPER_SERIF) +
    annotate("text", x = 3, y = Inf, vjust = -0.7, label = "Server",
             size = 2.0, fontface = "bold", colour = lcol[["Server"]], family = PAPER_SERIF)
  for (lg in langs) {
    p <- p + annotate("text", x = mean(lang_span[[lg]]), y = Inf, vjust = -0.7,
                      label = lg, size = 2.0, fontface = "bold", colour = lcol[[lg]],
                      family = PAPER_SERIF)
  }
  p + theme(plot.margin = margin(14, 8, 6, 6))
}

for (gname in names(GROUPS)) {
  ms <- GROUPS[[gname]]
  ps <- lapply(seq_along(ms), function(k) panel(ms[k], show_x = (k == length(ms))))
  ps[[1]] <- add_headers(ps[[1]])
  h <- 2.45 * length(ms) + 0.9
  fig <- wrap_plots(ps, ncol = 1)
  paper_save(fig, file.path(OUT, sprintf("multi_server_%s%s", gname, SUFFIX)), width = 14, height = h)
}
cat("Server set:", paste(SERVER_BENCHES, collapse = ", "), "\n")
