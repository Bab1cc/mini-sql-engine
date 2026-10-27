import pytest

from minisql.catalog import Catalog
from minisql.executor import Avg, Count, ExecutionError, Max, Min, run
from minisql.nodes import Column
from minisql.parser import parse


# ---------- Parser ----------

def test_parse_group_by():
    stmt = parse("SELECT city, COUNT(*) FROM t GROUP BY city ORDER BY city")
    assert stmt.group_by == [Column("city")]


# ---------- Accumulators ----------

def feed(accumulator, values):
    for value in values:
        accumulator.add(value)
    return accumulator.result()


def test_count_ignores_null():
    assert feed(Count(), [5, None, 7]) == 2


def test_avg():
    assert feed(Avg(), [10, 20, None, 30]) == 20
    assert feed(Avg(), []) is None


def test_min_and_max():
    assert feed(Min(), [3, None, 1, 2]) == 1
    assert feed(Max(), [3, None, 1, 2]) == 3
    assert feed(Max(), [None, None]) is None


# ---------- Executor ----------

@pytest.fixture
def catalog(tmp_path):
    (tmp_path / "users.csv").write_text(
        "id,name,city,age,salary\n"
        "1,Ana,Belgrade,34,1500\n"
        "2,Marko,Nis,28,1200\n"
        "3,Jovan,Belgrade,41,2100\n"
        "4,Mila,Nis,25,\n"  # Mila has no salary (NULL)
        "5,Luka,Belgrade,30,1800\n",
        encoding="utf-8",
    )
    (tmp_path / "empty.csv").write_text("id,salary\n", encoding="utf-8")
    return Catalog(tmp_path)


def test_count_star_without_group_by(catalog):
    result = run("SELECT COUNT(*) FROM users", catalog)
    assert result.columns == ["COUNT(*)"]
    assert result.rows == [[5]]


def test_aggregates_on_empty_table(catalog):
    result = run("SELECT COUNT(*), SUM(salary) FROM empty", catalog)
    assert result.rows == [[0, None]]


def test_group_by_with_several_aggregates(catalog):
    sql = (
        "SELECT city, COUNT(*), COUNT(salary), SUM(salary), MIN(age), MAX(age) "
        "FROM users GROUP BY city ORDER BY city"
    )
    result = run(sql, catalog)
    assert result.columns == [
        "city", "COUNT(*)", "COUNT(salary)", "SUM(salary)", "MIN(age)", "MAX(age)",
    ]
    assert result.rows == [
        ["Belgrade", 3, 3, 5400, 30, 41],
        ["Nis", 2, 1, 1200, 25, 28],
    ]


def test_avg_ignores_null(catalog):
    result = run("SELECT city, AVG(salary) FROM users GROUP BY city ORDER BY city", catalog)
    assert result.rows == [["Belgrade", 1800.0], ["Nis", 1200.0]]


def test_where_runs_before_grouping(catalog):
    sql = "SELECT city, COUNT(*) FROM users WHERE age > 29 GROUP BY city"
    assert run(sql, catalog).rows == [["Belgrade", 3]]


def test_order_by_aggregate(catalog):
    sql = "SELECT city, COUNT(*) FROM users GROUP BY city ORDER BY COUNT(*) DESC LIMIT 1"
    assert run(sql, catalog).rows == [["Belgrade", 3]]


def test_column_not_in_group_by_raises(catalog):
    with pytest.raises(ExecutionError, match="GROUP BY"):
        run("SELECT name, COUNT(*) FROM users GROUP BY city", catalog)


def test_aggregate_in_where_raises(catalog):
    with pytest.raises(ExecutionError):
        run("SELECT name FROM users WHERE COUNT(*) > 1", catalog)


def test_unknown_function_raises(catalog):
    with pytest.raises(ExecutionError, match="FOO"):
        run("SELECT FOO(age) FROM users", catalog)