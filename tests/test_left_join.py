import pytest

from minisql.catalog import Catalog
from minisql.executor import HashJoin, NestedLoopJoin, Operator, expr_name, run
from minisql.nodes import BinaryOp, Column, Literal, UnaryOp
from minisql.parser import parse


# ---------- Parser ----------

def test_parse_join_kinds():
    assert parse("SELECT * FROM a JOIN b ON a.id = b.id").joins[0].kind == "INNER"
    assert parse("SELECT * FROM a INNER JOIN b ON a.id = b.id").joins[0].kind == "INNER"
    assert parse("SELECT * FROM a LEFT JOIN b ON a.id = b.id").joins[0].kind == "LEFT"
    assert parse("SELECT * FROM a LEFT OUTER JOIN b ON a.id = b.id").joins[0].kind == "LEFT"


def test_parse_is_null_and_is_not_null():
    assert parse("SELECT * FROM t WHERE x IS NULL").where == UnaryOp("IS NULL", Column("x"))
    assert parse("SELECT * FROM t WHERE x IS NOT NULL").where == UnaryOp(
        "IS NOT NULL", Column("x")
    )


def test_parse_null_literal():
    assert parse("SELECT * FROM t WHERE x = NULL").where == BinaryOp(
        "=", Column("x"), Literal(None)
    )


def test_expr_name_for_is_null():
    assert expr_name(UnaryOp("IS NULL", Column("age"))) == "age IS NULL"
    assert expr_name(Literal(None)) == "NULL"


# ---------- Executor ----------

@pytest.fixture
def catalog(tmp_path):
    (tmp_path / "emp.csv").write_text(
        "id,name,department_id\n"
        "1,Ana,1\n"
        "2,Marko,2\n"
        "3,Jovan,1\n"
        "4,Mila,\n"    # no department (NULL)
        "5,Luka,9\n",  # department 9 does not exist
        encoding="utf-8",
    )
    (tmp_path / "dept.csv").write_text(
        "id,name\n"
        "1,Engineering\n"
        "2,Sales\n"
        "3,Support\n",  # nobody works in Support
        encoding="utf-8",
    )
    return Catalog(tmp_path)


def test_left_join_keeps_rows_without_a_match(catalog):
    sql = "SELECT e.name, d.name FROM emp e LEFT JOIN dept d ON e.department_id = d.id"
    assert run(sql, catalog).rows == [
        ["Ana", "Engineering"],
        ["Marko", "Sales"],
        ["Jovan", "Engineering"],
        ["Mila", None],
        ["Luka", None],
    ]


def test_inner_join_keyword_is_the_same_as_join(catalog):
    a = run("SELECT e.name FROM emp e JOIN dept d ON e.department_id = d.id", catalog)
    b = run("SELECT e.name FROM emp e INNER JOIN dept d ON e.department_id = d.id", catalog)
    assert a.rows == b.rows


def test_find_rows_without_a_match(catalog):
    sql = (
        "SELECT e.name FROM emp e LEFT JOIN dept d ON e.department_id = d.id "
        "WHERE d.id IS NULL"
    )
    assert run(sql, catalog).rows == [["Mila"], ["Luka"]]


def test_is_not_null(catalog):
    sql = "SELECT name FROM emp WHERE department_id IS NOT NULL"
    assert run(sql, catalog).rows == [["Ana"], ["Marko"], ["Jovan"], ["Luka"]]


def test_equals_null_never_matches(catalog):
    assert run("SELECT name FROM emp WHERE department_id = NULL", catalog).rows == []


def test_condition_in_on_keeps_left_rows(catalog):
    # In ON: Marko has no matching department, but he is still in the result
    sql = (
        "SELECT e.name, d.name FROM emp e LEFT JOIN dept d "
        "ON e.department_id = d.id AND d.name != 'Sales'"
    )
    assert run(sql, catalog).rows == [
        ["Ana", "Engineering"],
        ["Marko", None],
        ["Jovan", "Engineering"],
        ["Mila", None],
        ["Luka", None],
    ]


def test_condition_in_where_removes_rows(catalog):
    # In WHERE: rows with NULL d.name are removed too (NULL != 'Sales' is NULL)
    sql = (
        "SELECT e.name, d.name FROM emp e LEFT JOIN dept d "
        "ON e.department_id = d.id WHERE d.name != 'Sales'"
    )
    assert run(sql, catalog).rows == [["Ana", "Engineering"], ["Jovan", "Engineering"]]


def test_count_per_department_including_empty_ones(catalog):
    sql = (
        "SELECT d.name, COUNT(e.id) FROM dept d LEFT JOIN emp e ON e.department_id = d.id "
        "GROUP BY d.name ORDER BY d.name"
    )
    assert run(sql, catalog).rows == [["Engineering", 2], ["Sales", 1], ["Support", 0]]


# ---------- Operators directly ----------

class Rows(Operator):
    def __init__(self, rows):
        self.rows = rows

    def __iter__(self):
        yield from self.rows


LEFT = [{"l.k": 1, "l.v": "a"}, {"l.k": 2, "l.v": "b"}]
RIGHT = [{"r.k": 1, "r.w": "x"}]
NULL_ROW = {"r.k": None, "r.w": None}


def test_left_hash_join():
    join = HashJoin(
        Rows(LEFT), Rows(RIGHT), Column("k", table="l"), Column("k", table="r"), "LEFT", NULL_ROW
    )
    assert [(row["l.v"], row["r.w"]) for row in join] == [("a", "x"), ("b", None)]


def test_left_nested_loop_join():
    condition = BinaryOp("=", Column("k", table="l"), Column("k", table="r"))
    join = NestedLoopJoin(Rows(LEFT), Rows(RIGHT), condition, "LEFT", NULL_ROW)
    assert [(row["l.v"], row["r.w"]) for row in join] == [("a", "x"), ("b", None)]