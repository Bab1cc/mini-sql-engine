from minisql.nodes import Column, SelectItem, SelectStatement, Star
from minisql.tokenizer import TokenType, tokenize


class ParseError(Exception):
    pass


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0  # index of the current token

    # ---------- Helper methods (given) ----------

    def peek(self):
        """Return the current token without moving forward."""
        return self.tokens[self.pos]

    def advance(self):
        """Return the current token and move to the next one."""
        token = self.tokens[self.pos]
        if token.type != TokenType.EOF:
            self.pos += 1
        return token

    def check(self, token_type, value=None):
        """Is the current token of this type (and value, if given)?"""
        token = self.peek()
        return token.type == token_type and (value is None or token.value == value)

    def match(self, token_type, value=None):
        """If the current token matches, consume it and return True. Otherwise return False."""
        if self.check(token_type, value):
            self.advance()
            return True
        return False

    def expect(self, token_type, value=None):
        """The current token MUST match: consume and return it, or raise ParseError."""
        if not self.check(token_type, value):
            token = self.peek()
            expected = value if value is not None else token_type.name
            found = token.value if token.type != TokenType.EOF else "end of query"
            raise ParseError(
                f"Expected {expected} but found '{found}' at position {token.position}"
            )
        return self.advance()

    # ---------- Grammar ----------

    def parse_select(self):
        """SELECT <select_list> FROM <table> [LIMIT <number>] [;]"""
        self.expect(TokenType.KEYWORD, "SELECT")
        columns = self.parse_select_list()
        self.expect(TokenType.KEYWORD, "FROM")
        table = self.expect(TokenType.IDENTIFIER).value

        limit = None
        if self.match(TokenType.KEYWORD, "LIMIT"):
            limit = self.expect(TokenType.NUMBER).value

        self.match(TokenType.PUNCTUATION, ";")

        self.expect(TokenType.EOF)

        return SelectStatement(columns=columns, table=table, limit=limit)

    def parse_select_list(self):
        """Either * or one or more select items separated by commas."""
        # the tokenizer emits * as an OPERATOR token
        if self.match(TokenType.OPERATOR, "*"):
            return [SelectItem(Star())]

        items = [self.parse_select_item()]
        while self.match(TokenType.PUNCTUATION, ","):
            items.append(self.parse_select_item())
        return items

    def parse_select_item(self):
        """A single item in the SELECT list (for now: a column name)."""
        name = self.expect(TokenType.IDENTIFIER).value
        return SelectItem(Column(name))

def parse(sql):
    """Turn a SQL string into a SelectStatement."""
    return Parser(tokenize(sql)).parse_select()