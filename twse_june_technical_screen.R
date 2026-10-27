# TWSE listed-company technical screen for June 2026.
# Output focuses on close price, volume, seven buy signals, industry seasonality,
# and a final ranked candidate list.

start_month <- as.Date("2026-06-01")
end_date <- Sys.Date()

# Historical lookback is required for 3/6/12-month momentum and 52-week high.
history_start <- as.Date("2025-06-01")

output_dir <- "C:/Users/User/Desktop/\u80a1\u5e02"
candidate_output <- file.path(output_dir, "twse_june_buy_candidates.csv")

dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

download_text <- function(url, encoding = "UTF-8") {
  tmp <- tempfile(fileext = ".txt")

  ok <- tryCatch({
    download.file(url, tmp, mode = "wb", quiet = TRUE)
    TRUE
  }, error = function(e) FALSE)

  if (!ok && .Platform$OS.type == "windows") {
    curl <- Sys.which("curl.exe")
    if (nzchar(curl)) {
      args <- c(
        "-L", "--http1.1", "--ssl-no-revoke",
        "-A", "Mozilla/5.0",
        url,
        "-o", tmp
      )
      ok <- system2(curl, args = args, stdout = FALSE, stderr = FALSE) == 0
    }
  }

  if (!ok) {
    stop("Download failed: ", url)
  }

  paste(readLines(tmp, encoding = encoding, warn = FALSE), collapse = "\n")
}

clean_number <- function(x) {
  x <- gsub(",", "", x)
  x[x %in% c("--", "", " ")] <- NA
  suppressWarnings(as.numeric(x))
}

get_listed_companies <- function() {
  url <- "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
  txt <- download_text(url, encoding = "UTF-8")

  objects <- regmatches(txt, gregexpr("\\{[^{}]*\\}", txt))[[1]]

  field <- function(obj, key) {
    pattern <- paste0('"', key, '"\\s*:\\s*"([^"]*)"')
    hit <- regmatches(obj, regexec(pattern, obj))[[1]]
    if (length(hit) < 2) return(NA_character_)
    hit[2]
  }

  data.frame(
    stock_id = vapply(objects, field, character(1), key = "\u516c\u53f8\u4ee3\u865f"),
    stock_name = vapply(objects, field, character(1), key = "\u516c\u53f8\u540d\u7a31"),
    industry = vapply(objects, field, character(1), key = "\u7522\u696d\u5225"),
    paid_in_capital = clean_number(vapply(objects, field, character(1), key = "\u5be6\u6536\u8cc7\u672c\u984d")),
    stringsAsFactors = FALSE
  )
}

get_twse_day <- function(date) {
  url <- paste0(
    "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX",
    "?date=", format(date, "%Y%m%d"),
    "&type=ALLBUT0999",
    "&response=csv"
  )

  txt <- tryCatch(download_text(url, encoding = "CP950"), error = function(e) "")
  if (!nzchar(txt)) {
    return(data.frame())
  }

  lines <- unlist(strsplit(txt, "\n", fixed = TRUE))
  lines <- trimws(gsub('^="(.*)"$', "\\1", lines))
  lines <- lines[nzchar(lines)]

  rows <- list()
  n <- 0

  for (line in lines) {
    parsed <- tryCatch(
      read.csv(text = line, header = FALSE, stringsAsFactors = FALSE, check.names = FALSE),
      error = function(e) NULL
    )

    if (is.null(parsed) || ncol(parsed) < 16) {
      next
    }

    stock_id <- gsub('^=|"', "", as.character(parsed[1, 1]))

    # Keep TWSE listed common stocks only: 4 numeric digits.
    if (!grepl("^[1-9][0-9]{3}$", stock_id)) {
      next
    }

    n <- n + 1
    rows[[n]] <- data.frame(
      date = date,
      stock_id = stock_id,
      stock_name = as.character(parsed[1, 2]),
      volume = clean_number(as.character(parsed[1, 3])),
      close = clean_number(as.character(parsed[1, 9])),
      stringsAsFactors = FALSE
    )
  }

  if (length(rows) == 0) {
    return(data.frame())
  }

  do.call(rbind, rows)
}

trading_days <- function(from, to) {
  days <- seq(from, to, by = "day")
  days[as.POSIXlt(days)$wday %in% 1:5]
}

lag_value <- function(dates, values, target_date) {
  idx <- which(dates <= target_date & !is.na(values))
  if (length(idx) == 0) {
    return(NA_real_)
  }
  values[max(idx)]
}

safe_ratio <- function(a, b) {
  ifelse(is.na(a) | is.na(b) | b == 0, NA_real_, a / b)
}

calc_one_stock <- function(df) {
  df <- df[order(df$date), ]
  latest <- df[nrow(df), ]
  dates <- df$date
  close <- df$close
  volume <- df$volume

  current_close <- latest$close
  current_volume <- latest$volume

  close_3m <- lag_value(dates, close, latest$date - 90)
  close_6m <- lag_value(dates, close, latest$date - 180)
  close_12m <- lag_value(dates, close, latest$date - 365)

  mom_3m <- safe_ratio(current_close, close_3m) - 1
  mom_6m <- safe_ratio(current_close, close_6m) - 1
  mom_12m <- safe_ratio(current_close, close_12m) - 1

  ma20 <- mean(tail(close[!is.na(close)], 20), na.rm = TRUE)
  ma60 <- mean(tail(close[!is.na(close)], 60), na.rm = TRUE)
  vol20 <- mean(tail(volume[!is.na(volume)], 20), na.rm = TRUE)
  vol60 <- mean(tail(volume[!is.na(volume)], 60), na.rm = TRUE)

  returns <- diff(log(close))
  recent_returns <- tail(returns[is.finite(returns)], 20)
  breakout_level <- max(head(tail(close[!is.na(close)], 21), 20), na.rm = TRUE)

  high_52w <- max(close[dates >= latest$date - 365], na.rm = TRUE)
  distance_to_high <- safe_ratio(current_close, high_52w) - 1
  price_to_ma_distance <- safe_ratio(current_close, ma60) - 1
  ma_ratio <- safe_ratio(ma20, ma60)
  turnover_proxy <- safe_ratio(current_volume, vol60)
  volatility_20d <- sd(recent_returns, na.rm = TRUE) * sqrt(252)
  volume_shock <- safe_ratio(current_volume, vol20)

  momentum_buy <- sum(c(mom_3m > 0, mom_6m > 0, mom_12m > 0), na.rm = TRUE) >= 2
  high_52w_buy <- !is.na(distance_to_high) && distance_to_high >= -0.10
  ma_ratio_buy <- !is.na(ma_ratio) && ma_ratio > 1
  price_ma_buy <- !is.na(price_to_ma_distance) && price_to_ma_distance > 0 && price_to_ma_distance < 0.25
  turnover_buy <- !is.na(turnover_proxy) && turnover_proxy > 1.2
  volatility_breakout_buy <- !is.na(current_close) && is.finite(breakout_level) && current_close > breakout_level
  volume_shock_buy <- !is.na(volume_shock) && volume_shock > 1.5

  buy_count <- sum(c(
    momentum_buy,
    high_52w_buy,
    ma_ratio_buy,
    price_ma_buy,
    turnover_buy,
    volatility_breakout_buy,
    volume_shock_buy
  ))

  data.frame(
    stock_id = latest$stock_id,
    stock_name = latest$stock_name,
    signal_date = latest$date,
    close = current_close,
    volume = current_volume,
    mom_3m = mom_3m,
    mom_6m = mom_6m,
    mom_12m = mom_12m,
    distance_to_52w_high = distance_to_high,
    ma_ratio_20_60 = ma_ratio,
    price_to_ma60_distance = price_to_ma_distance,
    turnover_proxy = turnover_proxy,
    volatility_20d = volatility_20d,
    volume_shock = volume_shock,
    momentum_buy = momentum_buy,
    high_52w_buy = high_52w_buy,
    ma_ratio_buy = ma_ratio_buy,
    price_ma_buy = price_ma_buy,
    turnover_buy = turnover_buy,
    volatility_breakout_buy = volatility_breakout_buy,
    volume_shock_buy = volume_shock_buy,
    buy_signal_count = buy_count,
    stringsAsFactors = FALSE
  )
}

cat("Getting TWSE listed-company metadata...\n")
companies <- get_listed_companies()

days <- trading_days(history_start, end_date)
daily_list <- vector("list", length(days))

cat("Downloading daily close and volume from ", as.character(history_start), " to ", as.character(end_date), "...\n", sep = "")
for (i in seq_along(days)) {
  Sys.sleep(0.2)
  daily_list[[i]] <- get_twse_day(days[i])
  cat(format(days[i], "%Y-%m-%d"), " rows: ", nrow(daily_list[[i]]), "\n", sep = "")
}

daily <- do.call(rbind, daily_list)
daily <- merge(daily, companies[, c("stock_id", "industry", "paid_in_capital")], by = "stock_id", all.x = TRUE)
daily <- daily[order(daily$stock_id, daily$date), ]

latest_june_date <- max(daily$date[daily$date >= start_month & daily$date <= end_date], na.rm = TRUE)
june_stocks <- unique(daily$stock_id[daily$date == latest_june_date])

screen_input <- daily[daily$stock_id %in% june_stocks & daily$date <= latest_june_date, ]
by_stock <- split(screen_input, screen_input$stock_id)
signals <- do.call(rbind, lapply(by_stock, calc_one_stock))

signals <- merge(signals, companies[, c("stock_id", "industry", "paid_in_capital")], by = "stock_id", all.x = TRUE)

june_history <- daily[daily$date >= start_month & daily$date <= latest_june_date, ]
june_returns <- do.call(rbind, lapply(split(june_history, june_history$stock_id), function(x) {
  x <- x[order(x$date), ]
  if (nrow(x) < 2) return(NULL)
  data.frame(
    stock_id = x$stock_id[1],
    june_return = tail(x$close, 1) / x$close[1] - 1,
    stringsAsFactors = FALSE
  )
}))

june_returns <- merge(june_returns, companies[, c("stock_id", "industry")], by = "stock_id", all.x = TRUE)
industry_score <- aggregate(june_return ~ industry, june_returns, mean, na.rm = TRUE)
names(industry_score)[2] <- "industry_june_season_score"

signals <- merge(signals, industry_score, by = "industry", all.x = TRUE)
signals$industry_june_season_score[is.na(signals$industry_june_season_score)] <- 0

rank01 <- function(x, higher_is_better = TRUE) {
  if (all(is.na(x))) return(rep(0, length(x)))
  r <- rank(if (higher_is_better) x else -x, na.last = "keep", ties.method = "average")
  out <- (r - 1) / max(1, sum(!is.na(x)) - 1)
  out[is.na(out)] <- 0
  out
}

signals$technical_score <- signals$buy_signal_count / 7
signals$season_score_rank <- rank01(signals$industry_june_season_score)
signals$momentum_score_rank <- rank01(rowMeans(signals[, c("mom_3m", "mom_6m", "mom_12m")], na.rm = TRUE))
signals$volume_score_rank <- rank01(signals$volume_shock)

signals$final_score <- 0.65 * signals$technical_score +
  0.20 * signals$season_score_rank +
  0.10 * signals$momentum_score_rank +
  0.05 * signals$volume_score_rank

candidates <- signals[signals$buy_signal_count >= 5, ]
candidates <- candidates[order(-candidates$final_score, -candidates$buy_signal_count), ]

write.csv(candidates, candidate_output, row.names = FALSE, fileEncoding = "UTF-8")

cat("Latest June signal date: ", as.character(latest_june_date), "\n", sep = "")
cat("Candidates: ", nrow(candidates), "\n", sep = "")
cat("Saved candidates: ", candidate_output, "\n", sep = "")
