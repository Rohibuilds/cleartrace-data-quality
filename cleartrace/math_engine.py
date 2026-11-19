"""ClearTrace — Deterministic Mathematical Error Intelligence Engine.

Provides exact Decimal-based arithmetic validation, constraint verification,
statistical anomaly detection, and human-in-the-loop repair proposal generation.
Zero LLM hallucination in calculations: all arithmetic is 100% deterministic.
Supports safe AST evaluation, user-configured column relationships, percentages,
division-by-zero detection, missing results, and statistical outlier candidates.
"""

from __future__ import annotations

import ast
import math
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, ROUND_DOWN, ROUND_UP, ROUND_CEILING, ROUND_FLOOR, DivisionByZero
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple, Union
import pandas as pd

from cleartrace.models import CellDiff, Finding, MathFinding, MathRuleConfig, RepairProposal

DECIMAL_CENTS = Decimal("0.01")
VALID_NUMBER = re.compile(r"^[+-]?(?:\d+(?:\.\d+)?|\d{1,3}(?:,\d{3})+(?:\.\d+)?)$")

ROUNDING_MODES: Dict[str, str] = {
    "ROUND_HALF_UP": ROUND_HALF_UP,
    "ROUND_DOWN": ROUND_DOWN,
    "ROUND_UP": ROUND_UP,
    "ROUND_CEILING": ROUND_CEILING,
    "ROUND_FLOOR": ROUND_FLOOR,
}


class DivisionByZeroError(Exception):
    """Raised when an expression attempts to divide by zero."""
    pass


class SafeExpressionEvaluator(ast.NodeVisitor):
    """Safely evaluates arithmetic expressions using Python AST and Decimal precision.
    
    Guarantees no arbitrary code execution: rejects imports, attributes, loops,
    lambdas, and unapproved function calls.
    """

    ALLOWED_BIN_OPS: Dict[type, Callable[[Decimal, Decimal], Decimal]] = {
        ast.Add: lambda a, b: a + b,
        ast.Sub: lambda a, b: a - b,
        ast.Mult: lambda a, b: a * b,
        ast.Div: lambda a, b: SafeExpressionEvaluator._safe_div(a, b),
        ast.Mod: lambda a, b: SafeExpressionEvaluator._safe_mod(a, b),
        ast.Pow: lambda a, b: a ** b,
    }

    ALLOWED_UNARY_OPS: Dict[type, Callable[[Decimal], Decimal]] = {
        ast.UAdd: lambda a: +a,
        ast.USub: lambda a: -a,
    }

    ALLOWED_FUNCS: Dict[str, Callable[..., Decimal]] = {
        "abs": abs,
        "min": min,
        "max": max,
        "round": lambda v, n=0: round(v, int(n)),
    }

    @staticmethod
    def _safe_div(a: Decimal, b: Decimal) -> Decimal:
        if b == 0:
            raise DivisionByZeroError("Division by zero encountered in formula")
        try:
            return a / b
        except (DivisionByZero, ZeroDivisionError) as exc:
            raise DivisionByZeroError("Division by zero encountered in formula") from exc

    @staticmethod
    def _safe_mod(a: Decimal, b: Decimal) -> Decimal:
        if b == 0:
            raise DivisionByZeroError("Modulo by zero encountered in formula")
        return a % b

    def evaluate(self, expr_str: str, context: Mapping[str, Optional[Decimal]]) -> Decimal:
        """Parse and evaluate an arithmetic expression against a numeric context."""
        try:
            tree = ast.parse(expr_str.strip(), mode="eval")
        except SyntaxError as exc:
            raise ValueError(f"Invalid mathematical expression syntax: '{expr_str}'") from exc
        return self.visit(tree.body, context)

    def visit(self, node: ast.AST, context: Mapping[str, Optional[Decimal]]) -> Decimal:  # type: ignore[override]
        if isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in self.ALLOWED_BIN_OPS:
                raise ValueError(f"Unsupported binary operator in formula: {op_type.__name__}")
            left = self.visit(node.left, context)
            right = self.visit(node.right, context)
            return self.ALLOWED_BIN_OPS[op_type](left, right)

        elif isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in self.ALLOWED_UNARY_OPS:
                raise ValueError(f"Unsupported unary operator in formula: {op_type.__name__}")
            operand = self.visit(node.operand, context)
            return self.ALLOWED_UNARY_OPS[op_type](operand)

        elif isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return Decimal(str(node.value))
            raise ValueError(f"Non-numeric literal in formula: {node.value!r}")

        # Python <3.8 compatibility for ast.Num
        elif hasattr(ast, "Num") and isinstance(node, getattr(ast, "Num")):
            return Decimal(str(getattr(node, "n")))

        elif isinstance(node, ast.Name):
            col_name = node.id
            if col_name not in context:
                raise ValueError(f"Column '{col_name}' referenced in formula was not found in record")
            val = context[col_name]
            if val is None:
                raise ValueError(f"Referenced column '{col_name}' contains null or invalid value")
            return val

        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in self.ALLOWED_FUNCS:
                args = [self.visit(a, context) for a in node.args]
                return self.ALLOWED_FUNCS[node.func.id](*args)
            raise ValueError(f"Disallowed function call in formula: {ast.dump(node.func)}")

        else:
            raise ValueError(f"Disallowed expression element: {type(node).__name__}")


def parse_decimal(raw: Any, *, optional: bool = False) -> Optional[Decimal]:
    """Parse a non-ambiguous decimal value.
    
    Rejects currency symbols, booleans, NaN/Infinity, and locale-ambiguous formats.
    """
    if raw is None or pd.isna(raw) or (isinstance(raw, str) and not raw.strip()):
        if optional:
            return None
        raise ValueError("missing numeric value")
    if isinstance(raw, bool):
        raise ValueError("boolean is not a numeric value")
    s = str(raw).strip()
    if s.lower() in ("nan", "none", "null", "inf", "-inf"):
        if optional:
            return None
        raise ValueError("non-finite numeric value")
    if not VALID_NUMBER.fullmatch(s):
        raise ValueError(f"invalid or locale-ambiguous numeric value: '{s}'")
    try:
        value = Decimal(s.replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError(f"invalid numeric value: '{s}'") from exc
    if not value.is_finite():
        raise ValueError(f"non-finite numeric value: '{s}'")
    return value


def decimal_string(v: Optional[Decimal]) -> Optional[str]:
    """Format Decimal into clean string without scientific notation."""
    return None if v is None else str(v)


def quantize_decimal(
    val: Decimal,
    places: int = 2,
    mode: str = "ROUND_HALF_UP",
) -> Decimal:
    """Quantize decimal value to specified places and rounding mode."""
    exp = Decimal("10") ** (-places)
    r_mode = ROUNDING_MODES.get(mode, ROUND_HALF_UP)
    return val.quantize(exp, rounding=r_mode)


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURABLE GENERAL-PURPOSE MATHEMATICAL VALIDATION ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def inspect_dataset_math(
    data: Union[pd.DataFrame, Iterable[Mapping[str, Any]]],
    *,
    rules: Optional[List[MathRuleConfig]] = None,
    tolerance: Decimal = DECIMAL_CENTS,
    source_name: str = "dataset",
) -> List[MathFinding]:
    """Inspect dataset records against configurable mathematical rules.
    
    Supports:
    - Custom AST arithmetic formulas (e.g. `revenue - cogs - opex = net_income`)
    - Sum / subtotal aggregations (e.g. `col_a + col_b + col_c = total`)
    - Percentages (e.g. `part / total * 100 = pct`)
    - Percentage change (e.g. `(new - old) / old * 100 = pct_change`)
    - Numeric constraints (non_negative, positive, min, max, integer_only, column comparisons)
    - Division-by-zero detection with graceful error reporting
    - Missing calculated result derivations
    - Statistical outlier candidate flagging
    """
    if tolerance < 0:
        raise ValueError("tolerance must be nonnegative")

    findings: List[MathFinding] = []
    evaluator = SafeExpressionEvaluator()

    # Normalize into list of dicts with original row indices
    if isinstance(data, pd.DataFrame):
        df = data.copy()
        records = []
        for idx, row in df.iterrows():
            d = row.to_dict()
            d["_df_idx"] = idx
            records.append(d)
    else:
        records = list(data)
        df = pd.DataFrame(records)

    # If no rules are passed, check if invoice columns are present; if so, run invoice default rule
    if not rules:
        cols = set(df.columns)
        if {"quantity", "unit_price", "recorded_total"}.issubset(cols) or {"qty", "price", "total"}.issubset(cols):
            return inspect_invoice_dataset(data, tolerance=tolerance, source_name=source_name)
        return []

    # Process each rule across all records
    for rule in rules:
        # Pre-calculation for statistical outlier rule
        if rule.rule_type == "outlier" and rule.target_column and rule.target_column in df.columns:
            findings.extend(_inspect_outliers(df, rule, source_name))
            continue

        for idx, row in enumerate(records, start=2):
            df_row_idx = row.get("_df_idx", idx - 2)
            src = str(row.get("_source") or f"{source_name}:row {idx}")
            identifier = str(row.get("id") or row.get("invoice_id") or f"row-{idx}")

            # Parse rule tolerance & quantization
            rule_tol = Decimal(str(rule.tolerance)) if rule.tolerance else tolerance
            r_mode = rule.rounding_mode or "ROUND_HALF_UP"
            d_places = rule.decimal_places if rule.decimal_places is not None else 2

            # ── 1. Formula Rule ──────────────────────────────────────────────
            if rule.rule_type == "formula" and rule.target_column and rule.expression:
                target_col = rule.target_column
                raw_target = row.get(target_col)

                # Extract context variables
                context: Dict[str, Optional[Decimal]] = {}
                context_error: Optional[str] = None
                
                # Find all variable names in expression
                try:
                    tree = ast.parse(rule.expression, mode="eval")
                    var_names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
                except SyntaxError:
                    var_names = set()

                for v in var_names:
                    raw_v = row.get(v)
                    try:
                        context[v] = parse_decimal(raw_v, optional=False)
                    except ValueError as exc:
                        context[v] = None
                        context_error = f"Column '{v}': {exc}"
                        findings.append(
                            MathFinding(
                                id=f"mf-invalid-{rule.rule_id}-{identifier}-{v}",
                                source_ref=src,
                                invoice_id=identifier,
                                rule_id="INVALID_NUMBER",
                                severity=rule.severity,
                                field=v,
                                message=f"Invalid numeric input for formula '{rule.expression}': {exc}",
                                observed=str(raw_v),
                                row_idx=df_row_idx,
                                action="review",
                            )
                        )

                if context_error:
                    continue

                # Safely evaluate formula
                try:
                    raw_expected = evaluator.evaluate(rule.expression, context)
                    expected = quantize_decimal(raw_expected, places=d_places, mode=r_mode)
                except DivisionByZeroError as exc:
                    findings.append(
                        MathFinding(
                            id=f"mf-divzero-{rule.rule_id}-{identifier}-{target_col}",
                            source_ref=src,
                            invoice_id=identifier,
                            rule_id="DIVISION_BY_ZERO",
                            severity="High",
                            field=target_col,
                            message=f"Division by zero in formula '{rule.expression}': {exc}",
                            observed=str(raw_target),
                            expected=None,
                            deviation=None,
                            calculation_steps=f"Expression '{rule.expression}' evaluated with {context} attempted division by zero.",
                            row_idx=df_row_idx,
                            action="review",
                        )
                    )
                    continue
                except ValueError as exc:
                    continue

                calc_steps = f"{rule.expression} evaluated with {context} = {expected}"

                # Target comparison
                try:
                    reported = parse_decimal(raw_target, optional=True)
                except ValueError:
                    reported = None

                if reported is None:
                    findings.append(
                        MathFinding(
                            id=f"mf-missing-{rule.rule_id}-{identifier}-{target_col}",
                            source_ref=src,
                            invoice_id=identifier,
                            rule_id="MISSING_CALCULATED_RESULT",
                            severity="Medium",
                            field=target_col,
                            message=f"Missing calculated result for '{target_col}'. Formula '{rule.expression}' expects {expected}",
                            observed=None,
                            expected=decimal_string(expected),
                            deviation=None,
                            calculation_steps=calc_steps,
                            row_idx=df_row_idx,
                            action="fill_calculated",
                            proposed_value=decimal_string(expected),
                        )
                    )
                else:
                    diff = (reported - expected).quantize(Decimal("10") ** (-d_places))
                    if abs(diff) > rule_tol:
                        findings.append(
                            MathFinding(
                                id=f"mf-mismatch-{rule.rule_id}-{identifier}-{target_col}",
                                source_ref=src,
                                invoice_id=identifier,
                                rule_id="MATH_MISMATCH",
                                severity=rule.severity,
                                field=target_col,
                                message=f"Value ({reported}) does not match formula '{rule.expression}' expected ({expected})",
                                observed=decimal_string(reported),
                                expected=decimal_string(expected),
                                deviation=decimal_string(diff),
                                calculation_steps=f"{calc_steps}. Recorded {reported}. Discrepancy = {diff:+} ({diff})",
                                row_idx=df_row_idx,
                                action="correct_math_mismatch",
                                proposed_value=decimal_string(expected),
                            )
                        )

            # ── 2. Sum Rule ──────────────────────────────────────────────────
            elif rule.rule_type == "sum" and rule.target_column and rule.addend_columns:
                target_col = rule.target_column
                addends = rule.addend_columns
                values = []
                has_error = False

                for col in addends:
                    raw_val = row.get(col)
                    try:
                        v = parse_decimal(raw_val, optional=False)
                        values.append(v)
                    except ValueError:
                        has_error = True
                        break

                if has_error:
                    continue

                total_sum = quantize_decimal(sum(values), places=d_places, mode=r_mode)  # type: ignore[arg-type]
                addends_str = " + ".join(f"{col}({val})" for col, val in zip(addends, values))
                calc_steps = f"{addends_str} = {total_sum}"

                raw_target = row.get(target_col)
                try:
                    reported = parse_decimal(raw_target, optional=True)
                except ValueError:
                    reported = None

                if reported is None:
                    findings.append(
                        MathFinding(
                            id=f"mf-sum-missing-{rule.rule_id}-{identifier}-{target_col}",
                            source_ref=src,
                            invoice_id=identifier,
                            rule_id="MISSING_CALCULATED_RESULT",
                            severity="Medium",
                            field=target_col,
                            message=f"Missing sum total for '{target_col}'. Sum of {addends} expects {total_sum}",
                            observed=None,
                            expected=decimal_string(total_sum),
                            deviation=None,
                            calculation_steps=calc_steps,
                            row_idx=df_row_idx,
                            action="fill_calculated",
                            proposed_value=decimal_string(total_sum),
                        )
                    )
                else:
                    diff = (reported - total_sum).quantize(Decimal("10") ** (-d_places))
                    if abs(diff) > rule_tol:
                        findings.append(
                            MathFinding(
                                id=f"mf-sum-mismatch-{rule.rule_id}-{identifier}-{target_col}",
                                source_ref=src,
                                invoice_id=identifier,
                                rule_id="SUBTOTAL_MISMATCH",
                                severity=rule.severity,
                                field=target_col,
                                message=f"Recorded sum ({reported}) differs from sum of {addends} ({total_sum})",
                                observed=decimal_string(reported),
                                expected=decimal_string(total_sum),
                                deviation=decimal_string(diff),
                                calculation_steps=f"{calc_steps}. Discrepancy = {diff:+}",
                                row_idx=df_row_idx,
                                action="correct_math_mismatch",
                                proposed_value=decimal_string(total_sum),
                            )
                        )

            # ── 3. Percentage Rule ───────────────────────────────────────────
            elif rule.rule_type == "percentage" and rule.target_column and rule.part_column and rule.total_column:
                target_col = rule.target_column
                part_raw = row.get(rule.part_column)
                tot_raw = row.get(rule.total_column)
                try:
                    part_val = parse_decimal(part_raw)
                    tot_val = parse_decimal(tot_raw)
                except ValueError:
                    continue

                if tot_val == 0:
                    findings.append(
                        MathFinding(
                            id=f"mf-pct-divzero-{rule.rule_id}-{identifier}-{target_col}",
                            source_ref=src,
                            invoice_id=identifier,
                            rule_id="DIVISION_BY_ZERO",
                            severity="High",
                            field=target_col,
                            message=f"Cannot compute percentage: total column '{rule.total_column}' is zero (division by zero).",
                            observed=str(row.get(target_col)),
                            expected=None,
                            deviation=None,
                            calculation_steps=f"{rule.part_column}({part_val}) / {rule.total_column}(0) * 100",
                            row_idx=df_row_idx,
                            action="review",
                        )
                    )
                    continue

                raw_pct = (part_val / tot_val) * Decimal("100")  # type: ignore[operator]
                expected_pct = quantize_decimal(raw_pct, places=d_places, mode=r_mode)
                calc_steps = f"{rule.part_column}({part_val}) / {rule.total_column}({tot_val}) × 100 = {expected_pct}%"

                raw_target = row.get(target_col)
                try:
                    reported = parse_decimal(raw_target, optional=True)
                except ValueError:
                    reported = None

                if reported is None:
                    findings.append(
                        MathFinding(
                            id=f"mf-pct-missing-{rule.rule_id}-{identifier}-{target_col}",
                            source_ref=src,
                            invoice_id=identifier,
                            rule_id="MISSING_CALCULATED_RESULT",
                            severity="Medium",
                            field=target_col,
                            message=f"Missing percentage in '{target_col}'. Expected {expected_pct}%",
                            observed=None,
                            expected=decimal_string(expected_pct),
                            deviation=None,
                            calculation_steps=calc_steps,
                            row_idx=df_row_idx,
                            action="fill_calculated",
                            proposed_value=decimal_string(expected_pct),
                        )
                    )
                else:
                    diff = (reported - expected_pct).quantize(Decimal("10") ** (-d_places))
                    if abs(diff) > rule_tol:
                        findings.append(
                            MathFinding(
                                id=f"mf-pct-mismatch-{rule.rule_id}-{identifier}-{target_col}",
                                source_ref=src,
                                invoice_id=identifier,
                                rule_id="PERCENTAGE_MISMATCH",
                                severity=rule.severity,
                                field=target_col,
                                message=f"Recorded percentage ({reported}%) differs from expected {expected_pct}%",
                                observed=decimal_string(reported),
                                expected=decimal_string(expected_pct),
                                deviation=decimal_string(diff),
                                calculation_steps=f"{calc_steps}. Recorded {reported}%. Discrepancy = {diff:+}%",
                                row_idx=df_row_idx,
                                action="correct_math_mismatch",
                                proposed_value=decimal_string(expected_pct),
                            )
                        )

            # ── 4. Percentage Change Rule ────────────────────────────────────
            elif rule.rule_type == "percentage_change" and rule.target_column and rule.old_column and rule.new_column:
                target_col = rule.target_column
                old_raw = row.get(rule.old_column)
                new_raw = row.get(rule.new_column)
                try:
                    old_val = parse_decimal(old_raw)
                    new_val = parse_decimal(new_raw)
                except ValueError:
                    continue

                if old_val == 0:
                    findings.append(
                        MathFinding(
                            id=f"mf-pctchg-divzero-{rule.rule_id}-{identifier}-{target_col}",
                            source_ref=src,
                            invoice_id=identifier,
                            rule_id="DIVISION_BY_ZERO",
                            severity="High",
                            field=target_col,
                            message=f"Cannot compute percentage change: baseline column '{rule.old_column}' is zero.",
                            observed=str(row.get(target_col)),
                            expected=None,
                            deviation=None,
                            calculation_steps=f"({rule.new_column}({new_val}) - {rule.old_column}(0)) / 0 * 100",
                            row_idx=df_row_idx,
                            action="review",
                        )
                    )
                    continue

                raw_change = ((new_val - old_val) / abs(old_val)) * Decimal("100")  # type: ignore[operator]
                expected_change = quantize_decimal(raw_change, places=d_places, mode=r_mode)
                calc_steps = f"({rule.new_column}({new_val}) − {rule.old_column}({old_val})) / |{old_val}| × 100 = {expected_change}%"

                raw_target = row.get(target_col)
                try:
                    reported = parse_decimal(raw_target, optional=True)
                except ValueError:
                    reported = None

                if reported is None:
                    findings.append(
                        MathFinding(
                            id=f"mf-pctchg-missing-{rule.rule_id}-{identifier}-{target_col}",
                            source_ref=src,
                            invoice_id=identifier,
                            rule_id="MISSING_CALCULATED_RESULT",
                            severity="Medium",
                            field=target_col,
                            message=f"Missing percentage change in '{target_col}'. Expected {expected_change}%",
                            observed=None,
                            expected=decimal_string(expected_change),
                            deviation=None,
                            calculation_steps=calc_steps,
                            row_idx=df_row_idx,
                            action="fill_calculated",
                            proposed_value=decimal_string(expected_change),
                        )
                    )
                else:
                    diff = (reported - expected_change).quantize(Decimal("10") ** (-d_places))
                    if abs(diff) > rule_tol:
                        findings.append(
                            MathFinding(
                                id=f"mf-pctchg-mismatch-{rule.rule_id}-{identifier}-{target_col}",
                                source_ref=src,
                                invoice_id=identifier,
                                rule_id="PERCENTAGE_CHANGE_MISMATCH",
                                severity=rule.severity,
                                field=target_col,
                                message=f"Recorded percentage change ({reported}%) differs from expected {expected_change}%",
                                observed=decimal_string(reported),
                                expected=decimal_string(expected_change),
                                deviation=decimal_string(diff),
                                calculation_steps=f"{calc_steps}. Recorded {reported}%. Discrepancy = {diff:+}%",
                                row_idx=df_row_idx,
                                action="correct_math_mismatch",
                                proposed_value=decimal_string(expected_change),
                            )
                        )

            # ── 5. Numeric Constraint Rule ───────────────────────────────────
            elif rule.rule_type == "constraint" and rule.target_column and rule.constraint_type:
                target_col = rule.target_column
                raw_val = row.get(target_col)
                try:
                    val = parse_decimal(raw_val, optional=False)
                except ValueError:
                    continue

                c_type = rule.constraint_type
                if c_type == "non_negative" and val < 0:  # type: ignore[operator]
                    findings.append(
                        MathFinding(
                            id=f"mf-constraint-neg-{rule.rule_id}-{identifier}-{target_col}",
                            source_ref=src,
                            invoice_id=identifier,
                            rule_id="CONSTRAINT_VIOLATION",
                            severity=rule.severity,
                            field=target_col,
                            message=f"Value in '{target_col}' ({val}) violates non-negative constraint (must be >= 0).",
                            observed=decimal_string(val),
                            expected=">= 0",
                            deviation=decimal_string(val),
                            calculation_steps=f"{target_col} = {val} < 0",
                            row_idx=df_row_idx,
                            action="review",
                        )
                    )
                elif c_type == "positive" and val <= 0:  # type: ignore[operator]
                    findings.append(
                        MathFinding(
                            id=f"mf-constraint-pos-{rule.rule_id}-{identifier}-{target_col}",
                            source_ref=src,
                            invoice_id=identifier,
                            rule_id="CONSTRAINT_VIOLATION",
                            severity=rule.severity,
                            field=target_col,
                            message=f"Value in '{target_col}' ({val}) violates positive constraint (must be > 0).",
                            observed=decimal_string(val),
                            expected="> 0",
                            deviation=decimal_string(val),
                            calculation_steps=f"{target_col} = {val} <= 0",
                            row_idx=df_row_idx,
                            action="review",
                        )
                    )
                elif c_type == "integer_only" and val % 1 != 0:  # type: ignore[operator]
                    findings.append(
                        MathFinding(
                            id=f"mf-constraint-int-{rule.rule_id}-{identifier}-{target_col}",
                            source_ref=src,
                            invoice_id=identifier,
                            rule_id="CONSTRAINT_VIOLATION",
                            severity=rule.severity,
                            field=target_col,
                            message=f"Value in '{target_col}' ({val}) has fractional part but must be integer.",
                            observed=decimal_string(val),
                            expected=str(int(val)),  # type: ignore[arg-type]
                            deviation=decimal_string(val % 1),  # type: ignore[operator]
                            calculation_steps=f"{target_col} = {val} is not an integer",
                            row_idx=df_row_idx,
                            action="review",
                        )
                    )
                elif c_type == "min" and rule.constraint_value:
                    min_val = Decimal(str(rule.constraint_value))
                    if val < min_val:  # type: ignore[operator]
                        findings.append(
                            MathFinding(
                                id=f"mf-constraint-min-{rule.rule_id}-{identifier}-{target_col}",
                                source_ref=src,
                                invoice_id=identifier,
                                rule_id="CONSTRAINT_VIOLATION",
                                severity=rule.severity,
                                field=target_col,
                                message=f"Value in '{target_col}' ({val}) is below minimum limit ({min_val}).",
                                observed=decimal_string(val),
                                expected=f">= {min_val}",
                                deviation=decimal_string(val - min_val),  # type: ignore[operator]
                                calculation_steps=f"{target_col} = {val} < {min_val}",
                                row_idx=df_row_idx,
                                action="review",
                            )
                        )
                elif c_type == "max" and rule.constraint_value:
                    max_val = Decimal(str(rule.constraint_value))
                    if val > max_val:  # type: ignore[operator]
                        findings.append(
                            MathFinding(
                                id=f"mf-constraint-max-{rule.rule_id}-{identifier}-{target_col}",
                                source_ref=src,
                                invoice_id=identifier,
                                rule_id="CONSTRAINT_VIOLATION",
                                severity=rule.severity,
                                field=target_col,
                                message=f"Value in '{target_col}' ({val}) exceeds maximum limit ({max_val}).",
                                observed=decimal_string(val),
                                expected=f"<= {max_val}",
                                deviation=decimal_string(val - max_val),  # type: ignore[operator]
                                calculation_steps=f"{target_col} = {val} > {max_val}",
                                row_idx=df_row_idx,
                                action="review",
                            )
                        )
                elif c_type == "less_than_column" and rule.constraint_value in row:
                    other_col = rule.constraint_value
                    try:
                        other_val = parse_decimal(row.get(other_col))
                    except ValueError:
                        other_val = None
                    if other_val is not None and val > other_val:  # type: ignore[operator]
                        findings.append(
                            MathFinding(
                                id=f"mf-constraint-col-{rule.rule_id}-{identifier}-{target_col}",
                                source_ref=src,
                                invoice_id=identifier,
                                rule_id="CONSTRAINT_VIOLATION",
                                severity=rule.severity,
                                field=target_col,
                                message=f"Value in '{target_col}' ({val}) exceeds upper-bound column '{other_col}' ({other_val}).",
                                observed=decimal_string(val),
                                expected=f"<= {other_val}",
                                deviation=decimal_string(val - other_val),  # type: ignore[operator]
                                calculation_steps=f"{target_col}({val}) > {other_col}({other_val})",
                                row_idx=df_row_idx,
                                action="review",
                            )
                        )

    return findings


def _inspect_outliers(
    df: pd.DataFrame,
    rule: MathRuleConfig,
    source_name: str,
) -> List[MathFinding]:
    """Flag candidate statistical outliers using IQR or Z-Score."""
    findings: List[MathFinding] = []
    col = rule.target_column
    if not col or col not in df.columns:
        return findings

    # Extract valid numeric series
    series = pd.to_numeric(df[col], errors="coerce").dropna()
    if len(series) < 4:
        return findings

    threshold = float(rule.constraint_value or (1.5 if rule.constraint_type == "iqr" else 3.0))

    if rule.constraint_type == "zscore":
        mean = series.mean()
        std = series.std(ddof=1)
        if std == 0 or math.isnan(std):
            return findings
        for idx, val in series.items():
            z = abs((val - mean) / std)
            if z > threshold:
                src = f"{source_name}:row {idx + 2}"
                identifier = str(df.at[idx, "id"] if "id" in df.columns else f"row-{idx + 2}")
                findings.append(
                    MathFinding(
                        id=f"mf-outlier-z-{col}-{idx}",
                        source_ref=src,
                        invoice_id=identifier,
                        rule_id="STATISTICAL_OUTLIER",
                        severity="Low",
                        field=col,
                        message=f"Statistical outlier candidate: {col}={val} has Z-score {z:.2f} (> {threshold}).",
                        observed=str(val),
                        expected=f"Mean={mean:.2f} ± {threshold}×Std({std:.2f})",
                        deviation=f"{val - mean:+.2f}",
                        calculation_steps=f"Z = |{val} - {mean:.2f}| / {std:.2f} = {z:.2f} > {threshold}",
                        row_idx=int(idx),
                        action="review",
                    )
                )
    else:  # Default IQR
        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            return findings
        lower_bound = q1 - threshold * iqr
        upper_bound = q3 + threshold * iqr

        for idx, val in series.items():
            if val < lower_bound or val > upper_bound:
                src = f"{source_name}:row {idx + 2}"
                identifier = str(df.at[idx, "id"] if "id" in df.columns else f"row-{idx + 2}")
                bound_violated = f"< {lower_bound:.2f}" if val < lower_bound else f"> {upper_bound:.2f}"
                findings.append(
                    MathFinding(
                        id=f"mf-outlier-iqr-{col}-{idx}",
                        source_ref=src,
                        invoice_id=identifier,
                        rule_id="STATISTICAL_OUTLIER",
                        severity="Low",
                        field=col,
                        message=f"Statistical outlier candidate: {col}={val} falls outside IQR bounds ({lower_bound:.2f} to {upper_bound:.2f}).",
                        observed=str(val),
                        expected=f"[{lower_bound:.2f}, {upper_bound:.2f}]",
                        deviation=f"{val - (upper_bound if val > upper_bound else lower_bound):+.2f}",
                        calculation_steps=f"IQR = {iqr:.2f}; Bounds = [{lower_bound:.2f}, {upper_bound:.2f}]; Recorded {val} {bound_violated}",
                        row_idx=int(idx),
                        action="review",
                    )
                )

    return findings


# ─────────────────────────────────────────────────────────────────────────────
# INVOICE INVARIANT ENGINE (BACKWARD COMPATIBLE & GROUND TRUTH VALIDATOR)
# ─────────────────────────────────────────────────────────────────────────────

def inspect_invoice_dataset(
    data: Union[pd.DataFrame, Iterable[Mapping[str, Any]]],
    *,
    tolerance: Decimal = DECIMAL_CENTS,
    source_name: str = "dataset",
) -> List[MathFinding]:
    """Inspect invoice dataset rows against deterministic mathematical and constraint rules.
    
    Rule: expected_total = quantity * unit_price - discount + tax.
    Evaluated with exact decimal arithmetic and rounding.
    """
    if tolerance < 0:
        raise ValueError("tolerance must be nonnegative")

    findings: List[MathFinding] = []

    # Normalize input into list of dicts with original row indices
    if isinstance(data, pd.DataFrame):
        records = []
        for idx, row in data.iterrows():
            d = row.to_dict()
            d["_df_idx"] = idx
            records.append(d)
    else:
        records = list(data)

    for idx, row in enumerate(records, start=2):
        df_row_idx = row.get("_df_idx", idx - 2)
        src = str(row.get("_source") or f"{source_name}:row {idx}")
        identifier = str(row.get("invoice_id") or f"row-{idx}")
        values: Dict[str, Optional[Decimal]] = {}

        for field in ("quantity", "unit_price", "discount", "tax", "recorded_total"):
            raw = row.get(field)
            try:
                values[field] = parse_decimal(raw, optional=(field == "recorded_total"))
            except ValueError as exc:
                findings.append(
                    MathFinding(
                        id=f"mf-inv-num-{identifier}-{field}",
                        source_ref=src,
                        invoice_id=identifier,
                        rule_id="INVALID_NUMBER",
                        severity="High",
                        field=field,
                        message=f"{field}: {exc}",
                        observed=str(raw),
                        row_idx=df_row_idx,
                        action="edit",
                    )
                )
                values[field] = None

        qty, price, discount, tax, reported = (
            values["quantity"],
            values["unit_price"],
            values["discount"],
            values["tax"],
            values["recorded_total"],
        )

        # 1. Non-negative constraint checks
        for field in ("quantity", "unit_price", "discount", "tax"):
            val = values[field]
            if val is not None and val < 0:
                findings.append(
                    MathFinding(
                        id=f"mf-neg-{identifier}-{field}",
                        source_ref=src,
                        invoice_id=identifier,
                        rule_id="NEGATIVE_NOT_ALLOWED",
                        severity="High",
                        field=field,
                        message=f"{field} cannot be negative under invoice rules",
                        observed=decimal_string(val),
                        row_idx=df_row_idx,
                        action="review",
                    )
                )

        # 2. Arithmetic & Subtotal checks if core variables are valid
        if None not in (qty, price, discount, tax):
            gross = qty * price  # type: ignore[operator]
            # Discount exceeds subtotal
            if qty >= 0 and price >= 0 and discount > gross:  # type: ignore[operator]
                findings.append(
                    MathFinding(
                        id=f"mf-disc-{identifier}",
                        source_ref=src,
                        invoice_id=identifier,
                        rule_id="DISCOUNT_EXCEEDS_SUBTOTAL",
                        severity="High",
                        field="discount",
                        message=f"Discount ({discount}) exceeds gross subtotal quantity × unit_price ({gross})",
                        observed=decimal_string(discount),
                        expected=decimal_string(gross),
                        deviation=decimal_string(discount - gross),  # type: ignore[operator]
                        calculation_steps=f"{qty} × {price} = {gross}; discount {discount} > {gross}",
                        row_idx=df_row_idx,
                        action="review",
                    )
                )

            expected = (gross - discount + tax).quantize(DECIMAL_CENTS, rounding=ROUND_HALF_UP)  # type: ignore[operator]
            calc_steps = f"{qty} × {price} − {discount} + {tax} = {expected}"

            raw_total = row.get("recorded_total")
            if reported is None and (raw_total is None or pd.isna(raw_total) or not str(raw_total).strip() or str(raw_total).strip().lower() in ("nan", "none", "null")):
                findings.append(
                    MathFinding(
                        id=f"mf-miss-{identifier}",
                        source_ref=src,
                        invoice_id=identifier,
                        rule_id="MISSING_TOTAL",
                        severity="Medium",
                        field="recorded_total",
                        message=f"Reported total is missing; calculated expected total is {expected}",
                        observed=None,
                        expected=decimal_string(expected),
                        deviation=None,
                        calculation_steps=calc_steps,
                        row_idx=df_row_idx,
                        action="fill_calculated",
                        proposed_value=decimal_string(expected),
                    )
                )
            elif reported is not None:
                diff = (reported - expected).quantize(DECIMAL_CENTS)
                if abs(diff) > tolerance:
                    findings.append(
                        MathFinding(
                            id=f"mf-math-{identifier}",
                            source_ref=src,
                            invoice_id=identifier,
                            rule_id="MATH_MISMATCH",
                            severity="High",
                            field="recorded_total",
                            message=f"Reported total ({reported}) does not match formula quantity × unit_price − discount + tax ({expected})",
                            observed=decimal_string(reported),
                            expected=decimal_string(expected),
                            deviation=decimal_string(diff),
                            calculation_steps=f"{qty} × {price} − {discount} + {tax} = {expected}. Recorded {reported}. Discrepancy = {diff:+} ({diff})",
                            row_idx=df_row_idx,
                            action="correct_math_mismatch",
                            proposed_value=decimal_string(expected),
                        )
                    )

    return findings


def convert_math_findings_to_proposals(
    findings: List[MathFinding],
    df: pd.DataFrame,
) -> List[Tuple[Finding, RepairProposal]]:
    """Convert actionable MathFindings into ClearTrace standard Findings and RepairProposals."""
    results: List[Tuple[Finding, RepairProposal]] = []

    for mf in findings:
        if not mf.proposed_value or mf.field not in df.columns:
            continue

        finding_id = f"finding-math-{mf.invoice_id}-{mf.field}"
        std_finding = Finding(
            id=finding_id,
            rule_id=f"math_{mf.rule_id.lower()}",
            kind=f"Math Discrepancy ({mf.rule_id})",
            column=mf.field,
            affected_count=1,
            affected_row_indices=[mf.row_idx],
            example=f"Observed: {mf.observed} → Expected: {mf.expected}",
            explanation=f"{mf.message}. Calculation steps: {mf.calculation_steps}",
            recommendation=f"Update {mf.field} to calculated value {mf.proposed_value}.",
            risk=mf.severity,
            action=mf.action,
            payload={
                "invoice_id": mf.invoice_id,
                "source_ref": mf.source_ref,
                "expected": mf.expected,
                "observed": mf.observed,
                "deviation": mf.deviation,
                "calculation_steps": mf.calculation_steps,
                "proposed_value": mf.proposed_value,
            },
        )

        diff = CellDiff(
            row_idx=mf.row_idx,
            column=mf.field,
            before=df.at[mf.row_idx, mf.field] if mf.row_idx in df.index else mf.observed,
            after=mf.proposed_value,
        )

        proposal = RepairProposal(
            proposal_id=f"prop-math-{mf.invoice_id}-{mf.field}",
            finding_id=finding_id,
            rule_id=std_finding.rule_id,
            column=mf.field,
            target_rows=[mf.row_idx],
            before_summary=f"{mf.field}={diff.before}",
            after_summary=f"{mf.field}={diff.after} (Calculated)",
            diff_sample=[diff],
            risk=mf.severity,
            explanation=f"Replace discrepancy with verified arithmetic calculation: {mf.calculation_steps}",
            status="Proposed",
        )

        results.append((std_finding, proposal))

    return results
