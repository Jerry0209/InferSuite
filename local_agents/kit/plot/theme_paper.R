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

paper_save <- function(p, stem, width, height) {
  ragg::agg_png(paste0(stem, ".png"), width = width, height = height,
                units = "in", res = 300)
  print(p); invisible(dev.off())
  cairo_pdf(paste0(stem, ".pdf"), width = width, height = height, family = PAPER_SERIF)
  print(p); invisible(dev.off())
  cat("wrote", stem, ".png/.pdf\n")
}
