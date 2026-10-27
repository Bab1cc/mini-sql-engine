import pytest

from minisql.nodes import Column, SelectItem, SelectStatement, Star
from minisql.parser import ParseError, parse


def test_select_star():
    assert parse("SELECT * FROM users") == SelectStatement(
        columns=[SelectItem(Star())], table="users"
    )


def test_select_columns():
    stmt = parse("SELECT name, age FROM users")
    assert stmt.columns == [SelectItem(Column("name")), SelectItem(Column("age"))]
    assert stmt.table == "users"


def test_limit_and_semicolon():
    stmt = parse("SELECT name FROM users LIMIT 10;")
    assert stmt.limit == 10


def test_lowercase_keywords():
    assert parse("select name from users").table == "users"


def test_missing_from_raises():
    with pytest.raises(ParseError):
        parse("SELECT name users")


def test_trailing_garbage_raises():
    with pytest.raises(ParseError):
        parse("SELECT name FROM users u extra")


def test_missing_column_after_comma_raises():
    with pytest.raises(ParseError):
        parse("SELECT name, FROM users")


def test_limit_requires_number():
    with pytest.raises(ParseError):
        parse("SELECT name FROM users LIMIT abc")