import pytest

from minisql.catalog import Catalog
from minisql.executor import ExecutionError, HashJoin, NestedLoopJoin, Operator, run
from minisql.nodes import BinaryOp, Column


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


def test_join(catalog):
    result = run(
        "SELECT e.name, d.name AS department FROM emp e JOIN dept d ON e.department_id = d.id",
        catalog,
    )
    assert result.columns == ["name", "department"]
    assert result.rows == [
        ["Ana", "Engineering"],
        ["Marko", "Sales"],
        ["Jovan", "Engineering"],
    ]


def test_join_condition_written_the_other_way(catalog):
    sql = "SELECT e.name, d.name FROM emp e JOIN dept d ON d.id = e.department_id"
    assert [row[0] for row in run(sql, catalog).rows] == ["Ana", "Marko", "Jovan"]


def test_join_with_complex_condition(catalog):
    sql = (
        "SELECT e.name FROM emp e JOIN dept d "
        "ON e.department_id = d.id AND d.name != 'Sales'"
    )
    assert run(sql, catalog).rows == [["Ana"], ["Jovan"]]


def test_join_with_where_and_order_by(catalog):
    sql = (
        "SELECT e.name FROM emp e JOIN dept d ON e.department_id = d.id "
        "WHERE d.name = 'Engineering' ORDER BY e.name DESC"
    )
    assert run(sql, catalog).rows == [["Jovan"], ["Ana"]]


def test_join_with_group_by(catalog):
    sql = (
        "SELECT d.name, COUNT(*) FROM emp e JOIN dept d ON e.department_id = d.id "
        "GROUP BY d.name ORDER BY d.name"
    )
    assert run(sql, catalog).rows == [["Engineering", 2], ["Sales", 1]]


def test_unqualified_column_is_fine_when_unique(catalog):
    sql = "SELECT e.name FROM emp e JOIN dept d ON department_id = d.id"
    assert run(sql, catalog).rows == [["Ana"], ["Marko"], ["Jovan"]]


def test_self_join(catalog):
    sql = (
        "SELECT a.name, b.name FROM emp a JOIN emp b "
        "ON a.department_id = b.department_id AND a.id < b.id"
    )
    assert run(sql, catalog).rows == [["Ana", "Jovan"]]


def test_select_star_in_join(catalog):
    result = run("SELECT * FROM emp e JOIN dept d ON e.department_id = d.id", catalog)
    assert result.columns == ["id", "name", "department_id", "id", "name"]
    assert result.rows[0] == [1, "Ana", 1, 1, "Engineering"]


def test_ambiguous_column_raises(catalog):
    with pytest.raises(ExecutionError, match="ambiguous"):
        run("SELECT name FROM emp e JOIN dept d ON e.department_id = d.id", catalog)


def test_unknown_alias_raises(catalog):
    with pytest.raises(ExecutionError, match="x"):
        run("SELECT x.name FROM emp e JOIN dept d ON e.department_id = d.id", catalog)


# ---------- The two join algorithms directly ----------

class Rows(Operator):
    """A tiny in-memory table for testing operators directly."""

    def __init__(self, rows):
        self.rows = rows

    def __iter__(self):
        yield from self.rows


LEFT = [{"l.k": 1, "l.v": "a"}, {"l.k": 2, "l.v": "b"}, {"l.k": None, "l.v": "c"}]
RIGHT = [{"r.k": 1, "r.w": "x"}, {"r.k": 1, "r.w": "y"}, {"r.k": None, "r.w": "z"}]


def test_hash_join_matches_duplicates_and_skips_null():
    join = HashJoin(Rows(LEFT), Rows(RIGHT), Column("k", table="l"), Column("k", table="r"))
    assert [(row["l.v"], row["r.w"]) for row in join] == [("a", "x"), ("a", "y")]


def test_nested_loop_join_gives_same_result():
    condition = BinaryOp("=", Column("k", table="l"), Column("k", table="r"))
    join = NestedLoopJoin(Rows(LEFT), Rows(RIGHT), condition)
    assert [(row["l.v"], row["r.w"]) for row in join] == [("a", "x"), ("a", "y")]