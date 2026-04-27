from __future__ import annotations

import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from contabila_ai.importing.models import ImportedTransaction  # noqa: E402
from contabila_ai.planning import build_query_plan  # noqa: E402
from contabila_ai.review import ReviewService  # noqa: E402
from contabila_ai.storage.store import SQLiteTransactionStore  # noqa: E402


class ReviewServiceTest(unittest.TestCase):
    def test_candidates_returns_low_confidence_rows_first(self) -> None:
        db_path = ROOT / "test_review_candidates.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2024-04-20",
                        description="Plata diverse consumabile",
                        amount=-120.0,
                        currency="RON",
                        balance=4880.0,
                        merchant="Magazin Necunoscut",
                        source_file="statement.csv",
                        raw_payload='{"id":"candidate-1"}',
                    ),
                    ImportedTransaction(
                        transaction_date="2024-04-21",
                        description="Transfer ocazional fara regula",
                        amount=-90.0,
                        currency="RON",
                        balance=4790.0,
                        merchant="Alta Plata",
                        source_file="statement.csv",
                        raw_payload='{"id":"candidate-2"}',
                    ),
                    ImportedTransaction(
                        transaction_date="2024-04-22",
                        description="Comision administrare cont",
                        amount=-15.0,
                        currency="RON",
                        balance=4775.0,
                        merchant="Banca Exemplu",
                        source_file="statement.csv",
                        raw_payload='{"id":"not-review"}',
                    ),
                ]
            )

            service = ReviewService(store)
            rows = service.candidates(limit=2)

            self.assertEqual(len(rows), 2)
            self.assertEqual(
                [row["description"] for row in rows],
                [
                    "Transfer ocazional fara regula",
                    "Plata diverse consumabile",
                ],
            )
            self.assertTrue(all(row["confidence"] < 0.75 for row in rows))
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_apply_category_updates_targeted_and_similar_transactions(self) -> None:
        db_path = ROOT / "test_review_apply_category.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2024-02-10",
                        description="Chirie apartament",
                        amount=-500.0,
                        currency="RON",
                        balance=4500.0,
                        merchant="Locator SRL",
                        source_file="statement.csv",
                        raw_payload='{"id":"house-1"}',
                    ),
                    ImportedTransaction(
                        transaction_date="2024-05-20",
                        description="Reparatie urgenta",
                        amount=-300.0,
                        currency="RON",
                        balance=4200.0,
                        merchant="Locator SRL",
                        source_file="statement.csv",
                        raw_payload='{"id":"house-2"}',
                    ),
                    ImportedTransaction(
                        transaction_date="2024-09-01",
                        description="Chirie apartament",
                        amount=-700.0,
                        currency="RON",
                        balance=3500.0,
                        merchant="Alt Locator",
                        source_file="statement.csv",
                        raw_payload='{"id":"house-3"}',
                    ),
                    ImportedTransaction(
                        transaction_date="2024-03-01",
                        description="Cafea echipa",
                        amount=-45.0,
                        currency="RON",
                        balance=4455.0,
                        merchant="Coffee Shop",
                        source_file="statement.csv",
                        raw_payload='{"id":"other"}',
                    ),
                ]
            )

            target_row = store.query(
                """
                SELECT id
                FROM transactions
                WHERE raw_payload = '{"id":"house-1"}'
                """
            )[0]

            service = ReviewService(store)
            result = service.apply_category(
                category_name="casa",
                transaction_ids=[target_row["id"]],
                apply_to_similar=True,
            )

            self.assertEqual(result["updated_count"], 3)

            links = store.query(
                """
                SELECT t.raw_payload, ac.name
                FROM transaction_category_links AS tcl
                INNER JOIN transactions AS t
                    ON t.id = tcl.transaction_id
                INNER JOIN analysis_categories AS ac
                    ON ac.id = tcl.category_id
                WHERE ac.name = 'casa'
                ORDER BY t.id ASC
                """
            )
            self.assertEqual(
                [row["raw_payload"] for row in links],
                [
                    '{"id":"house-1"}',
                    '{"id":"house-2"}',
                    '{"id":"house-3"}',
                ],
            )

            execution = store.execute_plan(
                build_query_plan("pe jumatate de an, cat am avut cheltuielile cu casa")
            )
            self.assertEqual(
                execution.rows,
                [
                    {"group_key": "2024-H1", "metric_value": 800.0, "transaction_count": 2},
                    {"group_key": "2024-H2", "metric_value": 700.0, "transaction_count": 1},
                ],
            )

            remaining_candidates = service.candidates(limit=10)
            self.assertEqual(len(remaining_candidates), 1)
            self.assertEqual(remaining_candidates[0]["merchant"], "Coffee Shop")
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_confirm_transaction_marks_row_as_reviewed_and_hides_it_from_candidates(self) -> None:
        db_path = ROOT / "test_review_confirm.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2024-04-20",
                        description="Plata rara fara incadrare",
                        amount=-120.0,
                        currency="RON",
                        balance=4880.0,
                        merchant="Magazin Necunoscut",
                        source_file="statement.csv",
                        raw_payload='{"id":"confirm-me"}',
                    )
                ]
            )

            row = store.query(
                """
                SELECT id
                FROM transactions
                WHERE raw_payload = '{"id":"confirm-me"}'
                """
            )[0]

            service = ReviewService(store)
            before = service.candidates(limit=10)
            service.confirm_transaction(row["id"])
            after = service.candidates(limit=10)
            stored_row = store.query(
                """
                SELECT confidence, reason
                FROM transactions
                WHERE id = ?
                """,
                (row["id"],),
            )[0]

            self.assertEqual(len(before), 1)
            self.assertEqual(after, [])
            self.assertGreaterEqual(stored_row["confidence"], 0.99)
            self.assertIn("review confirmed", stored_row["reason"])
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_apply_category_matches_same_supplier_when_merchant_format_varies(self) -> None:
        db_path = ROOT / "test_review_supplier_similarity.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2024-04-06",
                        description="TRANSFER ONLINE INTERBANCAR | Beneficiar: EXPASCONT CENTER S.R.L. | Detalii: /ROC/FACTURA EPC 2027006",
                        amount=-605.0,
                        currency="RON",
                        balance=4500.0,
                        merchant="EXPASCONT CENTER S.R.L.",
                        source_file="statement.csv",
                        raw_payload='{"id":"supplier-1"}',
                    ),
                    ImportedTransaction(
                        transaction_date="2024-04-15",
                        description="TRANSFER ONLINE INTERBANCAR | Beneficiar: EXPASCONT CENTER SRL | Detalii: /ROC/FACTURA EPC 2026891",
                        amount=-605.0,
                        currency="RON",
                        balance=3895.0,
                        merchant="EXPASCONT CENTER SRL",
                        source_file="statement.csv",
                        raw_payload='{"id":"supplier-2"}',
                    ),
                    ImportedTransaction(
                        transaction_date="2024-04-20",
                        description="TRANSFER ONLINE INTERBANCAR | Beneficiar: ALT FURNIZOR SRL | Detalii: /ROC/FACTURA 9981",
                        amount=-605.0,
                        currency="RON",
                        balance=3290.0,
                        merchant="ALT FURNIZOR SRL",
                        source_file="statement.csv",
                        raw_payload='{"id":"supplier-3"}',
                    ),
                ]
            )

            target_row = store.query(
                """
                SELECT id
                FROM transactions
                WHERE raw_payload = '{"id":"supplier-1"}'
                """
            )[0]

            service = ReviewService(store)
            result = service.apply_category(
                category_name="servicii",
                transaction_ids=[target_row["id"]],
                apply_to_similar=True,
            )

            links = store.query(
                """
                SELECT t.raw_payload, ac.name
                FROM transaction_category_links AS tcl
                INNER JOIN transactions AS t
                    ON t.id = tcl.transaction_id
                INNER JOIN analysis_categories AS ac
                    ON ac.id = tcl.category_id
                WHERE ac.name = 'servicii'
                ORDER BY t.id ASC
                """
            )

            self.assertEqual(result["updated_count"], 2)
            self.assertEqual(
                [row["raw_payload"] for row in links],
                ['{"id":"supplier-1"}', '{"id":"supplier-2"}'],
            )
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_candidate_groups_merge_rows_for_same_supplier(self) -> None:
        db_path = ROOT / "test_review_candidate_groups.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2025-06-06",
                        description="TRANSFER ONLINE INTERBANCAR | Beneficiar: CEMI CONCEPT TEC SRL | Detalii: /ROC/PLATA FACTURA SERIE CCT NR. 25914",
                        amount=-31.9,
                        currency="RON",
                        balance=4100.0,
                        merchant="CEMI CONCEPT TEC SRL",
                        source_file="statement.csv",
                        raw_payload='{"id":"cemi-1"}',
                    ),
                    ImportedTransaction(
                        transaction_date="2025-06-06",
                        description="TRANSFER ONLINE INTERBANCAR | Beneficiar: CEMI CONCEPT TEC SRL | Detalii: /ROC/PLATA FACTURA SERIA CCT NR. 25804",
                        amount=-165.96,
                        currency="RON",
                        balance=3934.04,
                        merchant="CEMI CONCEPT TEC SRL",
                        source_file="statement.csv",
                        raw_payload='{"id":"cemi-2"}',
                    ),
                    ImportedTransaction(
                        transaction_date="2025-06-06",
                        description="TRANSFER ONLINE INTERBANCAR | Beneficiar: ELDAM SRL | Detalii: /ROC/PLATA FACTURA SERIA ELD NR. 1130",
                        amount=-20260.28,
                        currency="RON",
                        balance=2000.0,
                        merchant="ELDAM SRL",
                        source_file="statement.csv",
                        raw_payload='{"id":"eldam-1"}',
                    ),
                ]
            )

            service = ReviewService(store)
            groups = service.candidate_groups(limit=10)

            self.assertEqual(len(groups), 2)
            cemi_group = next(group for group in groups if group["group_label"] == "CEMI CONCEPT TEC SRL")
            eldam_group = next(group for group in groups if group["group_label"] == "ELDAM SRL")
            self.assertEqual(cemi_group["transaction_count"], 2)
            self.assertEqual(cemi_group["transaction_ids"], sorted(cemi_group["transaction_ids"]))
            self.assertEqual(
                [sample["merchant"] for sample in cemi_group["samples"]],
                ["CEMI CONCEPT TEC SRL", "CEMI CONCEPT TEC SRL"],
            )
            self.assertEqual(eldam_group["transaction_count"], 1)
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_candidate_groups_offer_suggestions_from_previously_categorized_transactions(self) -> None:
        db_path = ROOT / "test_review_suggestions.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2025-01-10",
                        description="TRANSFER ONLINE INTERBANCAR | Beneficiar: RAZVAN DUMITRESCU | Detalii: /ROC/PLATA SALAR DECEMBRIE 2024",
                        amount=-980.0,
                        currency="RON",
                        balance=6000.0,
                        merchant="RAZVAN DUMITRESCU",
                        source_file="statement.csv",
                        raw_payload='{"id":"salary-known"}',
                    ),
                    ImportedTransaction(
                        transaction_date="2025-02-05",
                        description="TRANSFER ONLINE INTERBANCAR | Beneficiar: RAZVAN DUMITRESCU | Detalii: /ROC/PLATA SALAR IANUARIE 2025",
                        amount=-992.0,
                        currency="RON",
                        balance=5008.0,
                        merchant="RAZVAN DUMITRESCU",
                        source_file="statement.csv",
                        raw_payload='{"id":"salary-review"}',
                    ),
                ]
            )

            known_row = store.query(
                """
                SELECT id
                FROM transactions
                WHERE raw_payload = '{"id":"salary-known"}'
                """
            )[0]
            review_row = store.query(
                """
                SELECT id
                FROM transactions
                WHERE raw_payload = '{"id":"salary-review"}'
                """
            )[0]

            store.assign_analysis_category("colaboratori", [known_row["id"]])

            service = ReviewService(store)
            groups = service.candidate_groups(limit=10)

            target_group = next(group for group in groups if review_row["id"] in group["transaction_ids"])
            self.assertEqual(target_group["suggested_category"], "colaboratori")
            self.assertIn("colaboratori", target_group["suggested_categories"])
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_candidate_groups_warn_when_existing_category_has_close_name(self) -> None:
        db_path = ROOT / "test_review_category_conflict.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            store.add_analysis_category("colaboratori")
            store.add_analysis_category("furnizori")
            store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2025-02-05",
                        description="TRANSFER ONLINE INTERBANCAR | Beneficiar: RAZVAN DUMITRESCU | Detalii: /ROC/PLATA SALAR IANUARIE 2025",
                        amount=-992.0,
                        currency="RON",
                        balance=5008.0,
                        merchant="RAZVAN DUMITRESCU",
                        source_file="statement.csv",
                        raw_payload='{"id":"salary-review"}',
                    )
                ]
            )

            service = ReviewService(store)
            warning = service.find_category_name_conflict("colaborator")

            self.assertIsNotNone(warning)
            self.assertEqual(warning["existing_category"], "colaboratori")
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_apply_category_can_replace_existing_category_for_similar_transactions(self) -> None:
        db_path = ROOT / "test_review_replace_category.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2025-05-01",
                        description="Amenajare casa parter",
                        amount=-1500.0,
                        currency="RON",
                        balance=8500.0,
                        merchant="Construct House SRL",
                        source_file="statement.csv",
                        raw_payload='{"id":"move-1"}',
                    ),
                    ImportedTransaction(
                        transaction_date="2025-05-10",
                        description="Amenajare casa etaj",
                        amount=-1700.0,
                        currency="RON",
                        balance=6800.0,
                        merchant="Construct House SRL",
                        source_file="statement.csv",
                        raw_payload='{"id":"move-2"}',
                    ),
                ]
            )

            target_row = store.query(
                """
                SELECT id
                FROM transactions
                WHERE raw_payload = '{"id":"move-1"}'
                """
            )[0]
            store.assign_analysis_category("casa", [target_row["id"]])

            service = ReviewService(store)
            result = service.apply_category(
                category_name="investitii",
                transaction_ids=[target_row["id"]],
                apply_to_similar=True,
                replace_existing=True,
                description="Cheltuieli de investitii non-operationale.",
                operational_scope="non_operational",
            )

            links = store.query(
                """
                SELECT t.raw_payload, ac.name, ac.operational_scope
                FROM transaction_category_links AS tcl
                INNER JOIN transactions AS t
                    ON t.id = tcl.transaction_id
                INNER JOIN analysis_categories AS ac
                    ON ac.id = tcl.category_id
                ORDER BY t.id ASC, ac.name ASC
                """
            )

            self.assertEqual(result["updated_count"], 2)
            self.assertEqual(
                [(row["raw_payload"], row["name"]) for row in links],
                [
                    ('{"id":"move-1"}', "investitii"),
                    ('{"id":"move-2"}', "investitii"),
                ],
            )
            self.assertTrue(all(row["operational_scope"] == "non_operational" for row in links))
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_candidate_groups_include_review_severity(self) -> None:
        db_path = ROOT / "test_review_severity.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            workspace_id = store.create_workspace("MobExc")
            store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2025-06-01",
                        description="Plata contractor major fara categorie",
                        amount=-15000.0,
                        currency="RON",
                        balance=8500.0,
                        merchant="Contractor Mare SRL",
                        source_file="statement.csv",
                        raw_payload='{"id":"sev-1"}',
                    ),
                    ImportedTransaction(
                        transaction_date="2025-06-02",
                        description="Plata mica ocazionala",
                        amount=-120.0,
                        currency="RON",
                        balance=8380.0,
                        merchant="Magazin Mic",
                        source_file="statement.csv",
                        raw_payload='{"id":"sev-2"}',
                    ),
                ],
                workspace_id=workspace_id,
            )

            service = ReviewService(store)
            groups = service.candidate_groups(limit=10, workspace_id=workspace_id)
            counts = service.severity_counts(workspace_id=workspace_id)

            severities = {group["severity"] for group in groups}
            self.assertIn("critical", severities)
            self.assertGreaterEqual(counts["critical"], 1)
            self.assertTrue(service.has_blocking_items(workspace_id=workspace_id))
        finally:
            if db_path.exists():
                db_path.unlink()


if __name__ == "__main__":
    unittest.main()
