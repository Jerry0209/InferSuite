#!/usr/bin/env Rscript
# fig08_hero_ipc — COPY of the canonical generator local_agents/kit/plot/plot_paper_hero.R
# (single source of truth; edit THERE). Runs from the repo root against the
# banked data tree and writes into plots/paper_v2/.
# Regenerate: see charts/README.md.
# plot_paper_hero.R -- the one/two-violin HERO figure with the reference's stats strip
# (mentor 1d, 2026-09-01): violin + jitter + inner-statistics glyph on top, and BELOW the
# panel a strip with rows Min / Max / Median / Mean±Std, one column per violin, alternating
# faint row shading, built as a second ggplot sharing the x scale and aligned by patchwork.
# Floating numeric labels are dropped here -- the strip is the numbers.
#
# METRIC env picks the metric (default IPC). Data: merged agent fence, one vote/workload.
# Output: plots/paper_v2/iso36_hero_<slug>.{png,pdf}
suppressPackageStartupMessages({
  library(ggplot2); library(dplyr); library(ragg); library(scales); library(patchwork)
})
repo <- path.expand("~/InferSuite")
source(file.path(repo, "local_agents/kit/plot/theme_paper.R"))
OUT <- file.path(repo, "local_agents/ML_iso36/plots/paper_v2")
METRIC <- Sys.getenv("METRIC", "IPC")
slug <- gsub("[^a-z0-9]+", "_", tolower(METRIC))
slug <- gsub("^_|_$", "", sub("_+$", "", strsplit(slug, "_")[[1]][1]))

d <- read.csv(file.path(repo, "local_agents/ML_iso36/data/l3_study/agg_rows_long.csv"),
              stringsAsFactors = FALSE) |> filter(fence == "both")
langs <- c("C", "C++", "Rust", "Go", "Java", "PHP", "Ruby", "JavaScript", "TypeScript")
pw <- bind_rows(
  d |> filter(grp %in% c("SPEC-int", "SPEC-fp"), metric == METRIC) |>
    group_by(wl = paste(grp, ave(value, grp, FUN = seq_along))) |>
    summarise(v = first(value), .groups = "drop") |> mutate(side = "SPEC"),
  d |> filter(grp %in% langs, metric == METRIC) |>
    group_by(wl = col) |> summarise(v = median(value), .groups = "drop") |>
    mutate(side = "Agentic"))
pw$side <- factor(pw$side, levels = c("SPEC", "Agentic"))

st_tab <- pw |> group_by(side) |>
  summarise(Min = min(v), Max = max(v), Median = median(v),
            `Mean±Std` = NA, mean = mean(v), sd = sd(v), .groups = "drop")
rows <- c("Min", "Max", "Median", "Mean±Std")
strip_df <- bind_rows(lapply(rows, function(rw) {
  tibble::tibble(side = st_tab$side, row = rw,
                 label = if (rw == "Mean±Std")
                   sprintf("%.3g ± %.2g", st_tab$mean, st_tab$sd)
                 else sprintf("%.3g", st_tab[[rw]]))
}))
strip_df$row <- factor(strip_df$row, levels = rev(rows))
strip_df$shade <- as.integer(strip_df$row) %% 2 == 0

br <- pretty(c(0, max(pw$v) * 1.05), 5)
pv <- ggplot(pw, aes(x = side, y = v, fill = side)) +
  geom_violin(scale = "width", width = 0.66, linewidth = PAPER_VIOLIN_LW,
              colour = "black", adjust = 1.0, trim = TRUE, alpha = 0.65) +
  paper_jitter() +
  paper_inner_stats(scale = 1.1) +
  scale_fill_manual(values = PAPER_TWO, guide = "none") +
  paper_x_discrete() +
  paper_scale_y(0, max(br), br[2] - br[1]) +
  labs(x = NULL, y = METRIC) +
  theme_paper(base_size = 10) +
  theme(panel.grid.major.x = element_blank(),
        axis.text.x = element_text(size = 9.5))

strip <- ggplot(strip_df, aes(x = side, y = row)) +
  geom_tile(aes(fill = shade), width = Inf, height = 1, colour = NA) +
  geom_text(aes(label = label), size = 2.9, family = PAPER_SERIF) +
  scale_fill_manual(values = c(`TRUE` = "grey93", `FALSE` = "white"), guide = "none") +
  scale_x_discrete(expand = expansion(add = 0.6)) +
  scale_y_discrete(expand = expansion(0, 0)) +
  labs(x = NULL, y = NULL) +
  theme_paper(base_size = 10) +
  theme(panel.grid = element_blank(), axis.ticks = element_blank(),
        axis.text.x = element_blank(),
        axis.text.y = element_text(size = 7.4))

fig <- (pv / strip) + plot_layout(heights = c(3.1, 0.8)) + plot_annotation(
  title = sprintf("%s — SPEC vs Agentic", METRIC),
  subtitle = paste("one vote per workload, combined agent fence\nSPEC = 26 benchmarks (dark blue), Agentic = the 36 tasks (dark red); points = workloads",
                   paste0("\n", PAPER_STATS_SUBTITLE), sep = ""),
  caption = "100 ms windows, matched configuration · per-window MEDIAN per workload, fences' raw counts summed",
  theme = theme(plot.title = element_text(size = 11, face = "bold", family = PAPER_SERIF),
                plot.subtitle = element_text(size = 6.8, colour = "grey35", family = PAPER_SERIF),
                plot.caption = element_text(size = 6, colour = "grey45", family = PAPER_SERIF)))
paper_save(fig, file.path(OUT, paste0("iso36_hero_", slug)), width = 5.2, height = 5.9)
