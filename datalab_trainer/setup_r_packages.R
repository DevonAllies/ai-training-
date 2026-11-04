# Optional R packages used in DataLab lesson examples (the checked exercises use base R only).
#   Windows: Rscript setup_r_packages.R        Ubuntu: Rscript setup_r_packages.R
# On Ubuntu, packages compile from source unless you use binaries; installing these first helps:
#   sudo apt install libcurl4-openssl-dev libssl-dev libxml2-dev
pkgs <- c("ggplot2", "dplyr", "tidyr", "readr", "readxl", "jsonlite", "DBI", "RSQLite", "rmarkdown",
          "kernelshap", "shapviz")
lib <- Sys.getenv("R_LIBS_USER")
if (!nzchar(lib)) lib <- .libPaths()[1]
dir.create(lib, recursive = TRUE, showWarnings = FALSE)
.libPaths(c(lib, .libPaths()))
missing <- pkgs[!vapply(pkgs, requireNamespace, logical(1), quietly = TRUE)]
if (length(missing)) {
  message("Installing: ", paste(missing, collapse = ", "))
  install.packages(missing, lib = lib, repos = "https://cloud.r-project.org")
} else {
  message("All optional R packages are already installed.")
}
