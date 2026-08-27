# ============================================================================
# iso36_style.R -- house-style module for the ML_iso36 figures (filled instance
# of skillhub/ggplot-house-style/reference/style_template.R). Only the three
# PROJECT STUBS are filled; the fixed look-and-feel is copied verbatim.
# ============================================================================

# 1. Palette: DISPLAY-name -> color, tied to the series NAME. The fence colors
#    are the deck-wide convention (green = tool, purple = harness); working /
#    stall reuse the overview figure's Okabe-Ito pair.
house_fill <- c(
  "CPU working"                 = "#0072B2",
  "CPU stall (incl. model wait)"= "#C9C9C9",
  "Tool"                        = "#159f77",
  "Harness"                     = "#6a51a3",
  "count"                       = "#0072B2"
)

# 2. Canonical legend / stack order.
house_levels <- c("CPU working", "CPU stall (incl. model wait)", "Tool", "Harness")

# 3. Relabel: raw tokens pass through unchanged in this project.
house_relabel <- function(x) x

# ---------------------------------------------------------------------------
# FIXED LOOK-AND-FEEL  --  copied from the template; do NOT edit per project.
# ---------------------------------------------------------------------------
house_fill_scale <- function(...) ggplot2::scale_fill_manual(values = house_fill, name = NULL, ...)
house_colour_scale <- function(...) ggplot2::scale_colour_manual(values = house_fill, name = NULL, ...)

theme_house <- function(base_size = 11, axis_title_size = 12, bars = TRUE) {
  th <- hrbrthemes::theme_ipsum_rc(base_size = base_size, axis_title_size = axis_title_size) +
    ggplot2::theme(
      legend.position = "bottom",
      axis.title.x = ggplot2::element_text(hjust = 0.5),
      axis.title.y = ggplot2::element_text(hjust = 0.5)
    )
  if (bars) th <- th + ggplot2::theme(panel.grid.major.x = ggplot2::element_blank())
  th
}

house_dodge   <- function(width = 0.9) ggplot2::position_dodge(width = width)
house_col     <- function(...) ggplot2::geom_col(width = 0.85, colour = "grey30", linewidth = 0.12, ...)
house_hline1  <- function(y = 1) ggplot2::geom_hline(yintercept = y, linetype = "dashed", colour = "grey40")

house_save <- function(plot, path_noext, width = 13, height = 7, dpi = 200,
                       vector = c("pdf", "svg")) {
  vector <- match.arg(vector)
  ggplot2::ggsave(paste0(path_noext, ".png"), plot, width = width, height = height,
                  dpi = dpi, device = ragg::agg_png)
  if (vector == "pdf") {
    ggplot2::ggsave(paste0(path_noext, ".pdf"), plot, width = width, height = height,
                    device = grDevices::cairo_pdf)
  } else {
    ggplot2::ggsave(paste0(path_noext, ".svg"), plot, width = width, height = height,
                    device = grDevices::svg)
  }
  message("wrote ", path_noext, ".{png,", vector, "}")
}

benefit_of_doubt_accuracy <- function(acc) ifelse(is.na(acc), 100, acc)
