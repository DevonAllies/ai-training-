id: forecast-r-2
stage: forecast
lang: r
title: HoltWinters() and a regression forecast in R
--- task
Using the same split (last 52 weeks = test):

* **`hw`** – `HoltWinters()` on a `ts` of the training sales (`frequency = 52`), **`mae_hw`** from `predict(hw, n.ahead = 52)`
* **`fit`** – `lm(sales ~ t + sin1 + cos1 + promo)` on the training rows, where `t` is 0, 1, 2, … and
  `sin1`/`cos1` use the ISO week `w <- as.numeric(strftime(as.Date(s$week), "%V"))`; **`mae_lm`** on the test rows

Plot the test actuals with both forecasts.
--- starter
s <- read.csv("data/store_sales.csv")

hw <- NA
mae_hw <- NA
fit <- NA
mae_lm <- NA
--- solution
s <- read.csv("data/store_sales.csv")
test_y <- tail(s$sales, 52)

train_ts <- ts(head(s$sales, -52), frequency = 52, start = c(2021, 1))
hw <- HoltWinters(train_ts)
fc_hw <- as.numeric(predict(hw, n.ahead = 52))
mae_hw <- mean(abs(test_y - fc_hw))

s$t <- seq_len(nrow(s)) - 1
w <- as.numeric(strftime(as.Date(s$week), "%V"))
s$sin1 <- sin(2 * pi * w / 52)
s$cos1 <- cos(2 * pi * w / 52)
fit <- lm(sales ~ t + sin1 + cos1 + promo, data = head(s, -52))
fc_lm <- predict(fit, newdata = tail(s, 52))
mae_lm <- mean(abs(test_y - fc_lm))

plot(test_y, type = "l", lwd = 2, ylim = range(c(test_y, fc_hw, fc_lm)),
     main = sprintf("2024 forecasts: lm MAE %.0f, Holt-Winters MAE %.0f", mae_lm, mae_hw),
     xlab = "Week of test year", ylab = "Weekly sales")
lines(fc_hw, col = "steelblue", lwd = 2)
lines(fc_lm, col = "firebrick", lwd = 2)
legend("topleft", c("actual", "Holt-Winters", "regression"), col = c("black", "steelblue", "firebrick"), lwd = 2, bty = "n")
--- check
expect(inherits(hw, "HoltWinters"), "hw should be HoltWinters(train_ts).")
expect(is.numeric(mae_hw) && mae_hw > 2000 && mae_hw < 9000, paste("mae_hw looks wrong:", mae_hw))
expect(inherits(fit, "lm") && all(c("t", "sin1", "cos1", "promo") %in% names(coef(fit))), "fit should be lm(sales ~ t + sin1 + cos1 + promo).")
expect(is.numeric(mae_lm) && mae_lm > 2000 && mae_lm < 3300, paste("mae_lm should be about 2,700; you have", round(mae_lm)))
CHECK_MESSAGE <- sprintf("Regression MAE %.0f vs Holt-Winters %.0f: knowing the promotion calendar wins.", mae_lm, mae_hw)
--- hints
- `HoltWinters(ts_object)` estimates level, trend and season automatically.
- `as.numeric(predict(hw, n.ahead = 52))`
- `predict(fit, newdata = tail(s, 52))`
