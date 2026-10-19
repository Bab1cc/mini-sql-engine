import pytest

from minisql.catalog import Catalog
from minisql.executor import ExecutionError, collect_columns, expr_name, run
from minisql.nodes import BinaryOp, Column, FunctionCall, Literal, SelectItem, Star, UnaryOp
from minisql.parser import ParseError, parse


# ---------- Parser: function calls ----------

def test_parse_count_star():
    assert parse("SELECT COUNT(*) FROM t").columns == [
        SelectItem(FunctionCall("COUNT", [Star()]))
    ]


def test_parse_function_with_column_and_lowercase_name():
    assert parse("SELECT avg(salary) FROM t").columns == [
        SelectItem(FunctionCall("AVG", [Column("salary")]))
    ]


def test_parse_mixed_select_list():
    assert parse("SELECT city, MAX(age) FROM t").columns == [
        SelectItem(Column("city")),
        SelectItem(FunctionCall("MAX", [Column("age")])),
    ]


def test_parse_unclosed_function_call_raises():
    with pytest.raises(ParseError):
        parse("SELECT COUNT(* FROM t")


# ---------- expr_name ----------

def test_expr_name():
    assert expr_name(Column("age")) == "age"
    assert expr_name(FunctionCall("COUNT", [Star()])) == "COUNT(*)"
    assert expr_name(FunctionCall("AVG", [Column("salary")])) == "AVG(salary)"
    assert expr_name(BinaryOp(">", Column("age"), Literal(30))) == "age > 30"
    assert expr_name(BinaryOp("=", Column("city"), Literal("Nis"))) == "city = 'Nis'"
    assert expr_name(UnaryOp("NOT", Column("active"))) == "NOT active"


# ---------- collect_columns ----------

def test_collect_columns():
    expr = BinaryOp(
        "AND",
        BinaryOp(">", Column("age"), Literal(30)),
        UnaryOp("NOT", BinaryOp("=", Column("city"), Literal("Nis"))),
    )
    assert collect_columns(expr) == {"age", "city"}
    assert collect_columns(FunctionCall("SUM", [Column("salary")])) == {"salary"}
    assert collect_columns(Literal(5)) == set()


# ---------- Executor ----------

@pytest.fixture
def catalog(tmp_path):
    (tmp_path / "users.csv").write_text(
        "id,name,age\n1,Ana,34\n2,Marko,28\n", encoding="utf-8"
    )
    (tmp_path / "empty.csv").write_text("id,name\n", encoding="utf-8")
    return Catalog(tmp_path)


def test_select_expression(catalog):
    result = run("SELECT name, age > 30 FROM users", catalog)
    assert result.columns == ["name", "age > 30"]
    assert result.rows == [["Ana", True], ["Marko", False]]


def test_unknown_column_detected_before_reading_rows(catalog):
    # The table is empty, so the error can only come from validation, not from a row
    with pytest.raises(ExecutionError, match="salary"):
        run("SELECT name FROM empty WHERE salary > 1", catalog)