# Download the latest available TWSE-listed daily market data.
#
# This script is intentionally dependency-free.  The previous version depended on
# CRAN packages and broken Chinese column names, which made scheduled runs fail
# before a report could be produced.

options(stringsAsFactors = FALSE)

base_dir <- normalizePath("C:/Users/User/Desktop/股市", winslash = "/", mustWork = TRUE)
setwd(base_dir)

start_lookup_date <- Sys.Date()
max_lookback_days <- 14

message("TWSE daily downloader")
message("Working directory: ", base_dir)
message("Lookup start date: ", format(start_lookup_date, "%Y-%m-%d"))

clean_num <- function(x) {
  x <- gsub(",", "", x)
  x <- gsub("--", "", x, fixed = TRUE)
  x <- gsub("^X", "", x)
  suppressWarnings(as.numeric(x))
}

clean_chr <- function(x) {
  trimws(gsub('^="|"$', "", x))
}

download_with_base_r <- function(url, dest) {
  result <- try(
    download.file(url, dest, mode = "wb", quiet = TRUE, method = "auto"),
    silent = TRUE
  )
  isTRUE(!inherits(result, "try-error") && file.exists(dest) && file.info(dest)$size > 5000)
}

download_with_curl <- function(url, dest) {
  curl <- Sys.which("curl.exe")
  if (identical(curl, "")) {
    return(FALSE)
  }

  args <- c(
    "-L",
    "--ssl-no-revoke",
    "-A", "Mozilla/5.0",
    "--max-time", "60",
    "-o", dest,
    url
  )

  result <- try(system2(curl, args = args, stdout = TRUE, stderr = TRUE), silent = TRUE)
  isTRUE(!inherits(result, "try-error") && file.exists(dest) && file.info(dest)$size > 5000)
}

read_twse_csv <- function(path) {
  lines <- readLines(path, encoding = "UTF-8", warn = FALSE)
  lines <- lines[nchar(trimws(lines)) > 0]

  header_idx <- grep("證券代號.*證券名稱.*成交股數", lines)
  if (length(header_idx) == 0) {
    stop("Downloaded CSV does not contain the expected TWSE stock table header.")
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

  required <- c(
    "證券代號", "證券名稱", "成交股數", "成交筆數", "成交金額",
    "開盤價", "最高價", "最低價", "收盤價", "漲跌(+/-)", "漲跌價差",
    "最後揭示買價", "最後揭示買量", "最後揭示賣價", "最後揭示賣量", "本益比"
  )

  missing <- setdiff(required, names(raw))
  if (length(missing) > 0) {
    stop("TWSE CSV is missing expected columns: ", paste(missing, collapse = ", "))
  }

  data.frame(
    stock_id = clean_chr(raw[["證券代號"]]),
    stock_name = clean_chr(raw[["證券名稱"]]),
    volume = clean_num(raw[["成交股數"]]),
    transactions = clean_num(raw[["成交筆數"]]),
    turnover = clean_num(raw[["成交金額"]]),
    open = clean_num(raw[["開盤價"]]),
    high = clean_num(raw[["最高價"]]),
    low = clean_num(raw[["最低價"]]),
    close = clean_num(raw[["收盤價"]]),
    direction = clean_chr(raw[["漲跌(+/-)"]]),
    change = clean_num(raw[["漲跌價差"]]),
    last_best_bid_price = clean_num(raw[["最後揭示買價"]]),
    last_best_bid_volume = clean_num(raw[["最後揭示買量"]]),
    last_best_ask_price = clean_num(raw[["最後揭示賣價"]]),
    last_best_ask_volume = clean_num(raw[["最後揭示賣量"]]),
    pe_ratio = clean_num(raw[["本益比"]]),
    stringsAsFactors = FALSE
  )
}

get_twse_daily <- function(date_value) {
  ymd <- format(date_value, "%Y%m%d")
  url <- paste0(
    "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX",
    "?date=", ymd,
    "&type=ALLBUT0999&response=csv"
  )

  dest <- tempfile(fileext = ".csv")
  ok <- download_with_base_r(url, dest)
  if (!ok) {
    ok <- download_with_curl(url, dest)
  }
  if (!ok) {
    stop("Unable to download TWSE CSV for ", format(date_value, "%Y-%m-%d"))
  }

  df <- read_twse_csv(dest)
  if (nrow(df) == 0) {
    stop("TWSE CSV contains no stock rows for ", format(date_value, "%Y-%m-%d"))
  }
  df$date <- format(date_value, "%Y-%m-%d")
  df
}

latest_local_file <- function() {
  files <- list.files(
    base_dir,
    pattern = "^twse_listed_daily_[0-9]{8}\\.csv$",
    full.names = TRUE
  )
  if (length(files) == 0) {
    return(NA_character_)
  }
  files[order(file.info(files)$mtime, decreasing = TRUE)][1]
}

errors <- character()
daily <- NULL
used_date <- NA

for (offset in 0:max_lookback_days) {
  date_value <- start_lookup_date - offset
  if (weekdays(date_value) %in% c("Saturday", "Sunday", "星期六", "星期日")) {
    next
  }

  message("Trying TWSE date: ", format(date_value, "%Y-%m-%d"))
  result <- try(get_twse_daily(date_value), silent = TRUE)
  if (!inherits(result, "try-error")) {
    daily <- result
    used_date <- date_value
    break
  }

  msg <- paste0(format(date_value, "%Y-%m-%d"), ": ", conditionMessage(attr(result, "condition")))
  errors <- c(errors, msg)
  message("Failed: ", msg)
}

if (is.null(daily)) {
  local_file <- latest_local_file()
  if (!is.na(local_file)) {
    message("Download failed. Falling back to local file: ", local_file)
    daily <- read.csv(local_file, check.names = FALSE, stringsAsFactors = FALSE)
    if (!"date" %in% names(daily)) {
      daily$date <- NA_character_
    }
    used_date <- as.Date(gsub("[^0-9]", "", basename(local_file)), format = "%Y%m%d")
  } else {
    stop(
      "No TWSE data could be downloaded and no local twse_listed_daily_YYYYMMDD.csv fallback file exists.\n",
      paste(errors, collapse = "\n")
    )
  }
}

date_stamp <- format(as.Date(used_date), "%Y%m%d")
output_file <- file.path(base_dir, paste0("twse_listed_daily_", date_stamp, ".csv"))
latest_file <- file.path(base_dir, "twse_listed_daily_latest.csv")
status_file <- file.path(base_dir, "twse_listed_daily_status.txt")

write.csv(daily, output_file, row.names = FALSE, fileEncoding = "UTF-8")
write.csv(daily, latest_file, row.names = FALSE, fileEncoding = "UTF-8")

status_lines <- c(
  paste0("status=ok"),
  paste0("data_date=", format(as.Date(used_date), "%Y-%m-%d")),
  paste0("rows=", nrow(daily)),
  paste0("output_file=", output_file),
  paste0("latest_file=", latest_file),
  if (length(errors) > 0) "download_warnings:" else character(),
  errors
)
writeLines(status_lines, status_file, useBytes = TRUE)

message("Done.")
message("Data date: ", format(as.Date(used_date), "%Y-%m-%d"))
message("Rows: ", nrow(daily))
message("Saved: ", output_file)
message("Latest copy: ", latest_file)
