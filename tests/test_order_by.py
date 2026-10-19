import pytest

from minisql.catalog import Catalog
from minisql.executor import ExecutionError, run
from minisql.nodes import BinaryOp, Column, Literal, OrderItem
from minisql.parser import ParseError, parse


# ---------- Parser ----------

def test_parse_order_by_default_ascending():
    assert parse("SELECT * FROM t ORDER BY age").order_by == [OrderItem(Column("age"))]


def test_parse_order_by_multiple_with_directions():
    assert parse("SELECT * FROM t ORDER BY city ASC, age DESC").order_by == [
        OrderItem(Column("city")),
        OrderItem(Column("age"), descending=True),
    ]


def test_parse_order_by_with_where_and_limit():
    stmt = parse("SELECT name FROM t WHERE age > 30 ORDER BY age DESC LIMIT 2")
    assert stmt.where == BinaryOp(">", Column("age"), Literal(30))
    assert stmt.order_by == [OrderItem(Column("age"), descending=True)]
    assert stmt.limit == 2


def test_parse_order_without_by_raises():
    with pytest.raises(ParseError):
        parse("SELECT * FROM t ORDER age")


# ---------- Executor ----------

@pytest.fixture
def catalog(tmp_path):
    (tmp_path / "users.csv").write_text(
        "id,name,city,age\n"
        "1,Ana,Belgrade,34\n"
        "2,Marko,Nis,28\n"
        "3,Jovan,Belgrade,41\n"
        "4,Mila,,25\n"  # Mila has no city (NULL)
        "5,Luka,Nis,34\n",
        encoding="utf-8",
    )
    return Catalog(tmp_path)


def names(sql, catalog):
    return [row[0] for row in run(sql, catalog).rows]


def test_order_by_ascending(catalog):
    # Ana and Luka are both 34: they keep their original order (stable sort)
    assert names("SELECT name FROM users ORDER BY age", catalog) == [
        "Mila", "Marko", "Ana", "Luka", "Jovan",
    ]


def test_order_by_descending(catalog):
    assert names("SELECT name FROM users ORDER BY age DESC", catalog) == [
        "Jovan", "Ana", "Luka", "Marko", "Mila",
    ]


def test_order_by_two_columns(catalog):
    # city ascending (NULL last), then age descending inside each city
    assert names("SELECT name FROM users ORDER BY city, age DESC", catalog) == [
        "Jovan", "Ana", "Luka", "Marko", "Mila",
    ]


def test_nulls_first_when_descending(catalog):
    assert names("SELECT name FROM users ORDER BY city DESC", catalog) == [
        "Mila", "Marko", "Luka", "Ana", "Jovan",
    ]


def test_order_by_column_not_in_select(catalog):
    assert names("SELECT name FROM users ORDER BY age DESC LIMIT 2", catalog) == [
        "Jovan", "Ana",
    ]


def test_order_by_after_where(catalog):
    assert names("SELECT name FROM users WHERE city = 'Nis' ORDER BY age", catalog) == [
        "Marko", "Luka",
    ]


def test_sort_runs_before_limit(catalog):
    assert names("SELECT name FROM users ORDER BY age LIMIT 1", catalog) == ["Mila"]


def test_order_by_unknown_column_raises(catalog):
    with pytest.raises(ExecutionError):
        run("SELECT name FROM users ORDER BY salary", catalog)