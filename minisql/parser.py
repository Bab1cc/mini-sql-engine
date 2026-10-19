from minisql.nodes import (
    BinaryOp, Column, Literal, OrderItem, SelectItem, SelectStatement, Star, UnaryOp, FunctionCall
)
from minisql.tokenizer import TokenType, tokenize

COMPARISON_OPERATORS = {"=", "!=", "<", ">", "<=", ">="}


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
        """SELECT <select_list> FROM <table> [WHERE <expr>] [LIMIT <number>] [;]"""
        self.expect(TokenType.KEYWORD, "SELECT")
        columns = self.parse_select_list()
        self.expect(TokenType.KEYWORD, "FROM")
        table = self.expect(TokenType.IDENTIFIER).value

        where = None
        if self.match(TokenType.KEYWORD, "WHERE"):
            where = self.parse_expression()

        order_by = []
        if self.match(TokenType.KEYWORD, "ORDER"):
            self.expect(TokenType.KEYWORD, "BY")
            order_by = self.parse_order_by()

        limit = None
        if self.match(TokenType.KEYWORD, "LIMIT"):
            limit = self.expect(TokenType.NUMBER).value

        self.match(TokenType.PUNCTUATION, ";")
        self.expect(TokenType.EOF)

        return SelectStatement(columns=columns, table=table, where=where, order_by=order_by, limit=limit)

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
        """A single item in the SELECT list: any expression."""
        return SelectItem(self.parse_expression())

    def parse_function_call(self, name):
        """Called after NAME( has been read: [* | expr (, expr)*] )"""
        # the tokenizer emits * as an OPERATOR token
        if self.match(TokenType.OPERATOR, "*"):
            args = [Star()]
        else:
            args = [self.parse_expression()]
            while self.match(TokenType.PUNCTUATION, ","):
                args.append(self.parse_expression())
        self.expect(TokenType.PUNCTUATION, ")")
        return FunctionCall(name.upper(), args)  # avg(x) and AVG(x) are the same

    # ---------- Expressions (WHERE conditions) ----------

    def parse_order_by(self):
        """order_item (, order_item)*"""
        items = [self.parse_order_item()]
        while self.match(TokenType.PUNCTUATION, ","):
            items.append(self.parse_order_item())
        return items

    def parse_order_item(self):
        """expression [ASC | DESC]"""
        expr = self.parse_expression()
        if self.match(TokenType.KEYWORD, "DESC"):
            return OrderItem(expr, descending=True)
        self.match(TokenType.KEYWORD, "ASC")  # ASC is the default, so just skip it
        return OrderItem(expr)

    def parse_expression(self):
        """Entry point for any expression."""
        return self.parse_or()

    def parse_or(self):
        """and_expr (OR and_expr)*   (given as an example)"""
        left = self.parse_and()
        while self.match(TokenType.KEYWORD, "OR"):
            right = self.parse_and()
            left = BinaryOp("OR", left, right)
        return left

    def parse_and(self):
        """not_expr (AND not_expr)*"""
        left = self.parse_not()
        while self.match(TokenType.KEYWORD, "AND"):
            right = self.parse_not()
            left = BinaryOp("AND", left, right)
        return left

    def parse_not(self):
        """NOT not_expr  |  comparison"""
        if self.match(TokenType.KEYWORD, "NOT"):
            operand = self.parse_not()
            return UnaryOp("NOT", operand)
        return self.parse_comparison()

    def parse_comparison(self):
        """primary [ (= | != | < | > | <= | >=) primary ]"""
        left = self.parse_primary()
        if self.check(TokenType.OPERATOR) and self.peek().value in COMPARISON_OPERATORS:
            op = self.advance().value
            right = self.parse_primary()
            return BinaryOp(op, left, right)
        return left

    def parse_primary(self):
        """NUMBER | STRING | IDENTIFIER | ( expression )"""
        token = self.peek()

        if token.type in (TokenType.NUMBER, TokenType.STRING):
            self.advance()
            return Literal(token.value)

        if token.type == TokenType.IDENTIFIER:
            self.advance()
            # NAME( ... ) is a function call, a bare NAME is a column
            if self.match(TokenType.PUNCTUATION, "("):
                return self.parse_function_call(token.value)
            return Column(token.value)

        if self.match(TokenType.PUNCTUATION, "("):
            expr = self.parse_expression()  # recursion: a whole expression inside the brackets
            self.expect(TokenType.PUNCTUATION, ")")
            return expr

        found = token.value if token.type != TokenType.EOF else "end of query"
        raise ParseError(
            f"Expected a number, string, identifier, or '(' but found '{found}' "
            f"at position {token.position}"
        )

def parse(sql):
    """Turn a SQL string into a SelectStatement."""
    return Parser(tokenize(sql)).parse_select()