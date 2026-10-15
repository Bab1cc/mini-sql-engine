from dataclasses import dataclass
from enum import Enum, auto


class TokenType(Enum):
    KEYWORD = auto()
    IDENTIFIER = auto()
    NUMBER = auto()
    STRING = auto()
    OPERATOR = auto()
    PUNCTUATION = auto()
    EOF = auto()  # end of input


KEYWORDS = {
    "SELECT", "FROM", "WHERE", "AND", "OR", "NOT", "GROUP", "BY",
    "ORDER", "ASC", "DESC", "LIMIT", "AS", "JOIN", "ON",
}
OPERATORS = {"=", "!=", "<", ">", "<=", ">=", "+", "-", "*", "/"}
PUNCTUATION = {",", "(", ")", ";", "."}


@dataclass
class Token:
    type: TokenType
    value: str | int | float
    position: int  # index in the SQL string where the token starts


class TokenizerError(Exception):
    pass


def tokenize(sql: str) -> list[Token]:
    """Split a SQL string into a list of tokens, ending with an EOF token."""
    tokens = []
    i = 0  # cursor: index of the character we are currently looking at

    while i < len(sql):
        ch = sql[i]

        # 1. Whitespace: not a token, just move the cursor forward
        if ch.isspace():
            i += 1
            continue

        # 2. Numbers: collect digits (and a decimal point), e.g. 42 or 3.14
        if ch.isdigit():
            start = i
            while i < len(sql) and (sql[i].isdigit() or sql[i] == "."):
                i += 1
            text = sql[start:i]
            value = float(text) if "." in text else int(text)
            tokens.append(Token(TokenType.NUMBER, value, start))
            continue

        # 3. Words: keywords (SELECT, FROM...) or identifiers (column/table names)
        if ch.isalpha() or ch == "_":
            start = i
            while i < len(sql) and (sql[i].isalnum() or sql[i] == "_"):
                i += 1
            text = sql[start:i]
            if text.upper() in KEYWORDS:
                # keywords are stored in uppercase, so "select" == "SELECT"
                tokens.append(Token(TokenType.KEYWORD, text.upper(), start))
            else:
                # identifiers keep their original spelling
                tokens.append(Token(TokenType.IDENTIFIER, text, start))
            continue

        # 4. Strings in single quotes, e.g. 'Belgrade'
        if ch == "'":
            start = i
            i += 1  # skip the opening quote
            while i < len(sql) and sql[i] != "'":
                i += 1
            if i >= len(sql):
                # reached the end of the input without a closing quote
                raise TokenizerError(f"Unterminated string starting at position {start}")
            text = sql[start + 1:i]  # the text between the quotes
            tokens.append(Token(TokenType.STRING, text, start))
            i += 1  # skip the closing quote
            continue

        # 5a. Two-character operators: >=, <=, !=
        #     Checked first, otherwise ">=" would become ">" and "="
        two_chars = sql[i:i + 2]
        if two_chars in OPERATORS:
            tokens.append(Token(TokenType.OPERATOR, two_chars, i))
            i += 2
            continue

        # 5b. One-character operators: =, <, >, +, -, *, /
        if ch in OPERATORS:
            tokens.append(Token(TokenType.OPERATOR, ch, i))
            i += 1
            continue

        # 6. Punctuation: , ( ) ; .
        if ch in PUNCTUATION:
            tokens.append(Token(TokenType.PUNCTUATION, ch, i))
            i += 1
            continue

        # 7. Nothing matched: the character is not valid SQL
        raise TokenizerError(f"Unexpected character '{ch}' at position {i}")

    # End-of-input marker, so the parser always knows where the query ends
    tokens.append(Token(TokenType.EOF, "", len(sql)))
    return tokens