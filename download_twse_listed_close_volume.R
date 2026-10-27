# Download the most recent available TWSE-listed daily data and maintain
# a rolling 53-week history for technical analysis.
#
# Output:
# - twse_listed_close_volume_YYYYMMDD.csv
# - twse_listed_close_volume_latest.csv
# - twse_listed_close_volume_history_53w.csv
# - twse_listed_close_volume_status.txt
#
# Notes:
# - Uses only base R.
# - Falls back to a local Python downloader when R download.file hits SSL issues.
# - Writes UTF-8 with BOM so stock names open correctly in Excel.

options(stringsAsFactors = FALSE)

stock_folder_name <- paste0(intToUtf8(0x80A1), intToUtf8(0x5E02))
output_dir <- file.path(Sys.getenv("USERPROFILE"), "Desktop", stock_folder_name)
if (!dir.exists(output_dir)) {
  dir.create(output_dir, recursive = TRUE)
}

# Default for morning automation: look for the previous available trading day.
# If run after market data is published, it can still find the latest available
# day by setting target_date <- Sys.Date().
target_date <- Sys.Date() - 1
max_lookback_days <- 14
history_weeks <- 53
history_days <- history_weeks * 7

clean_num <- function(x) {
  x <- gsub(",", "", x)
  x <- gsub("--", "", x, fixed = TRUE)
  x <- gsub("^X", "", x)
  suppressWarnings(as.numeric(x))
}

clean_chr <- function(x) {
  trimws(gsub('^="|"$', "", x))
}

write_excel_csv <- function(df, path) {
  con <- file(path, open = "wb")
  writeBin(as.raw(c(0xEF, 0xBB, 0xBF)), con)
  close(con)
  write.table(
    df,
    file = path,
    append = TRUE,
    sep = ",",
    row.names = FALSE,
    col.names = TRUE,
    quote = TRUE,
    qmethod = "double",
    fileEncoding = "UTF-8"
  )
}

download_with_python <- function(url, dest) {
  python_candidates <- c(
    file.path(Sys.getenv("USERPROFILE"), ".cache", "codex-runtimes", "codex-primary-runtime", "dependencies", "python", "python.exe"),
    Sys.which("python"),
    Sys.which("py")
  )
  python_candidates <- python_candidates[nzchar(python_candidates)]
  python <- python_candidates[file.exists(python_candidates)][1]
  if (is.na(python) || !nzchar(python)) {
    return(FALSE)
  }

  py_code <- paste(
    "import sys, urllib.request",
    "url, dest = sys.argv[1], sys.argv[2]",
    "req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})",
    "with urllib.request.urlopen(req, timeout=60) as r:",
    "    data = r.read()",
    "open(dest, 'wb').write(data)",
    sep = "\n"
  )
  py_file <- tempfile(fileext = ".py")
  writeLines(py_code, py_file, useBytes = TRUE)

  result <- try(system2(python, args = c(py_file, url, dest), stdout = TRUE, stderr = TRUE), silent = TRUE)
  !inherits(result, "try-error") && file.exists(dest) && file.info(dest)$size > 5000
}

download_twse_csv <- function(date_value) {
  ymd <- format(date_value, "%Y%m%d")
  url <- paste0(
    "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX",
    "?date=", ymd,
    "&type=ALLBUT0999",
    "&response=csv"
  )

  tmp <- tempfile(fileext = ".csv")

  ok <- tryCatch({
    download.file(url, tmp, mode = "wb", quiet = TRUE)
    file.exists(tmp) && file.info(tmp)$size > 5000
  }, error = function(e) FALSE)

  if (!ok) {
    ok <- download_with_python(url, tmp)
  }

  if (!ok) {
    stop("Download failed: ", format(date_value, "%Y-%m-%d"))
  }

  tmp
}

parse_twse_csv <- function(path, date_value) {
  raw_lines <- readLines(path, encoding = "bytes", warn = FALSE)
  lines <- iconv(raw_lines, from = "CP950", to = "UTF-8", sub = "")
  header_pattern <- "\u8b49\u5238\u4ee3\u865f.*\u8b49\u5238\u540d\u7a31.*\u6210\u4ea4\u80a1\u6578"

  if (!any(grepl(header_pattern, lines, useBytes = TRUE))) {
    lines <- iconv(raw_lines, from = "UTF-8", to = "UTF-8", sub = "")
  }
  lines <- lines[nchar(trimws(lines)) > 0]

  header_idx <- grep(header_pattern, lines, useBytes = TRUE)
  if (length(header_idx) == 0) {
    stop("Could not find TWSE stock table header. Market may be closed or CSV format changed.")
  }

  table_lines <- lines[header_idx[1]:length(lines)]
  table_lines <- table_lines[grepl("^\"", table_lines)]

  tmp <- tempfile(fileext = ".csv")
  writeLines(table_lines, tmp, useBytes = TRUE)

  raw <- read.csv(
    tmp,
    fileEncoding = "UTF-8",
    check.names = FALSE,
    quote = "\"",
    na.strings = c("", "--")
  )

  # TWSE MI_INDEX table column order:
  # 1 id, 2 name, 3 volume, 4 transactions, 5 turnover,
  # 6 open, 7 high, 8 low, 9 close, 10 direction, 11 change,
  # 12 bid price, 13 bid volume, 14 ask price, 15 ask volume, 16 PE.
  out <- data.frame(
    date = format(date_value, "%Y-%m-%d"),
    stock_id = clean_chr(raw[[1]]),
    stock_name = clean_chr(raw[[2]]),
    close = clean_num(raw[[9]]),
    volume = clean_num(raw[[3]]),
    transactions = clean_num(raw[[4]]),
    turnover = clean_num(raw[[5]]),
    open = clean_num(raw[[6]]),
    high = clean_num(raw[[7]]),
    low = clean_num(raw[[8]]),
    direction = clean_chr(raw[[10]]),
    change = clean_num(raw[[11]]),
    last_best_bid_price = clean_num(raw[[12]]),
    last_best_bid_volume = clean_num(raw[[13]]),
    last_best_ask_price = clean_num(raw[[14]]),
    last_best_ask_volume = clean_num(raw[[15]]),
    pe_ratio = clean_num(raw[[16]])
  )

  out <- out[!is.na(out$close) & nzchar(out$stock_id), ]
  out
}

read_existing_history <- function(path) {
  if (!file.exists(path)) {
    return(NULL)
  }
  read.csv(path, fileEncoding = "UTF-8-BOM", stringsAsFactors = FALSE, check.names = FALSE)
}

read_archived_daily_files <- function() {
  files <- list.files(
    output_dir,
    pattern = "^twse_listed_close_volume_[0-9]{8}\\.csv$",
    full.names = TRUE
  )
  files <- files[basename(files) != "twse_listed_close_volume_latest.csv"]
  if (length(files) == 0) {
    return(NULL)
  }

  dfs <- lapply(files, function(path) {
    tryCatch(
      read.csv(path, fileEncoding = "UTF-8-BOM", stringsAsFactors = FALSE, check.names = FALSE),
      error = function(e) NULL
    )
  })
  dfs <- Filter(Negate(is.null), dfs)
  if (length(dfs) == 0) {
    return(NULL)
  }

  common_cols <- Reduce(union, lapply(dfs, names))
  normalized <- lapply(dfs, function(df) {
    for (col in setdiff(common_cols, names(df))) df[[col]] <- NA
    df[common_cols]
  })
  do.call(rbind, normalized)
}

update_history <- function(new_data, history_file) {
  old <- read_existing_history(history_file)
  archives <- read_archived_daily_files()
  parts <- Filter(Negate(is.null), list(old, archives, new_data))

  common_cols <- Reduce(union, lapply(parts, names))
  normalized <- lapply(parts, function(df) {
    for (col in setdiff(common_cols, names(df))) df[[col]] <- NA
    df[common_cols]
  })
  combined <- do.call(rbind, normalized)

  # If earlier files used a smaller schema, keep the analysis columns available.
  preferred <- c(
    "date", "stock_id", "stock_name", "close", "volume", "transactions",
    "turnover", "open", "high", "low", "direction", "change",
    "last_best_bid_price", "last_best_bid_volume",
    "last_best_ask_price", "last_best_ask_volume", "pe_ratio"
  )
  for (col in setdiff(preferred, names(combined))) {
    combined[[col]] <- NA
  }
  combined <- combined[union(preferred, names(combined))]

  combined$date <- as.character(combined$date)
  combined <- combined[order(combined$date, combined$stock_id), ]
  combined <- combined[!duplicated(paste(combined$date, combined$stock_id), fromLast = TRUE), ]

  max_date <- max(as.Date(combined$date), na.rm = TRUE)
  min_keep_date <- max_date - history_days
  combined <- combined[as.Date(combined$date) >= min_keep_date, ]
  combined <- combined[order(combined$date, combined$stock_id), ]
  combined
}

result <- NULL
used_date <- NULL
errors <- character()

for (i in 0:max_lookback_days) {
  d <- target_date - i
  if (weekdays(d) %in% c("Saturday", "Sunday", "\u661f\u671f\u516d", "\u661f\u671f\u65e5")) {
    next
  }

  message("Trying: ", format(d, "%Y-%m-%d"))
  try_result <- tryCatch({
    csv_path <- download_twse_csv(d)
    parse_twse_csv(csv_path, d)
  }, error = function(e) {
    errors <<- c(errors, paste(format(d, "%Y-%m-%d"), e$message))
    NULL
  })

  if (!is.null(try_result) && nrow(try_result) > 0) {
    result <- try_result
    used_date <- d
    break
  }
}

if (is.null(result)) {
  stop(
    "Unable to download TWSE data for the last ",
    max_lookback_days,
    " days.\n",
    paste(errors, collapse = "\n")
  )
}

date_stamp <- format(used_date, "%Y%m%d")
daily_file <- file.path(output_dir, paste0("twse_listed_close_volume_", date_stamp, ".csv"))
daily_excel_file <- file.path(output_dir, paste0("twse_listed_close_volume_", date_stamp, "_excel.csv"))
latest_file <- file.path(output_dir, "twse_listed_close_volume_latest.csv")
latest_excel_file <- file.path(output_dir, "twse_listed_close_volume_latest_excel.csv")
history_file <- file.path(output_dir, "twse_listed_close_volume_history_53w.csv")
status_file <- file.path(output_dir, "twse_listed_close_volume_status.txt")

history <- update_history(result, history_file)

write_excel_csv(result, daily_file)
write_excel_csv(result, daily_excel_file)
write_excel_csv(result, latest_file)
write_excel_csv(result, latest_excel_file)
write_excel_csv(history, history_file)

status_lines <- c(
  "status=ok",
  paste0("data_date=", format(used_date, "%Y-%m-%d")),
  paste0("daily_rows=", nrow(result)),
  paste0("history_rows=", nrow(history)),
  paste0("history_min_date=", min(history$date, na.rm = TRUE)),
  paste0("history_max_date=", max(history$date, na.rm = TRUE)),
  paste0("history_weeks=", history_weeks),
  paste0("daily_file=", daily_file),
  paste0("latest_file=", latest_file),
  paste0("history_file=", history_file),
  if (length(errors) > 0) "download_warnings:" else character(),
  errors
)
writeLines(status_lines, status_file, useBytes = TRUE)

message("Done")
message("Data date: ", format(used_date, "%Y-%m-%d"))
message("Daily rows: ", nrow(result))
message("History rows: ", nrow(history))
message("History range: ", min(history$date), " to ", max(history$date))
message("Daily file: ", daily_file)
message("Latest file: ", latest_file)
message("History file: ", history_file)
