from __future__ import annotations

import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from contabila_ai.importing.models import ImportedInvoice, ImportedTransaction  # noqa: E402
from contabila_ai.importing.parsers import parse_issued_invoices_path  # noqa: E402
from contabila_ai.planning import build_query_plan  # noqa: E402
from contabila_ai.server.http import render_answer  # noqa: E402
from contabila_ai.storage.store import SQLiteTransactionStore  # noqa: E402


class PlannerTest(unittest.TestCase):
    def test_build_query_plan_extracts_multi_year_creditare_question(self) -> None:
        plan = build_query_plan("cat am avut creditare pe 2023/2024/2025")

        self.assertEqual(plan.mode, "aggregate")
        self.assertEqual(plan.metric, "total_amount")
        self.assertEqual(plan.years, [2023, 2024, 2025])
        self.assertEqual(plan.group_by, "year")
        self.assertEqual(plan.economic_kind, "creditare")
        self.assertIsNone(plan.analysis_category)
        self.assertIsNone(plan.entity_name)
        self.assertEqual(plan.direction, "inflow")
        self.assertFalse(plan.requested_profit)

    def test_build_query_plan_understands_creditat_wording(self) -> None:
        plan = build_query_plan("cati bani am creditat uitandu-te la extras")

        self.assertEqual(plan.metric, "total_amount")
        self.assertEqual(plan.economic_kind, "creditare")
        self.assertEqual(plan.direction, "inflow")

    def test_build_query_plan_groups_creditare_by_year_for_each_year_wording(self) -> None:
        plan = build_query_plan("cat am creditat in fiecare an de cand ai informatii")

        self.assertEqual(plan.metric, "total_amount")
        self.assertEqual(plan.economic_kind, "creditare")
        self.assertEqual(plan.direction, "inflow")
        self.assertEqual(plan.group_by, "year")

    def test_build_query_plan_compares_creditare_with_recovery(self) -> None:
        plan = build_query_plan("cati bani am creditat in toti anii si cati bani am recuperat")

        self.assertEqual(plan.metric, "creditare_vs_recuperare")
        self.assertIsNone(plan.economic_kind)
        self.assertEqual(plan.direction, "both")
        self.assertEqual(plan.metric_label, "creditare si recuperare creditare")
        self.assertEqual(plan.creditare_focus, "recovered")
        self.assertTrue(plan.include_creditare_balance)

    def test_build_query_plan_detects_remaining_creditare_focus(self) -> None:
        plan = build_query_plan("cat mai am de recuperat din creditare")

        self.assertEqual(plan.metric, "creditare_vs_recuperare")
        self.assertEqual(plan.creditare_focus, "remaining")
        self.assertTrue(plan.include_creditare_balance)

    def test_build_query_plan_detects_outstanding_received_invoice_balance(self) -> None:
        plan = build_query_plan("cat mai am de platit pe facturile primite")

        self.assertEqual(plan.mode, "aggregate")
        self.assertEqual(plan.metric, "invoice_residual_total")
        self.assertEqual(plan.support_level, "exact")
        self.assertEqual(plan.metric_label, "sold facturi primite")

    def test_build_query_plan_extracts_half_year_house_expense_question(self) -> None:
        plan = build_query_plan("pe jumatate de an, cat am avut cheltuielile cu casa")

        self.assertEqual(plan.mode, "aggregate")
        self.assertEqual(plan.metric, "expense_total")
        self.assertEqual(plan.years, [])
        self.assertEqual(plan.group_by, "half_year")
        self.assertIsNone(plan.economic_kind)
        self.assertEqual(plan.analysis_category, "casa")
        self.assertIsNone(plan.entity_name)
        self.assertEqual(plan.direction, "outflow")
        self.assertFalse(plan.requested_profit)

    def test_build_query_plan_marks_profit_question_as_net_cashflow_request(self) -> None:
        plan = build_query_plan("care a fost profitul pe 2024")

        self.assertEqual(plan.mode, "aggregate")
        self.assertEqual(plan.metric, "net_cashflow")
        self.assertEqual(plan.years, [2024])
        self.assertIsNone(plan.group_by)
        self.assertTrue(plan.requested_profit)
        self.assertEqual(plan.direction, "both")

    def test_build_query_plan_detects_first_year_relative_period(self) -> None:
        plan = build_query_plan("cat am avut pe primul an profit")

        self.assertEqual(plan.metric, "net_cashflow")
        self.assertEqual(plan.relative_period, "first_year")
        self.assertTrue(plan.requested_profit)

    def test_build_query_plan_extracts_entity_name_for_search_questions(self) -> None:
        plan = build_query_plan("arata tranzactiile cu Dedeman")

        self.assertEqual(plan.mode, "search")
        self.assertEqual(plan.entity_name, "dedeman")
        self.assertIsNone(plan.analysis_category)
        self.assertIsNone(plan.economic_kind)

    def test_build_query_plan_detects_entity_relationship_summary(self) -> None:
        plan = build_query_plan("care e situatia lui Ai Excellence")

        self.assertEqual(plan.metric, "entity_relationship_summary")
        self.assertEqual(plan.support_level, "exact")
        self.assertEqual(plan.entity_name, "ai excellence")

    def test_build_query_plan_marks_generic_situation_question_for_clarification(self) -> None:
        plan = build_query_plan("care e situatia acum")

        self.assertEqual(plan.support_level, "clarify")
        self.assertEqual(plan.metric_label, "clarificare")

    def test_build_query_plan_detects_entity_relationship_summary_with_project_scope(self) -> None:
        plan = build_query_plan("care e situatia lui Casa Decor pe proiectul Casa Noua")

        self.assertEqual(plan.metric, "entity_relationship_summary")
        self.assertEqual(plan.support_level, "exact")
        self.assertEqual(plan.entity_name, "casa decor")
        self.assertEqual(plan.project_name, "casa noua")

    def test_build_query_plan_extracts_project_name(self) -> None:
        plan = build_query_plan("cat am platit pe proiectul Casa Noua")

        self.assertEqual(plan.project_name, "casa noua")
        self.assertEqual(plan.direction, "outflow")

    def test_build_query_plan_extracts_entity_name_for_aggregate_counterparty_question(self) -> None:
        plan = build_query_plan("cate plati am facut catre ai excellence")

        self.assertEqual(plan.mode, "aggregate")
        self.assertEqual(plan.metric, "transaction_count")
        self.assertEqual(plan.direction, "outflow")
        self.assertEqual(plan.entity_name, "ai excellence")

    def test_build_query_plan_marks_cifra_de_afaceri_as_estimated_operational_income(self) -> None:
        plan = build_query_plan("ce cifra de afaceri am avut pe 2025")

        self.assertEqual(plan.mode, "aggregate")
        self.assertEqual(plan.metric, "operational_income_estimate")
        self.assertEqual(plan.years, [2025])
        self.assertEqual(plan.direction, "inflow")
        self.assertEqual(plan.support_level, "estimated")
        self.assertEqual(plan.metric_label, "cifra de afaceri")

    def test_build_query_plan_marks_tva_question_as_unsupported_from_bank_statement(self) -> None:
        plan = build_query_plan("cat TVA am de plata pe 2025")

        self.assertEqual(plan.support_level, "unsupported")
        self.assertEqual(plan.metric_label, "TVA")
        self.assertEqual(plan.metric, "unsupported")

    def test_store_execute_plan_groups_creditare_amounts_by_year(self) -> None:
        db_path = ROOT / "test_planner_year_group.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2023-02-10",
                        description="Creditare firma asociat",
                        amount=1000.0,
                        currency="RON",
                        balance=1000.0,
                        merchant="Asociat",
                        source_file="statement.csv",
                        raw_payload='{"id":"2023"}',
                    ),
                    ImportedTransaction(
                        transaction_date="2024-04-15",
                        description="Creditare firma asociat",
                        amount=2000.0,
                        currency="RON",
                        balance=3000.0,
                        merchant="Asociat",
                        source_file="statement.csv",
                        raw_payload='{"id":"2024"}',
                    ),
                    ImportedTransaction(
                        transaction_date="2025-08-05",
                        description="Creditare firma asociat",
                        amount=3000.0,
                        currency="RON",
                        balance=6000.0,
                        merchant="Asociat",
                        source_file="statement.csv",
                        raw_payload='{"id":"2025"}',
                    ),
                ]
            )

            result = store.execute_plan(build_query_plan("cat am avut creditare pe 2023/2024/2025"))

            self.assertEqual(
                result.rows,
                [
                    {"group_key": "2023", "metric_value": 1000.0, "transaction_count": 1},
                    {"group_key": "2024", "metric_value": 2000.0, "transaction_count": 1},
                    {"group_key": "2025", "metric_value": 3000.0, "transaction_count": 1},
                ],
            )
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_store_execute_plan_filters_by_project_assignment_inside_workspace(self) -> None:
        db_path = ROOT / "test_planner_project_filter.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            workspace_id = store.create_workspace("MobExc")
            store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2025-05-10",
                        description="Plata colaborator proiect Casa Noua",
                        amount=-1200.0,
                        currency="RON",
                        balance=8800.0,
                        merchant="Casa Decor SRL",
                        source_file="statement.csv",
                        raw_payload='{\"id\":\"project-house\"}',
                    ),
                    ImportedTransaction(
                        transaction_date="2025-05-11",
                        description="Plata colaborator proiect App Core",
                        amount=-800.0,
                        currency="RON",
                        balance=8000.0,
                        merchant="Dev Sprint SRL",
                        source_file="statement.csv",
                        raw_payload='{\"id\":\"project-app\"}',
                    ),
                ],
                workspace_id=workspace_id,
            )
            instruction_id = store.add_business_instruction(
                workspace_id=workspace_id,
                raw_text="Casa Decor SRL lucreaza pe proiectul Casa Noua",
            )
            # direct seed because this test exercises planner/store filtering, not parser behavior
            from contabila_ai.memory.models import BusinessFact  # noqa: E402

            store.add_business_facts(
                workspace_id=workspace_id,
                instruction_id=instruction_id,
                facts=[
                    BusinessFact(
                        fact_type="project_assignment",
                        subject_name="Casa Decor SRL",
                        fact_value="Casa Noua",
                    )
                ],
            )

            plan = build_query_plan("cat am platit pe proiectul Casa Noua")
            result = store.execute_plan_for_import(plan, workspace_id=workspace_id)

            self.assertEqual(
                result.rows,
                [{"group_key": None, "metric_value": 1200.0, "transaction_count": 1}],
            )
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_store_execute_plan_filters_to_first_available_year(self) -> None:
        db_path = ROOT / "test_planner_first_year.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2022-02-10",
                        description="Incasare primul an",
                        amount=1000.0,
                        currency="RON",
                        balance=1000.0,
                        merchant="Client Alpha",
                        source_file="statement.csv",
                        raw_payload='{"id":"2022-income"}',
                    ),
                    ImportedTransaction(
                        transaction_date="2022-03-10",
                        description="Plata primul an",
                        amount=-300.0,
                        currency="RON",
                        balance=700.0,
                        merchant="Furnizor Alpha",
                        source_file="statement.csv",
                        raw_payload='{"id":"2022-expense"}',
                    ),
                    ImportedTransaction(
                        transaction_date="2026-03-31",
                        description="Plata an recent",
                        amount=-70.45,
                        currency="RON",
                        balance=629.55,
                        merchant="Furnizor Recent",
                        source_file="statement.csv",
                        raw_payload='{"id":"2026-expense"}',
                    ),
                ]
            )

            plan = build_query_plan("cat am avut pe primul an profit")
            result = store.execute_plan(plan)
            rows = store.list_matching_transactions_for_plan(plan)

            self.assertEqual(
                result.rows,
                [{"group_key": None, "metric_value": 700.0, "transaction_count": 2}],
            )
            self.assertEqual({row["transaction_date"][:4] for row in rows}, {"2022"})
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_store_execute_plan_filters_to_first_year_within_workspace_scope(self) -> None:
        db_path = ROOT / "test_planner_first_year_workspace.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            workspace_alpha = store.create_workspace("Alpha")
            workspace_beta = store.create_workspace("Beta")
            store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2022-01-05",
                        description="Incasare Alpha",
                        amount=1000.0,
                        currency="RON",
                        balance=1000.0,
                        merchant="Client Alpha",
                        source_file="alpha.csv",
                        raw_payload='{"id":"alpha-2022"}',
                    )
                ],
                workspace_id=workspace_alpha,
            )
            store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2026-01-05",
                        description="Incasare Beta",
                        amount=500.0,
                        currency="RON",
                        balance=500.0,
                        merchant="Client Beta",
                        source_file="beta.csv",
                        raw_payload='{"id":"beta-2026-income"}',
                    ),
                    ImportedTransaction(
                        transaction_date="2026-01-07",
                        description="Plata Beta",
                        amount=-150.0,
                        currency="RON",
                        balance=350.0,
                        merchant="Supplier Beta",
                        source_file="beta.csv",
                        raw_payload='{"id":"beta-2026-expense"}',
                    ),
                ],
                workspace_id=workspace_beta,
            )

            plan = build_query_plan("cat am avut pe primul an profit")
            result = store.execute_plan_for_import(plan, workspace_id=workspace_beta)
            rows = store.list_matching_transactions_for_plan(plan, workspace_id=workspace_beta)

            self.assertEqual(
                result.rows,
                [{"group_key": None, "metric_value": 350.0, "transaction_count": 2}],
            )
            self.assertEqual({row["transaction_date"][:4] for row in rows}, {"2026"})
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_store_execute_plan_filters_aggregate_question_by_entity_name(self) -> None:
        db_path = ROOT / "test_planner_entity_aggregate.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2025-02-10",
                        description="Plata servicii AI Excellence sprint 1",
                        amount=-1000.0,
                        currency="RON",
                        balance=9000.0,
                        merchant="AI Excellence SRL",
                        source_file="statement.csv",
                        raw_payload='{"id":"ai-1"}',
                    ),
                    ImportedTransaction(
                        transaction_date="2025-03-10",
                        description="Plata servicii AI Excellence sprint 2",
                        amount=-2000.0,
                        currency="RON",
                        balance=7000.0,
                        merchant="1/AI EXCELLENCE S.R.L.",
                        source_file="statement.csv",
                        raw_payload='{"id":"ai-2"}',
                    ),
                    ImportedTransaction(
                        transaction_date="2025-03-11",
                        description="Plata alt colaborator",
                        amount=-500.0,
                        currency="RON",
                        balance=6500.0,
                        merchant="Alt Colaborator SRL",
                        source_file="statement.csv",
                        raw_payload='{"id":"other"}',
                    ),
                ]
            )

            plan = build_query_plan("cate plati am facut catre ai excellence")
            result = store.execute_plan(plan)
            rows = store.list_matching_transactions_for_plan(plan)

            self.assertEqual(
                result.rows,
                [{"group_key": None, "metric_value": 2, "transaction_count": 2}],
            )
            self.assertEqual(len(rows), 2)
            self.assertEqual(
                {row["merchant"] for row in rows},
                {"AI Excellence SRL", "1/AI EXCELLENCE S.R.L."},
            )
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_store_execute_plan_returns_entity_relationship_summary(self) -> None:
        db_path = ROOT / "test_planner_entity_relationship.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2025-02-10",
                        description="Incasare AI Excellence sprint 1",
                        amount=3000.0,
                        currency="RON",
                        balance=3000.0,
                        merchant="AI Excellence SRL",
                        source_file="statement.csv",
                        raw_payload='{"id":"ai-in-1"}',
                    ),
                    ImportedTransaction(
                        transaction_date="2025-03-10",
                        description="Plata AI Excellence subcontractor",
                        amount=-1000.0,
                        currency="RON",
                        balance=2000.0,
                        merchant="1/AI EXCELLENCE S.R.L.",
                        source_file="statement.csv",
                        raw_payload='{"id":"ai-out-1"}',
                    ),
                ]
            )

            result = store.execute_plan(build_query_plan("care e situatia lui ai excellence"))

            self.assertEqual(
                result.rows,
                [
                    {
                        "group_key": None,
                        "income_total": 3000.0,
                        "expense_total": 1000.0,
                        "net_value": 2000.0,
                        "transaction_count": 2,
                        "entity_type": "partner",
                    }
                ],
            )
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_store_execute_plan_returns_entity_relationship_summary_scoped_to_project(self) -> None:
        db_path = ROOT / "test_planner_entity_relationship_project.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            workspace_id = store.create_workspace("MobExc")
            store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2025-02-10",
                        description="Plata Casa Decor proiect Casa Noua",
                        amount=-1200.0,
                        currency="RON",
                        balance=8800.0,
                        merchant="Casa Decor SRL",
                        source_file="statement.csv",
                        raw_payload='{"id":"project-rel-1"}',
                    ),
                    ImportedTransaction(
                        transaction_date="2025-02-12",
                        description="Plata Casa Decor alt proiect",
                        amount=-700.0,
                        currency="RON",
                        balance=8100.0,
                        merchant="Casa Decor SRL",
                        source_file="statement.csv",
                        raw_payload='{"id":"project-rel-2"}',
                    ),
                ],
                workspace_id=workspace_id,
            )
            instruction_id = store.add_business_instruction(
                workspace_id=workspace_id,
                raw_text="Casa Decor SRL lucreaza pe proiectul Casa Noua",
            )
            from contabila_ai.memory.models import BusinessFact  # noqa: E402

            store.add_business_facts(
                workspace_id=workspace_id,
                instruction_id=instruction_id,
                facts=[
                    BusinessFact(
                        fact_type="project_assignment",
                        subject_name="Casa Decor SRL",
                        fact_value="Casa Noua",
                    )
                ],
            )

            plan = build_query_plan("care e situatia lui Casa Decor pe proiectul Casa Noua")
            result = store.execute_plan_for_import(plan, workspace_id=workspace_id)

            self.assertEqual(
                result.rows,
                [
                    {
                        "group_key": None,
                        "income_total": 0.0,
                        "expense_total": 1900.0,
                        "net_value": -1900.0,
                        "transaction_count": 2,
                        "entity_type": "collaborator",
                    }
                ],
            )
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_store_execute_plan_returns_only_creditare_and_recovery_for_compound_question(self) -> None:
        db_path = ROOT / "test_planner_creditare_recovery.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2026-04-20",
                        description="Creditare firma asociat",
                        amount=10000.0,
                        currency="RON",
                        balance=10000.0,
                        merchant="Asociat",
                        source_file="statement.csv",
                        raw_payload='{"id":"creditare"}',
                    ),
                    ImportedTransaction(
                        transaction_date="2026-04-22",
                        description="Recuperare creditare asociat",
                        amount=-2500.0,
                        currency="RON",
                        balance=7500.0,
                        merchant="Asociat",
                        source_file="statement.csv",
                        raw_payload='{"id":"recuperare"}',
                    ),
                    ImportedTransaction(
                        transaction_date="2026-04-23",
                        description="Plata furnizor",
                        amount=-4000.0,
                        currency="RON",
                        balance=3500.0,
                        merchant="Furnizor SRL",
                        source_file="statement.csv",
                        raw_payload='{"id":"supplier"}',
                    ),
                ]
            )

            plan = build_query_plan("cati bani am creditat si cati bani am recuperat")
            result = store.execute_plan(plan)
            rows = store.list_matching_transactions_for_plan(plan)

            self.assertEqual(
                result.rows,
                [
                    {"group_key": "creditare", "metric_value": 10000.0, "transaction_count": 1},
                    {"group_key": "recuperare_creditare", "metric_value": 2500.0, "transaction_count": 1},
                ],
            )
            self.assertEqual([row["economic_kind"] for row in rows], ["recuperare_creditare", "creditare"])
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_store_execute_plan_groups_creditare_vs_recovery_by_year(self) -> None:
        db_path = ROOT / "test_planner_creditare_recovery_yearly.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2025-01-10",
                        description="Creditare firma",
                        amount=1000.0,
                        currency="RON",
                        balance=1000.0,
                        merchant="Asociat",
                        source_file="statement.csv",
                        raw_payload='{"id":"c-2025"}',
                    ),
                    ImportedTransaction(
                        transaction_date="2025-02-10",
                        description="Recuperare creditare",
                        amount=-300.0,
                        currency="RON",
                        balance=700.0,
                        merchant="Asociat",
                        source_file="statement.csv",
                        raw_payload='{"id":"r-2025"}',
                    ),
                    ImportedTransaction(
                        transaction_date="2026-01-11",
                        description="Creditare firma",
                        amount=2000.0,
                        currency="RON",
                        balance=2700.0,
                        merchant="Asociat",
                        source_file="statement.csv",
                        raw_payload='{"id":"c-2026"}',
                    ),
                    ImportedTransaction(
                        transaction_date="2026-02-12",
                        description="Recuperare creditare",
                        amount=-500.0,
                        currency="RON",
                        balance=2200.0,
                        merchant="Asociat",
                        source_file="statement.csv",
                        raw_payload='{"id":"r-2026"}',
                    ),
                ]
            )

            plan = build_query_plan("cati bani am creditat in fiecare an si cati am recuperat")
            result = store.execute_plan(plan)

            self.assertEqual(
                result.rows,
                [
                    {
                        "group_key": "2025",
                        "creditare_value": 1000.0,
                        "recuperare_value": 300.0,
                        "transaction_count": 2,
                    },
                    {
                        "group_key": "2026",
                        "creditare_value": 2000.0,
                        "recuperare_value": 500.0,
                        "transaction_count": 2,
                    },
                ],
            )
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_store_execute_plan_groups_house_expenses_by_half_year(self) -> None:
        db_path = ROOT / "test_planner_half_year.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            store.add_classification_rule(
                "description",
                "casa",
                analysis_category="casa",
            )
            store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2024-02-10",
                        description="Chirie casa februarie",
                        amount=-500.0,
                        currency="RON",
                        balance=4500.0,
                        merchant="Locator",
                        source_file="statement.csv",
                        raw_payload='{"id":"h1"}',
                    ),
                    ImportedTransaction(
                        transaction_date="2024-09-03",
                        description="Reparatii casa toamna",
                        amount=-700.0,
                        currency="RON",
                        balance=3800.0,
                        merchant="Meserias",
                        source_file="statement.csv",
                        raw_payload='{"id":"h2"}',
                    ),
                ]
            )

            result = store.execute_plan(build_query_plan("pe jumatate de an, cat am avut cheltuielile cu casa"))

            self.assertEqual(
                result.rows,
                [
                    {"group_key": "2024-H1", "metric_value": 500.0, "transaction_count": 1},
                    {"group_key": "2024-H2", "metric_value": 700.0, "transaction_count": 1},
                ],
            )
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_store_execute_plan_returns_matching_rows_for_entity_search(self) -> None:
        db_path = ROOT / "test_planner_search.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2024-05-20",
                        description="Plata materiale constructii",
                        amount=-150.0,
                        currency="RON",
                        balance=3850.0,
                        merchant="Dedeman",
                        source_file="statement.csv",
                        raw_payload='{"id":"dedeman"}',
                    ),
                    ImportedTransaction(
                        transaction_date="2024-05-21",
                        description="Cafea",
                        amount=-20.0,
                        currency="RON",
                        balance=3830.0,
                        merchant="Coffee Shop",
                        source_file="statement.csv",
                        raw_payload='{"id":"coffee"}',
                    ),
                ]
            )

            result = store.execute_plan(build_query_plan("arata tranzactiile cu Dedeman"))

            self.assertEqual(len(result.rows), 1)
            self.assertEqual(result.rows[0]["merchant"], "Dedeman")
            self.assertEqual(result.rows[0]["amount"], -150.0)
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_store_execute_plan_estimates_operational_income_without_creditari(self) -> None:
        db_path = ROOT / "test_planner_operational_income.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2025-01-10",
                        description="Incasare factura client Alpha",
                        amount=15000.0,
                        currency="RON",
                        balance=15000.0,
                        merchant="Client Alpha",
                        source_file="statement.csv",
                        raw_payload='{"id":"client-income"}',
                    ),
                    ImportedTransaction(
                        transaction_date="2025-02-10",
                        description="Creditare firma asociat",
                        amount=8000.0,
                        currency="RON",
                        balance=23000.0,
                        merchant="Asociat",
                        source_file="statement.csv",
                        raw_payload='{"id":"creditare"}',
                    ),
                    ImportedTransaction(
                        transaction_date="2025-03-10",
                        description="Transfer intern intre conturi",
                        amount=4000.0,
                        currency="RON",
                        balance=27000.0,
                        merchant="Cont propriu",
                        source_file="statement.csv",
                        raw_payload='{"id":"internal"}',
                    ),
                ]
            )

            result = store.execute_plan(build_query_plan("ce cifra de afaceri am avut pe 2025"))

            self.assertEqual(
                result.rows,
                [{"group_key": None, "metric_value": 15000.0, "transaction_count": 1}],
            )
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_store_execute_plan_prefers_issued_invoices_for_turnover(self) -> None:
        db_path = ROOT / "test_planner_invoice_turnover.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2025-01-10",
                        description="Incasare factura client Alpha",
                        amount=5000.0,
                        currency="RON",
                        balance=5000.0,
                        merchant="Client Alpha",
                        source_file="statement.csv",
                        raw_payload='{"id":"client-income"}',
                    )
                ]
            )
            store.insert_issued_invoices(
                [
                    ImportedInvoice(
                        invoice_number="INV-001",
                        issue_date="2025-01-15",
                        customer_name="Client Alpha",
                        net_amount=10000.0,
                        vat_amount=1900.0,
                        total_amount=11900.0,
                        currency="RON",
                        status="issued",
                        source_file="invoices.json",
                        raw_payload='{"invoice_number":"INV-001"}',
                    ),
                    ImportedInvoice(
                        invoice_number="INV-002",
                        issue_date="2025-02-15",
                        customer_name="Client Beta",
                        net_amount=20000.0,
                        vat_amount=3800.0,
                        total_amount=23800.0,
                        currency="RON",
                        status="issued",
                        source_file="invoices.json",
                        raw_payload='{"invoice_number":"INV-002"}',
                    ),
                ]
            )

            result = store.execute_plan(build_query_plan("ce cifra de afaceri am avut pe 2025"))

            self.assertEqual(
                result.rows,
                [
                    {
                        "group_key": None,
                        "metric_value": 30000.0,
                        "transaction_count": 2,
                        "source": "issued_invoices",
                    }
                ],
            )
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_store_execute_plan_returns_received_invoice_residual_total(self) -> None:
        db_path = ROOT / "test_planner_invoice_residual.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            workspace_id = store.create_workspace("MobExc")
            import_batch_id = store.create_document_import_batch(
                source_path=ROOT / "_planner_received_invoice.json",
                workspace_id=workspace_id,
                source_type="received_invoice",
            )
            store.insert_invoices(
                workspace_id=workspace_id,
                import_batch_id=import_batch_id,
                role="received",
                invoices=[
                    ImportedInvoice(
                        invoice_number="R-1000",
                        issue_date="2025-03-01",
                        customer_name="Casa Decor SRL",
                        net_amount=840.34,
                        vat_amount=159.66,
                        total_amount=1000.0,
                        currency="RON",
                        status="issued",
                        source_file="received.json",
                        raw_payload='{"invoice":"R-1000"}',
                    )
                ],
            )
            store.insert_many(
                [
                    ImportedTransaction(
                        transaction_date="2025-03-10",
                        description="Plata partiala factura R-1000",
                        amount=-400.0,
                        currency="RON",
                        balance=4600.0,
                        merchant="Casa Decor SRL",
                        source_file="statement.csv",
                        raw_payload='{"id":"pay-r-1000"}',
                    )
                ],
                workspace_id=workspace_id,
            )
            store.create_invoice_match(
                workspace_id=workspace_id,
                transaction_id=store.list_transactions(workspace_id=workspace_id, limit=1)[0]["id"],
                invoice_id=store.list_workspace_invoices(workspace_id, role="received", limit=1)[0]["id"],
                match_kind="partial_payment",
                matched_amount=400.0,
                residual_amount=600.0,
                confidence=0.9,
                reasoning="seeded for residual query",
            )

            plan = build_query_plan("cat mai am de platit pe facturile primite")
            result = store.execute_plan_for_import(plan, workspace_id=workspace_id)

            self.assertEqual(
                result.rows,
                [
                    {
                        "group_key": None,
                        "metric_value": 600.0,
                        "transaction_count": 1,
                        "source": "received_invoices",
                    }
                ],
            )
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_store_uses_real_invoice_pdfs_for_turnover_by_year(self) -> None:
        invoice_paths = sorted((ROOT / "Date" / "DigExc").glob("f_*.pdf"))
        if not invoice_paths:
            self.skipTest("DigExc invoice PDF fixtures are missing from Date/DigExc.")

        db_path = ROOT / "test_planner_real_invoice_pdf_turnover.sqlite3"
        if db_path.exists():
            db_path.unlink()
        try:
            store = SQLiteTransactionStore(db_path)
            for invoice_path in invoice_paths:
                store.insert_issued_invoices(parse_issued_invoices_path(invoice_path))

            result = store.execute_plan(build_query_plan("ce cifra de afaceri am avut pe 2024/2025"))

            self.assertEqual(
                result.rows,
                [
                    {
                        "group_key": "2024",
                        "metric_value": 63483.01,
                        "transaction_count": 2,
                        "source": "issued_invoices",
                    },
                    {
                        "group_key": "2025",
                        "metric_value": 32864.62,
                        "transaction_count": 1,
                        "source": "issued_invoices",
                    },
                ],
            )
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_render_answer_explains_estimated_operational_metric(self) -> None:
        plan = build_query_plan("ce cifra de afaceri am avut pe 2025")

        answer = render_answer(
            plan,
            [{"group_key": None, "metric_value": 15000.0, "transaction_count": 1}],
        )

        self.assertIn("estimare", answer.lower())
        self.assertIn("cifra de afaceri", answer.lower())

    def test_render_answer_rejects_unsupported_official_metric(self) -> None:
        plan = build_query_plan("cat TVA am de plata pe 2025")

        answer = render_answer(plan, [])

        self.assertIn("nu pot calcula", answer.lower())
        self.assertIn("extras", answer.lower())

    def test_render_answer_summarizes_entity_relationship_question(self) -> None:
        plan = build_query_plan("care e situatia lui Ai Excellence")

        answer = render_answer(
            plan,
            [
                {
                    "group_key": None,
                    "income_total": 3000.0,
                    "expense_total": 1000.0,
                    "net_value": 2000.0,
                    "transaction_count": 2,
                    "entity_type": "partner",
                }
            ],
        )

        self.assertIn("relatia cu ai excellence", answer.lower())
        self.assertIn("incasari 3000.0", answer.lower())
        self.assertIn("plati 1000.0", answer.lower())
        self.assertIn("net 2000.0", answer.lower())
        self.assertIn("ai excellence", answer.lower())

    def test_render_answer_asks_for_clarification_on_generic_situation_question(self) -> None:
        plan = build_query_plan("care e situatia acum")

        answer = render_answer(plan, [])

        self.assertIn("nu sunt sigur", answer.lower())
        self.assertIn("mai specific", answer.lower())

    def test_render_answer_mentions_project_for_entity_relationship_question(self) -> None:
        plan = build_query_plan("care e situatia lui Casa Decor pe proiectul Casa Noua")

        answer = render_answer(
            plan,
            [
                {
                    "group_key": None,
                    "income_total": 0.0,
                    "expense_total": 1900.0,
                    "net_value": -1900.0,
                    "transaction_count": 2,
                    "entity_type": "collaborator",
                }
            ],
        )

        self.assertIn("proiectul casa noua", answer.lower())
        self.assertIn("casa decor", answer.lower())

    def test_render_answer_marks_statement_aggregation_as_exact_line_sum(self) -> None:
        plan = build_query_plan("cat am avut incasari pe 2025")

        answer = render_answer(
            plan,
            [{"group_key": None, "metric_value": 15000.0, "transaction_count": 3}],
        )

        self.assertIn("calcul exact", answer.lower())
        self.assertIn("liniile extrasului", answer.lower())
        self.assertIn("din 3 tranzactii", answer.lower())

    def test_render_answer_marks_grouped_statement_aggregation_as_exact_line_sum(self) -> None:
        plan = build_query_plan("cat am avut incasari pe 2024/2025")

        answer = render_answer(
            plan,
            [
                {"group_key": "2024", "metric_value": 10000.0, "transaction_count": 2},
                {"group_key": "2025", "metric_value": 20000.0, "transaction_count": 5},
            ],
        )

        self.assertIn("calcul exact", answer.lower())
        self.assertIn("2024: 10000.0 (2 tranzactii)", answer)
        self.assertIn("2025: 20000.0 (5 tranzactii)", answer)

    def test_render_answer_creditare_includes_remaining_amount(self) -> None:
        plan = build_query_plan("cat am recuperat din creditare")

        answer = render_answer(
            plan,
            [
                {"group_key": "creditare", "metric_value": 458000.0, "transaction_count": 10},
                {"group_key": "recuperare_creditare", "metric_value": 135000.51, "transaction_count": 5},
            ],
        )

        self.assertIn("ai recuperat 135000.51", answer.lower())
        self.assertIn("ramas de recuperat: 322999.49", answer.lower())

    def test_render_answer_creditare_remaining_focus(self) -> None:
        plan = build_query_plan("cat mai am de recuperat din creditare")

        answer = render_answer(
            plan,
            [
                {"group_key": "creditare", "metric_value": 458000.0, "transaction_count": 10},
                {"group_key": "recuperare_creditare", "metric_value": 135000.51, "transaction_count": 5},
            ],
        )

        self.assertIn("mai ai de recuperat 322999.49", answer.lower())

    def test_render_answer_creditare_grouped_by_year(self) -> None:
        plan = build_query_plan("cati bani am creditat in fiecare an si cati am recuperat")

        answer = render_answer(
            plan,
            [
                {"group_key": "2025", "creditare_value": 1000.0, "recuperare_value": 300.0, "transaction_count": 2},
                {"group_key": "2026", "creditare_value": 2000.0, "recuperare_value": 500.0, "transaction_count": 2},
            ],
        )

        self.assertIn("2025: creditare 1000.0, recuperare 300.0, ramas 700.0", answer.lower())
        self.assertIn("2026: creditare 2000.0, recuperare 500.0, ramas 1500.0", answer.lower())

    def test_render_answer_for_invoice_residual_metric(self) -> None:
        plan = build_query_plan("cat mai am de platit pe facturile primite")

        answer = render_answer(
            plan,
            [{"group_key": None, "metric_value": 600.0, "transaction_count": 1, "source": "received_invoices"}],
        )

        self.assertIn("sold facturi primite neacoperite: 600.0", answer.lower())
        self.assertIn("din 1 facturi", answer.lower())


if __name__ == "__main__":
    unittest.main()
