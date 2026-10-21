import pytest

from minisql.catalog import Catalog
from minisql.executor import ExecutionError, run
from minisql.nodes import BinaryOp, Column, Join, Literal, SelectItem
from minisql.parser import ParseError, parse


def test_select_alias():
    assert parse("SELECT name AS employee FROM t").columns == [
        SelectItem(Column("name"), alias="employee")
    ]


def test_qualified_column():
    assert parse("SELECT e.name FROM employees e").columns == [
        SelectItem(Column("name", table="e"))
    ]


def test_table_alias_with_and_without_as():
    assert parse("SELECT * FROM employees e").alias == "e"
    assert parse("SELECT * FROM employees AS e").alias == "e"
    assert parse("SELECT * FROM employees").alias is None


def test_join():
    stmt = parse(
        "SELECT e.name, d.name AS department "
        "FROM employees e JOIN departments d ON e.department_id = d.id"
    )
    assert stmt.table == "employees"
    assert stmt.alias == "e"
    assert stmt.joins == [
        Join(
            "departments",
            "d",
            BinaryOp("=", Column("department_id", table="e"), Column("id", table="d")),
        )
    ]


def test_join_followed_by_where():
    stmt = parse("SELECT * FROM a JOIN b ON a.id = b.a_id WHERE b.x > 1")
    assert len(stmt.joins) == 1
    assert stmt.where == BinaryOp(">", Column("x", table="b"), Literal(1))


def test_join_without_on_raises():
    with pytest.raises(ParseError):
        parse("SELECT * FROM a JOIN b")


def test_alias_without_name_raises():
    with pytest.raises(ParseError):
        parse("SELECT name AS FROM t")


@pytest.fixture
def catalog(tmp_path):
    (tmp_path / "users.csv").write_text(
        "id,name,age\n1,Ana,34\n2,Marko,28\n", encoding="utf-8"
    )
    return Catalog(tmp_path)


def test_select_alias_is_used_as_header(catalog):
    result = run("SELECT name AS employee FROM users", catalog)
    assert result.columns == ["employee"]
    assert result.rows == [["Ana"], ["Marko"]]


def test_qualified_column_on_single_table(catalog):
    result = run("SELECT u.name FROM users u WHERE u.age > 30", catalog)
    assert result.rows == [["Ana"]]


def test_join_is_not_executed_yet(catalog):
    with pytest.raises(ExecutionError):
        run("SELECT * FROM users a JOIN users b ON a.id = b.id", catalog)