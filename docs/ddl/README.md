# Migration SQL

One file per schema change, named `YYYY-MM-DD-description.sql`, each opening
with a comment naming the decision or finding that motivated it.

`Base.metadata.create_all()` handles new *tables* by itself (`D-0032`). Every
other change — a widened column, a new column on an existing table, a dropped
one — is hand-written DDL and belongs here, because a statement run against
production and not written down is a schema change nobody can reconstruct.

Before applying anything here, run `python tools/check_schema_drift.py` against
the target so you know what it currently disagrees about.

The procedure, including the fact that `psql` is not in the image, is in
`docs/architecture.md` under *Schema changes are manual*.

## Outstanding

`update_logs.error_message` is `varchar(500)` and `A-0003` records that a
multi-series FRED failure can overflow it — the insert throws and the log row
is lost. ORDER-01 B4 added truncation at 480 so the row survives; widening the
column is the other half and has not been done.
