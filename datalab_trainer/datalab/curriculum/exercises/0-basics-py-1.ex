id: basics-py-1
stage: basics
lang: python
title: Python essentials - lists, loops, dictionaries, functions
--- task
Without pandas, using plain Python:

1. Given the list `spends`, compute **`total`** with a `for` loop (don't use `sum()`) and **`mean`** = total / number of items.
2. Write a function **`annual(monthly)`** that returns the yearly amount (× 12).
3. Build a dictionary **`counts`** that counts how often each plan appears in the list `plans`,
   e.g. `{"Basic": 3, ...}`.
4. Make a list **`big`** with only the spends above 60 (a list comprehension: `[s for s in spends if ...]`).
--- starter
spends = [52.1, 80.0, 61.5, 45.0, 99.9, 70.25]
plans = ["Basic", "Premium", "Basic", "Standard", "Basic", "Premium"]

total = 0
# loop here

mean = None


def annual(monthly):
    pass


counts = {}
big = []
--- solution
spends = [52.1, 80.0, 61.5, 45.0, 99.9, 70.25]
plans = ["Basic", "Premium", "Basic", "Standard", "Basic", "Premium"]

total = 0
for s in spends:
    total = total + s
mean = total / len(spends)


def annual(monthly):
    return monthly * 12


counts = {}
for p in plans:
    counts[p] = counts.get(p, 0) + 1

big = [s for s in spends if s > 60]
print(total, round(mean, 2), annual(19.99), counts, big)
--- check
expect(abs(total - 408.75) < 1e-9, f"total should be 408.75, you have {total}.")
expect(mean is not None and abs(mean - 408.75 / 6) < 1e-9, "mean should be total / len(spends).")
expect(callable(annual) and annual(10) == 120, "annual(10) should return 120.")
expect(counts == {"Basic": 3, "Premium": 2, "Standard": 1}, f"counts should be {{'Basic': 3, 'Premium': 2, 'Standard': 1}}, you have {counts}.")
expect(big == [80.0, 61.5, 99.9, 70.25], f"big should keep the spends above 60 in their original order, you have {big}.")
CHECK_MESSAGE = "Well done: loops, functions, dictionaries and comprehensions are the building blocks of everything later."
--- hints
- Inside the loop: `total = total + s` (or `total += s`).
- `counts.get(p, 0)` returns 0 the first time a plan is seen.
- `[s for s in spends if s > 60]`
