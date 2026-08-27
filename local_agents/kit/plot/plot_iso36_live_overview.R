#!/usr/bin/env Rscript
# plot_iso36_live_overview.R -- house-style (ggplot2) rendering of the 4-panel live
# overview over the 36 count-view picks.
#
# Inputs : local_agents/ML_iso36/plots/iso36_live_overview_numbers.csv
#          (language, task, working_pct, stall_pct, tool_pct, harness_pct, n_calls,
#           med_dur_s; final row = AVG, the unweighted per-task mean; panel-d AVG is
#           the mean of the per-task medians)
# Outputs: local_agents/ML_iso36/plots/iso36_live_overview_gg.{png,pdf}
#          local_agents/ML_iso36/plots/iso36_live_overview_gg_numbers.csv
suppressPackageStartupMessages({
  library(ggplot2); library(hrbrthemes); library(dplyr); library(tidyr)
  library(yaml); library(ragg); library(scales); library(patchwork)
})
repo <- path.expand("~/InferSuite")
source(file.path(repo, "local_agents/kit/plot/iso36_style.R"))

d <- read.csv(file.path(repo, "local_agents/ML_iso36/plots/iso36_live_overview_numbers.csv"),
              stringsAsFactors = FALSE)
write.csv(d, file.path(repo, "local_agents/ML_iso36/plots/iso36_live_overview_gg_numbers.csv"),
          row.names = FALSE)

langs <- c("C", "C++", "Rust", "Go", "Java", "PHP", "Ruby", "JavaScript", "TypeScript")
# y order: language groups top-to-bottom with a spacer row between groups, AVG last.
lv <- c()
for (lg in langs) {
  lv <- c(lv, paste0(".hd_", lg), d$task[d$language == lg])
}
lv <- c(lv, ".hd_", "AVG")
d$task_f <- factor(d$task, levels = rev(lv))
d$is_avg <- d$language == "AVG"

# header rows carry the language name on the y axis (bold via fontface vector below)
lab_task <- function(x) ifelse(x == ".hd_", "",
                        ifelse(grepl("^\\.hd_", x), sub("^\\.hd_", "", x), x))
face_task <- ifelse(grepl("^\\.hd_", rev(lv)) | rev(lv) == "AVG", "bold", "plain")

y_scale <- scale_y_discrete(labels = lab_task, drop = FALSE)
base_th <- theme_house(base_size = 8, axis_title_size = 9) +
  theme(panel.grid.major.y = element_blank(),
        axis.text.y = element_text(size = 5.6, face = face_task),
        plot.title = element_text(size = 9, hjust = 0.5),
        # black bounding box per chart (mentor 2026-08-28): makes each chart's extent
        # unambiguous and gives panel (d) its x=0 edge
        panel.border = element_rect(colour = "black", fill = NA, linewidth = 0.55),
        plot.margin = margin(2, 8, 2, 6))

stacked_panel <- function(v1, v2, n1, n2, title) {
  dd <- d |>
    transmute(task_f, is_avg, !!n1 := .data[[v1]], !!n2 := .data[[v2]]) |>
    pivot_longer(-c(task_f, is_avg), names_to = "part", values_to = "pct") |>
    mutate(part = factor(part, levels = c(n1, n2)))
  ggplot(dd, aes(x = pct, y = task_f, fill = part)) +
    geom_col(width = 0.8, colour = "grey30", linewidth = 0.1,
             position = position_stack(reverse = TRUE)) +
    geom_col(data = dd |> filter(is_avg), width = 0.8, colour = "black",
             linewidth = 0.5, fill = NA) +
    geom_text(data = dd |> filter(pct >= 8),
              aes(label = sprintf("%.0f", pct)),
              position = position_stack(vjust = 0.5, reverse = TRUE), size = 1.9,
              colour = ifelse((dd |> filter(pct >= 8))$part == n1, "white", "grey20")) +
    house_fill_scale(breaks = c(n1, n2)) +
    scale_x_continuous(limits = c(0, 100.001), breaks = seq(0, 100, 25),
                       expand = expansion(mult = c(0, 0.02))) +
    y_scale + labs(title = title, x = "%", y = NULL) + base_th
}

plain_panel <- function(v, title, xlab, fmt) {
  dd <- d
  m <- max(dd[[v]])
  ggplot(dd, aes(x = .data[[v]], y = task_f)) +
    geom_col(width = 0.8, colour = "grey30", linewidth = 0.1, fill = house_fill[["count"]]) +
    geom_col(data = dd |> filter(is_avg), width = 0.8, colour = "black",
             linewidth = 0.5, fill = NA) +
    geom_text(aes(label = fmt(.data[[v]])), hjust = -0.15, size = 1.9, colour = "grey20") +
    scale_x_continuous(limits = c(0, m * 1.24), expand = expansion(mult = c(0, 0.02))) +
    y_scale + labs(title = title, x = xlab, y = NULL) + base_th
}

pa <- stacked_panel("working_pct", "stall_pct",
                    "CPU working", "CPU stall (incl. model wait)",
                    "(a) CPU working vs. stall")
pb <- stacked_panel("tool_pct", "harness_pct", "Tool", "Harness",
                    "(b) Tool vs. harness (core-s split)")
pc <- plain_panel("n_calls", "(c) # tool calls", "calls",
                  function(v) sprintf("%.0f", v))
pd <- plain_panel("med_dur_s", "(d) median call duration", "seconds",
                  function(v) sprintf("%.2f", v))
for (p in list()) invisible(p)
pb <- pb + theme(axis.text.y = element_blank())
pc <- pc + theme(axis.text.y = element_blank())
pd <- pd + theme(axis.text.y = element_blank())

fig <- (pa | pb | pc | pd) +
  plot_layout(guides = "collect") &
  theme(legend.position = "bottom", legend.text = element_text(size = 6.5),
        legend.key.size = unit(3.2, "mm"))
fig <- fig + plot_annotation(
  caption = paste("(c) every trajectory action incl. failed/errored calls and the final submit;",
                  "model-only turns not counted. (d) AVG = mean of per-task medians.",
                  "AVG bars (black outline) = unweighted per-task means. Live census episodes."),
  theme = theme(plot.caption = element_text(size = 5.2, colour = "grey40", hjust = 0.5)))

house_save(fig, file.path(repo, "local_agents/ML_iso36/plots/iso36_live_overview_gg"),
           width = 10.5, height = 7.5)
