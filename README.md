# regulatory-return-automation

A monthly regulatory return, built from transaction data by a pipeline that refuses to produce the file when the numbers can't be trusted.

## The problem

A return that's assembled by hand works fine for months. Then somebody's on leave, or a load fails quietly, or a query gets copied from last quarter with last quarter's dates still in it, and the wrong number goes out under the company's name.

The query is rarely the hard part. The hard part is everything around it. Is the data for the period complete? Does the total on the form agree with the source? Why did line C1 jump 15% since August, and can you answer that before the regulator asks? Six months on, can you show exactly what was run?

In my day job I build and automate the data behind central-bank submissions, and our Compliance team files them. This repo isn't that work. It's the same shape of problem, rebuilt from scratch on invented data, so you can read the approach and run it yourself.

## What it does

```
transactions (raw, UTC)
      |
      v
stg_transactions        local reporting date, test accounts out, integers only
      |
      v
return_lines.sql        13 lines across 4 sections of the form
      |
      v
checks                  10 blocking controls + 1 review warning
      |
      +--> FAIL:  no file is written, exit code 1
      |
      +--> PASS:  PS-M1_<period>.xlsx  (form, variance sheet, check results)
      |
      v
manifest.json           written every time, including for blocked runs
```

The form is PS-M1, a monthly payment systems return for the Central Bank of Meridia. I made both up, along with the reporting institution, Zaffre Wallet. The form has 13 lines in 4 sections, and 11 checks run before any of them is written: 10 that block the return and 1 that only warns.

## The checks

| Check | If it fails | What it catches |
|---|---|---|
| `line_set` | Blocked | The SQL returned a line the form doesn't have, or missed one it does |
| `every_day_present` | Blocked | A day with no transactions, which nearly always means a load didn't run |
| `unique_transaction_ids` | Blocked | Rows loaded twice |
| `status_domain` | Blocked | A status the pipeline doesn't know, which would silently drop out of every section |
| `amounts_valid` | Blocked | Missing, zero or negative amounts |
| `control_total` | Blocked | The headline total recomputed by a second route that shares no code with the first |
| `type_lines_sum_to_total` | Blocked | Section B lines that don't add up to the section total |
| `status_reconciliation` | Blocked | Successful + failed + reversed not accounting for every row |
| `customer_counts_consistent` | Blocked | More active or new customers than registered ones |
| `test_accounts_excluded` | Blocked | Internal test accounts leaking into the figures |
| `variance_vs_prior_period` | Released with a warning | Any line that moved more than the threshold since last month |

I split blocking from warning on purpose. A blocked check means the numbers are wrong. A variance warning means they may well be right, but a person should look before signing. So the file is still produced, and the warning is written into it where whoever files it will see it.

## Run it

You need Python 3.9 or later.

```bash
pip install -r requirements.txt
```

```bash
python data/generate.py
```

```bash
python -m return_pipeline --period 2025-09 --variance-threshold 0.10
```

```bash
python -m pytest
```

## What a run looks like

September 2025 in the synthetic data has an outage on the 17th. With a 10% threshold:

```
Run PS-M1-2025-09-20261115T171621
  PASS    line_set: all lines present
  PASS    every_day_present: 30 of 30 days have transactions
  PASS    unique_transaction_ids: 18426 rows, 18426 distinct ids
  PASS    status_domain: 0 rows with an unrecognised status
  PASS    amounts_valid: 0 rows with a missing, zero or negative amount
  PASS    control_total: return: 16769 txns / 108121205 minor; independent: 16769 txns / 108121205 minor
  PASS    type_lines_sum_to_total: types: 16769 / 108121205; total line: (16769, 108121205)
  PASS    status_reconciliation: 18095 reported of 18095 rows
  PASS    customer_counts_consistent: registered=3629 new=99 active=2646
  PASS    test_accounts_excluded: 0 test-account rows in staging
  REVIEW  variance_vs_prior_period: A2 count -22.7%; C1 count +15.0%; C1 value +20.5%
Status: released_with_warnings
```

All 10 blocking checks pass, so the return goes out: 16,769 successful transactions, with all 18,095 rows in the period accounted for. Three figures are flagged for review. Failed transactions are up 15% on August and their value is up 20.5%. That's the outage, and it's exactly the line a regulator would ask about. New registrations are down 22.7%, from 128 to 99, which is ordinary month-to-month noise at that size.

You'll find the workbook and manifest from this run in [`docs/`](docs/).

## Decisions worth explaining

**I keep money in integers.** Amounts are stored in minor units, 100 to 1 MRD, and only divided when the workbook is written. September's total is 108,121,205 minor units by both routes, to the unit. That's what lets `control_total` compare with `==` and not "close enough".

**One staging view owns the 3 decisions everyone gets wrong.** Local reporting date, test-account exclusion and units are defined once in [`sql/stg_transactions.sql`](sql/stg_transactions.sql). The timestamp is stored in UTC and the business reports in UTC+3, so 182 transactions in this dataset belong to a different month depending on which clock you read.

**The control total takes a different road.** The return goes through the staging view and filters on local date. The control goes straight to the raw table with UTC bounds worked out in Python: local midnight on 1 June is 21:00 on 31 May. If I'd got the timezone wrong in one path, the two would disagree.

**The source is opened read-only.** The pipeline can't change the data it reports on, and I test that byte for byte.

**A blocked run still writes a manifest.** A record of what was stopped, and why, is worth as much as a record of what went out.

**The manifest hashes its inputs.** It holds a SHA-256 of the database, both SQL files and the workbook, plus the threshold used. Six months later, "what exactly produced this number" has an answer.

**5 of the 14 tests break the data on purpose.** They delete a day, invent a status, load rows twice and plant a negative amount, then check the run is blocked.

## The messy part

- The primary key on my demo table makes duplicates impossible, so the duplicate test has to rebuild the table without one first. Warehouse tables usually have no enforced keys, which is why the check exists.
- The variance threshold is one number for every line, 25% by default. That's too blunt. New registrations swing by 20% on their own, as September shows. A 20% move in transaction value would be a much bigger deal. Each line should carry its own tolerance, learned from its own history.
- It runs on SQLite so you can run it anywhere. The SQL would need small changes for a warehouse engine, mostly the date functions.
- There's no scheduler here. In practice this sits behind one, with the exit code (0 or 1) deciding whether anyone gets paged.

## About the data

Every row is generated by [`data/generate.py`](data/generate.py) from a fixed seed: 4,000 customers and 194,707 transactions across 2025. No real company, customer, merchant, regulator or reporting format appears anywhere in this repo, and none of the code comes from an employer's systems.

## Licence

MIT
