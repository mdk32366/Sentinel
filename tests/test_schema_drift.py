"""D-0032 — the drift check that replaces what alembic would have detected.

Alembic was pinned and never initialized, so dropping it costs no migrations.
What it costs is *detection*: `create_all()` creates missing tables and
silently ignores changed columns (`F-0022`), so `models.py` and the database
can disagree indefinitely with nothing saying so.

`diff_schema` is pure, so these run offline against hand-built schemas — no
database, no fixtures that can rot.
"""
import unittest

from tools.check_schema_drift import (
    declared_schema,
    diff_schema,
    has_structural_drift,
    render,
)

IN_SYNC = {"metrics": {"id": "INTEGER", "code": "VARCHAR(50)"}}


class TestDiffSchema(unittest.TestCase):
    def test_identical_schemas_show_no_drift(self):
        """Clause (c): a checker that always reported drift would pass every
        test below and be useless."""
        diff = diff_schema(IN_SYNC, IN_SYNC)
        self.assertFalse(has_structural_drift(diff))
        self.assertEqual(render(diff), "  no drift")

    def test_a_table_in_models_but_not_the_database(self):
        """What happens when create_all has not been run after adding a model."""
        diff = diff_schema({**IN_SYNC, "composite_snapshots": {"id": "INTEGER"}}, IN_SYNC)
        self.assertEqual(diff["missing_tables"], ["composite_snapshots"])
        self.assertTrue(has_structural_drift(diff))

    def test_a_table_in_the_database_but_not_models(self):
        diff = diff_schema(IN_SYNC, {**IN_SYNC, "leftovers": {"id": "INTEGER"}})
        self.assertEqual(diff["extra_tables"], ["leftovers"])
        self.assertTrue(has_structural_drift(diff))

    def test_a_column_added_to_models_and_never_to_the_database(self):
        """The case create_all cannot fix: the table exists, so it does nothing."""
        declared = {"metrics": {"id": "INTEGER", "code": "VARCHAR(50)", "note": "TEXT"}}
        diff = diff_schema(declared, IN_SYNC)
        self.assertEqual(diff["missing_columns"], {"metrics": ["note"]})
        self.assertTrue(has_structural_drift(diff))

    def test_a_column_in_the_database_that_models_does_not_know_about(self):
        live = {"metrics": {"id": "INTEGER", "code": "VARCHAR(50)", "legacy": "TEXT"}}
        diff = diff_schema(IN_SYNC, live)
        self.assertEqual(diff["extra_columns"], {"metrics": ["legacy"]})
        self.assertTrue(has_structural_drift(diff))

    def test_a_changed_column_TYPE_is_reported_but_does_not_fail(self):
        """A-0003's live case: error_message is varchar(500) and wants widening.
        Reported so a human sees it; not fatal, because SQLAlchemy types and
        database introspection do not round-trip cleanly and a checker that
        cried wolf on every VARCHAR would be ignored within a week."""
        declared = {"update_logs": {"error_message": "VARCHAR(2000)"}}
        live = {"update_logs": {"error_message": "VARCHAR(500)"}}
        diff = diff_schema(declared, live)
        self.assertEqual(
            diff["type_differences"]["update_logs"],
            [("error_message", "VARCHAR(2000)", "VARCHAR(500)")],
        )
        self.assertFalse(has_structural_drift(diff))
        self.assertIn("advisory", render(diff))

    def test_the_canary_table_is_not_drift(self):
        """It exists in a disposable database by design and is deliberately
        absent from models.py, so the app cannot create its own disposability
        marker (D-0039)."""
        diff = diff_schema(IN_SYNC, {**IN_SYNC, "canary": {"marker": "VARCHAR(64)"}})
        self.assertFalse(has_structural_drift(diff))

    def test_empty_database_reports_every_table_as_missing(self):
        diff = diff_schema(IN_SYNC, {})
        self.assertEqual(diff["missing_tables"], ["metrics"])

    def test_render_names_the_table_and_column(self):
        """A drift report that does not say WHICH sends you to psql to find out."""
        declared = {"metrics": {"id": "INTEGER", "note": "TEXT"}}
        text = render(diff_schema(declared, {"metrics": {"id": "INTEGER"}}))
        self.assertIn("metrics", text)
        self.assertIn("note", text)


class TestDeclaredSchemaFromModels(unittest.TestCase):
    def test_it_reads_the_real_models(self):
        declared = declared_schema()
        self.assertIn("metrics", declared)
        self.assertIn("timeseries", declared)
        self.assertIn("update_logs", declared)
        self.assertIn("composite_snapshots", declared)

    def test_models_does_not_declare_the_canary(self):
        """If this ever fails, the application can create its own disposability
        marker and the Step 12 guard means nothing."""
        self.assertNotIn("canary", declared_schema())

    def test_error_message_is_still_the_varchar_500_from_A_0003(self):
        """Pins the known constraint. When it is widened by hand, this test is
        what tells the next person the DDL and the model must move together."""
        self.assertEqual(
            declared_schema()["update_logs"]["error_message"], "VARCHAR(500)"
        )


if __name__ == "__main__":
    unittest.main()
