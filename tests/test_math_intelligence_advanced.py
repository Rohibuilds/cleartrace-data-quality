"""ClearTrace — Advanced Mathematical Intelligence Tests.

Verifies configurable mathematical rules beyond invoice data:
1. Safe AST expression evaluation (security against eval injection).
2. Sum and subtotal aggregation mismatches.
3. Percentage and percentage-change calculation errors.
4. Division-by-zero handling with clean error diagnostics.
5. Missing calculated results and candidate derivation.
6. Domain-specific numeric constraints (non-negative, range, integer-only, column bounds).
7. Statistical outlier candidates (IQR and Z-score).
8. Precision, rounding modes, and tolerance settings.
"""

from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
import pytest
import pandas as pd

from cleartrace.math_engine import (
    SafeExpressionEvaluator,
    DivisionByZeroError,
    inspect_dataset_math,
    quantize_decimal,
)
from cleartrace.models import MathRuleConfig


def test_safe_expression_evaluator_security_and_precision():
    """Verify AST evaluator security: strictly allows safe arithmetic, rejects code injection."""
    evaluator = SafeExpressionEvaluator()

    # 1. Valid safe arithmetic
    ctx = {
        "revenue": Decimal("1000.00"),
        "cogs": Decimal("400.00"),
        "opex": Decimal("250.00"),
        "tax_rate": Decimal("0.20"),
    }
    gross_profit = evaluator.evaluate("revenue - cogs", ctx)
    assert gross_profit == Decimal("600.00")

    net_income = evaluator.evaluate("(revenue - cogs - opex) * (1 - tax_rate)", ctx)
    assert net_income == Decimal("280.0000")

    # 2. Math functions: abs, min, max, round
    ctx_func = {"x": Decimal("-45.67"), "y": Decimal("10.00"), "z": Decimal("20.00")}
    assert evaluator.evaluate("abs(x)", ctx_func) == Decimal("45.67")
    assert evaluator.evaluate("min(y, z)", ctx_func) == Decimal("10.00")
    assert evaluator.evaluate("max(y, z)", ctx_func) == Decimal("20.00")

    # 3. Code injection rejection (Bandit ASVS V5 check)
    with pytest.raises(ValueError, match="Disallowed (expression element|function call)"):
        evaluator.evaluate("__import__('os').system('ls')", ctx)

    with pytest.raises(ValueError, match="Disallowed (expression element|function call)"):
        evaluator.evaluate("open('/etc/passwd')", ctx)

    with pytest.raises(ValueError, match="Disallowed (expression element|function call)"):
        evaluator.evaluate("[x for x in [1, 2, 3]]", ctx)


def test_sum_and_subtotal_mismatches():
    """Verify N-column sum and subtotal aggregation validation."""
    data = pd.DataFrame([
        {"dept": "Engineering", "q1": "100.00", "q2": "150.00", "q3": "120.00", "q4": "130.00", "annual_total": "500.00"},  # Correct: 500
        {"dept": "Marketing",   "q1": "50.00",  "q2": "60.00",  "q3": "70.00",  "q4": "80.00",  "annual_total": "300.00"},   # Error: sum is 260.00, recorded 300.00 (diff +40.00)
    ])

    rule = MathRuleConfig(
        rule_id="annual_budget_sum",
        rule_type="sum",
        target_column="annual_total",
        addend_columns=["q1", "q2", "q3", "q4"],
        tolerance="0.01",
        description="Annual budget must equal the sum of Q1-Q4 quarterly budgets.",
    )

    findings = inspect_dataset_math(data, rules=[rule])
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "SUBTOTAL_MISMATCH"
    assert f.field == "annual_total"
    assert f.observed == "300.00"
    assert f.expected == "260.00"
    assert f.deviation == "40.00"
    assert f.proposed_value == "260.00"
    assert "q1(50.00) + q2(60.00) + q3(70.00) + q4(80.00) = 260.00" in f.calculation_steps


def test_percentage_and_percentage_change_errors():
    """Verify percentage calculation and percentage-change validation."""
    data = pd.DataFrame([
        # Row 1: Valid percentage (25/100 * 100 = 25.00)
        {"id": "rec-1", "sales": "25.00", "total_sales": "100.00", "sales_pct": "25.00", "prev_year": "100.00", "curr_year": "120.00", "yoy_growth": "20.00"},
        # Row 2: Percentage mismatch (40/200 * 100 = 20.00, recorded 25.00)
        {"id": "rec-2", "sales": "40.00", "total_sales": "200.00", "sales_pct": "25.00", "prev_year": "200.00", "curr_year": "250.00", "yoy_growth": "25.00"},
        # Row 3: Percentage change mismatch ((150-100)/100 * 100 = 50.00, recorded 40.00)
        {"id": "rec-3", "sales": "50.00", "total_sales": "100.00", "sales_pct": "50.00", "prev_year": "100.00", "curr_year": "150.00", "yoy_growth": "40.00"},
    ])

    rule_pct = MathRuleConfig(
        rule_id="sales_share_pct",
        rule_type="percentage",
        target_column="sales_pct",
        part_column="sales",
        total_column="total_sales",
        tolerance="0.01",
    )
    rule_growth = MathRuleConfig(
        rule_id="yoy_growth_pct",
        rule_type="percentage_change",
        target_column="yoy_growth",
        old_column="prev_year",
        new_column="curr_year",
        tolerance="0.01",
    )

    findings = inspect_dataset_math(data, rules=[rule_pct, rule_growth])
    assert len(findings) == 2

    pct_finding = next(f for f in findings if f.rule_id == "PERCENTAGE_MISMATCH")
    assert pct_finding.field == "sales_pct"
    assert pct_finding.expected == "20.00"
    assert pct_finding.observed == "25.00"
    assert pct_finding.deviation == "5.00"

    growth_finding = next(f for f in findings if f.rule_id == "PERCENTAGE_CHANGE_MISMATCH")
    assert growth_finding.field == "yoy_growth"
    assert growth_finding.expected == "50.00"
    assert growth_finding.observed == "40.00"
    assert growth_finding.deviation == "-10.00"


def test_division_by_zero_handling():
    """Verify that division by zero in formulas or percentages is gracefully captured and reported."""
    data = pd.DataFrame([
        {"id": "div-zero-1", "numerator": "100.00", "denominator": "0.00", "ratio": "0.00"},
        {"id": "div-zero-2", "part": "50.00", "total": "0.00", "share": "0.00"},
    ])

    rule_formula = MathRuleConfig(
        rule_id="ratio_rule",
        rule_type="formula",
        target_column="ratio",
        expression="numerator / denominator",
    )
    rule_pct = MathRuleConfig(
        rule_id="pct_rule",
        rule_type="percentage",
        target_column="share",
        part_column="part",
        total_column="total",
    )

    findings = inspect_dataset_math(data, rules=[rule_formula, rule_pct])
    div_zero_findings = [f for f in findings if f.rule_id == "DIVISION_BY_ZERO"]
    assert len(div_zero_findings) == 2
    for f in div_zero_findings:
        assert f.rule_id == "DIVISION_BY_ZERO"
        assert f.severity == "High"
        assert f.action == "review"
        assert "division by zero" in f.message.lower()


def test_missing_calculated_results_derivation():
    """Verify that missing calculated cells are derived as candidate proposals."""
    data = pd.DataFrame([
        {"id": "calc-1", "base_price": "100.00", "tax": "15.00", "final_price": None},
        {"id": "calc-2", "base_price": "200.00", "tax": "30.00", "final_price": ""},
    ])

    rule = MathRuleConfig(
        rule_id="final_price_calc",
        rule_type="formula",
        target_column="final_price",
        expression="base_price + tax",
    )

    findings = inspect_dataset_math(data, rules=[rule])
    assert len(findings) == 2
    for idx, f in enumerate(findings):
        assert f.rule_id == "MISSING_CALCULATED_RESULT"
        assert f.action == "fill_calculated"
        expected_val = "115.00" if idx == 0 else "230.00"
        assert f.proposed_value == expected_val


def test_domain_specific_numeric_constraints():
    """Verify non-negative, range, integer-only, and column comparison constraints."""
    data = pd.DataFrame([
        {"id": "c-1", "units": "-5", "discount": "150.00", "subtotal": "100.00", "score": "105"},
        {"id": "c-2", "units": "4.5", "discount": "20.00", "subtotal": "100.00", "score": "85"},
    ])

    rules = [
        MathRuleConfig(rule_id="c_nonneg", rule_type="constraint", target_column="units", constraint_type="non_negative"),
        MathRuleConfig(rule_id="c_int", rule_type="constraint", target_column="units", constraint_type="integer_only"),
        MathRuleConfig(rule_id="c_max", rule_type="constraint", target_column="score", constraint_type="max", constraint_value="100"),
        MathRuleConfig(rule_id="c_col", rule_type="constraint", target_column="discount", constraint_type="less_than_column", constraint_value="subtotal"),
    ]

    findings = inspect_dataset_math(data, rules=rules)
    assert len(findings) == 4
    rule_ids = {f.id for f in findings}
    assert any("mf-constraint-neg" in rid for rid in rule_ids)
    assert any("mf-constraint-int" in rid for rid in rule_ids)
    assert any("mf-constraint-max" in rid for rid in rule_ids)
    assert any("mf-constraint-col" in rid for rid in rule_ids)


def test_statistical_outlier_candidates():
    """Verify statistical outlier candidate detection via IQR and Z-Score."""
    # Data with median around 10 and one obvious outlier 500
    values = [10.0, 11.0, 9.5, 10.5, 10.2, 9.8, 11.2, 10.1, 500.0]
    data = pd.DataFrame([{"id": f"row-{i}", "val": v} for i, v in enumerate(values)])

    rule_iqr = MathRuleConfig(rule_id="outlier_iqr", rule_type="outlier", target_column="val", constraint_type="iqr", constraint_value="1.5")
    rule_z = MathRuleConfig(rule_id="outlier_z", rule_type="outlier", target_column="val", constraint_type="zscore", constraint_value="2.0")

    findings_iqr = inspect_dataset_math(data, rules=[rule_iqr])
    assert len(findings_iqr) == 1
    assert findings_iqr[0].rule_id == "STATISTICAL_OUTLIER"
    assert findings_iqr[0].observed == "500.0"

    findings_z = inspect_dataset_math(data, rules=[rule_z])
    assert len(findings_z) == 1
    assert findings_z[0].rule_id == "STATISTICAL_OUTLIER"
    assert findings_z[0].observed == "500.0"


def test_configurable_precision_and_rounding():
    """Verify configurable decimal precision and rounding modes."""
    val = Decimal("12.34567")
    # Round half up to 2 decimal places -> 12.35
    assert quantize_decimal(val, places=2, mode="ROUND_HALF_UP") == Decimal("12.35")
    # Round down to 2 decimal places -> 12.34
    assert quantize_decimal(val, places=2, mode="ROUND_DOWN") == Decimal("12.34")
    # Round to 4 decimal places -> 12.3457
    assert quantize_decimal(val, places=4, mode="ROUND_HALF_UP") == Decimal("12.3457")
