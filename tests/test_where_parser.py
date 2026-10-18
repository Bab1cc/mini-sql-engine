import pytest

from minisql.nodes import BinaryOp, Column, Literal, UnaryOp
from minisql.parser import ParseError, parse


def where(sql):
    return parse(sql).where


def test_where_comparison():
    assert where("SELECT * FROM users WHERE age > 30") == BinaryOp(
        ">", Column("age"), Literal(30)
    )


def test_where_string_literal():
    assert where("SELECT * FROM users WHERE city = 'Belgrade'") == BinaryOp(
        "=", Column("city"), Literal("Belgrade")
    )


def test_and_binds_tighter_than_or():
    assert where("SELECT * FROM t WHERE a = 1 OR b = 2 AND c = 3") == BinaryOp(
        "OR",
        BinaryOp("=", Column("a"), Literal(1)),
        BinaryOp(
            "AND",
            BinaryOp("=", Column("b"), Literal(2)),
            BinaryOp("=", Column("c"), Literal(3)),
        ),
    )


def test_parentheses_override_precedence():
    assert where("SELECT * FROM t WHERE (a = 1 OR b = 2) AND c = 3") == BinaryOp(
        "AND",
        BinaryOp(
            "OR",
            BinaryOp("=", Column("a"), Literal(1)),
            BinaryOp("=", Column("b"), Literal(2)),
        ),
        BinaryOp("=", Column("c"), Literal(3)),
    )


def test_not():
    assert where("SELECT * FROM t WHERE NOT a = 1") == UnaryOp(
        "NOT", BinaryOp("=", Column("a"), Literal(1))
    )


def test_where_with_limit():
    stmt = parse("SELECT name FROM users WHERE age >= 18 LIMIT 5")
    assert stmt.where == BinaryOp(">=", Column("age"), Literal(18))
    assert stmt.limit == 5


def test_no_where():
    assert where("SELECT * FROM users") is None


def test_unclosed_parenthesis_raises():
    with pytest.raises(ParseError):
        parse("SELECT * FROM t WHERE (a = 1")


def test_missing_right_side_raises():
    with pytest.raises(ParseError):
        parse("SELECT * FROM t WHERE a >")