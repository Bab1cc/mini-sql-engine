import pytest

from minisql.tokenizer import Token, TokenType, TokenizerError, tokenize


def values(sql):
    return [t.value for t in tokenize(sql)]


def test_simple_select():
    assert [(t.type, t.value) for t in tokenize("SELECT name FROM users")] == [
        (TokenType.KEYWORD, "SELECT"),
        (TokenType.IDENTIFIER, "name"),
        (TokenType.KEYWORD, "FROM"),
        (TokenType.IDENTIFIER, "users"),
        (TokenType.EOF, ""),
    ]


def test_keywords_are_case_insensitive():
    tokens = tokenize("select Name from Users")
    assert tokens[0] == Token(TokenType.KEYWORD, "SELECT", 0)
    assert tokens[1].value == "Name"


def test_numbers():
    tokens = tokenize("42 3.14")
    assert (tokens[0].type, tokens[0].value) == (TokenType.NUMBER, 42)
    assert (tokens[1].type, tokens[1].value) == (TokenType.NUMBER, 3.14)


def test_string_literal():
    token = tokenize("'Belgrade'")[0]
    assert (token.type, token.value) == (TokenType.STRING, "Belgrade")


def test_operators():
    assert values("a >= 1 AND b != 2") == ["a", ">=", 1, "AND", "b", "!=", 2, ""]


def test_full_query():
    sql = "SELECT city, COUNT(*) FROM users WHERE age > 30 GROUP BY city;"
    assert values(sql) == [
        "SELECT", "city", ",", "COUNT", "(", "*", ")", "FROM", "users",
        "WHERE", "age", ">", 30, "GROUP", "BY", "city", ";", "",
    ]


def test_unterminated_string_raises():
    with pytest.raises(TokenizerError):
        tokenize("'abc")


def test_unknown_character_raises():
    with pytest.raises(TokenizerError):
        tokenize("SELECT @")