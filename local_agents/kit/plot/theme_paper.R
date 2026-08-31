# theme_paper.R -- the ONE paper figure style (mentor spec 2026-08-31), ggplot2 side.
# Visual contract mirrors paper_style.py (anchors: Hermes MICRO'22 Fig 9/12, Constable
# ISCA'24 Fig 11/13): Libertine serif; full black panel border with the value axis ending
# EXACTLY on its outermost labeled break (paper_scale_*); dotted light-grey major grid
# behind the marks; outward tick marks visible outside the border; a thin black edge on
# every bar/violin/box; SPEC / AVG aggregate groups on a grey band behind everything
# (paper_band), closed by a solid black separator heavier than the dotted language
# separators (paper_lang_sep); top single-row legend with black-bordered keys.
# No chart may set these properties locally -- source this file and use the helpers.
suppressPackageStartupMessages({ library(ggplot2); library(scales) })

PAPER_SERIF <- "Linux Libertine O"
PAPER_GRID  <- "#cccccc"
PAPER_LSEP  <- "#666666"
PAPER_BAND  <- "#ebebeb"

theme_paper <- function(base_size = 10) {
  theme_minimal(base_size = base_size, base_family = PAPER_SERIF) +
    theme(
      panel.border      = element_rect(colour = "black", fill = NA, linewidth = 0.4),
      panel.grid.major  = element_line(colour = PAPER_GRID, linetype = "dotted",
                                       linewidth = 0.25),
      panel.grid.minor  = element_blank(),
      axis.ticks        = element_line(colour = "black", linewidth = 0.3),
      axis.ticks.length = unit(3, "pt"),
      axis.text         = element_text(size = base_size * 0.9, colour = "black"),
      axis.title        = element_text(size = base_size),
      legend.position   = "top",
      legend.direction  = "horizontal",
      legend.title      = element_blank(),
      legend.text       = element_text(size = base_size * 0.9),
      legend.key.size   = unit(0.4, "cm"),
      legend.margin     = margin(0, 0, 2, 0),
      plot.title        = element_text(size = base_size * 1.05, hjust = 0.5),
      strip.text        = element_text(size = base_size * 0.95),
      plot.margin       = margin(6, 8, 6, 6))
}

# value axis that terminates exactly at its outermost break (continuous axes only;
# categorical axes keep a small expansion so end bars don't fuse into the border)
paper_scale_y <- function(lo, hi, step, ...)
  scale_y_continuous(limits = c(lo, hi), breaks = seq(lo, hi, step),
                     expand = expansion(0, 0), ...)
paper_scale_x <- function(lo, hi, step, ...)
  scale_x_continuous(limits = c(lo, hi), breaks = seq(lo, hi, step),
                     expand = expansion(0, 0), ...)
paper_x_discrete <- function(...)
  scale_x_discrete(expand = expansion(add = 0.6), ...)

# grey band behind an aggregate group (x positions in discrete-axis units), drawn under
# gridlines and marks; pair with paper_agg_sep at the group boundary
paper_band <- function(xmin, xmax)
  annotate("rect", xmin = xmin, xmax = xmax, ymin = -Inf, ymax = Inf,
           fill = PAPER_BAND, colour = NA)
paper_agg_sep <- function(x)
  geom_vline(xintercept = x, colour = "black", linewidth = 0.4)
paper_lang_sep <- function(xs)
  geom_vline(xintercept = xs, colour = PAPER_LSEP, linewidth = 0.3,
             linetype = "dotted")

# legend keys as small filled squares WITH black borders
paper_legend_keys <- function()
  guides(fill = guide_legend(override.aes = list(colour = "black", linewidth = 0.25)))

# every bar/segment gets a black edge: use these constants in the geoms
PAPER_EDGE <- "black"; PAPER_EDGE_LW <- 0.25

# ---- violin components (mentor spec 2026-09-01) ----------------------------------------
# Paired hue/lightness palette: primary contrast = HUE (blue vs red family), secondary
# variant = LIGHTNESS (dark vs light). Two-group SPEC-vs-Agentic plots use the two DARK
# hues. NOTE: the reference PNG was not provided, so these are the canonical print-safe
# RdBu anchors matching its description — swap in the sampled hexes when the file lands.
PAPER_PAIR <- c(blue_dark = "#2166ac", blue_light = "#92c5de",
                red_dark  = "#b2182b", red_light  = "#f4a582")
PAPER_TWO  <- c(SPEC = unname(PAPER_PAIR["blue_dark"]),
                Agentic = unname(PAPER_PAIR["red_dark"]))
PAPER_VIOLIN_LW <- 0.3        # thin black outline on every violin

# The inner-statistics glyph, drawn ON TOP of the violin (one encoding everywhere):
#   thin black whisker = p5-p95 · THICK black bar = IQR · white square (22) = median ·
#   black circle (21) = mean. `scale` shrinks it for many-column figures.
paper_inner_stats <- function(scale = 1) {
  list(
    stat_summary(fun.min = function(x) quantile(x, .05),
                 fun.max = function(x) quantile(x, .95),
                 geom = "linerange", linewidth = 0.4 * scale, colour = "black"),
    stat_summary(fun.min = function(x) quantile(x, .25),
                 fun.max = function(x) quantile(x, .75),
                 geom = "linerange", linewidth = 2.5 * scale, colour = "black"),
    stat_summary(fun = median, geom = "point", shape = 22, size = 2.1 * scale,
                 fill = "white", colour = "black", stroke = 0.5 * scale),
    stat_summary(fun = mean, geom = "point", shape = 21, size = 1.5 * scale,
                 fill = "black", colour = "black", stroke = 0.3 * scale))
}
PAPER_STATS_SUBTITLE <- paste("violin outline thin black; whisker = 5th-95th pct,",
                              "thick black bar = IQR, white square = median,",
                              "black circle = mean")

# raw-sample overlay for small-n violins (n = workloads, not windows): fixed seed
paper_jitter <- function(seed = 7)
  geom_point(position = position_jitter(width = 0.06, height = 0, seed = seed),
             alpha = 0.5, size = 0.7, colour = "black", shape = 16)

# broken-axis qualifier (mentor rule): a panel qualifies ONLY when its pooled max exceeds
# 3x the pooled 95th percentile. Never combine with a log scale.
paper_break_qualifies <- function(v) max(v) > 3 * quantile(v, .95)

paper_save <- function(p, stem, width, height) {
  ragg::agg_png(paste0(stem, ".png"), width = width, height = height,
                units = "in", res = 300)
  print(p); invisible(dev.off())
  cairo_pdf(paste0(stem, ".pdf"), width = width, height = height, family = PAPER_SERIF)
  print(p); invisible(dev.off())
  cat("wrote", stem, ".png/.pdf\n")
}
