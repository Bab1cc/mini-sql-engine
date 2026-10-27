from minisql.nodes import (BinaryOp, Column, Join, Literal, OrderItem, SelectItem, SelectStatement, Star, UnaryOp, FunctionCall)
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
        table, alias = self.parse_table_ref()

        joins = []
        while True:
            kind = self.parse_join_kind()
            if kind is None:
                break  # no more joins
            join_table, join_alias = self.parse_table_ref()
            self.expect(TokenType.KEYWORD, "ON")
            condition = self.parse_expression()
            joins.append(Join(join_table, join_alias, condition, kind))

        where = None
        if self.match(TokenType.KEYWORD, "WHERE"):
            where = self.parse_expression()

        group_by = []
        if self.match(TokenType.KEYWORD, "GROUP"):
            self.expect(TokenType.KEYWORD, "BY")
            group_by = self.parse_group_by()

        order_by = []
        if self.match(TokenType.KEYWORD, "ORDER"):
            self.expect(TokenType.KEYWORD, "BY")
            order_by = self.parse_order_by()

        limit = None
        if self.match(TokenType.KEYWORD, "LIMIT"):
            limit = self.expect(TokenType.NUMBER).value

        self.match(TokenType.PUNCTUATION, ";")
        self.expect(TokenType.EOF)

        return SelectStatement(columns=columns, table=table, where=where, order_by=order_by, limit=limit, group_by=group_by, alias=alias, joins=joins)

    def parse_select_list(self):
        """Either * or one or more select items separated by commas."""
        # the tokenizer emits * as an OPERATOR token
        if self.match(TokenType.OPERATOR, "*"):
            return [SelectItem(Star())]

        items = [self.parse_select_item()]
        while self.match(TokenType.PUNCTUATION, ","):
            items.append(self.parse_select_item())
        return items

    def parse_table_ref(self):
        """table_name [[AS] alias]   -> returns (name, alias)"""
        name = self.expect(TokenType.IDENTIFIER).value
        if self.match(TokenType.KEYWORD, "AS"):
            # after AS the alias is required
            return name, self.expect(TokenType.IDENTIFIER).value
        if self.check(TokenType.IDENTIFIER):
            # alias without AS: FROM employees e
            return name, self.advance().value
        return name, None

    def parse_join_kind(self):
        """JOIN | INNER JOIN | LEFT [OUTER] JOIN  -> "INNER" / "LEFT", or None if no join follows"""
        if self.match(TokenType.KEYWORD, "JOIN"):
            return "INNER"
        if self.match(TokenType.KEYWORD, "INNER"):
            self.expect(TokenType.KEYWORD, "JOIN")
            return "INNER"
        if self.match(TokenType.KEYWORD, "LEFT"):
            self.match(TokenType.KEYWORD, "OUTER")  # OUTER is optional, LEFT JOIN = LEFT OUTER JOIN
            self.expect(TokenType.KEYWORD, "JOIN")
            return "LEFT"
        return None

    def parse_select_item(self):
        """expression [AS alias]"""
        expr = self.parse_expression()
        alias = None
        if self.match(TokenType.KEYWORD, "AS"):
            alias = self.expect(TokenType.IDENTIFIER).value
        return SelectItem(expr, alias)

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

    def parse_group_by(self):
        """expression (, expression)*"""
        exprs = [self.parse_expression()]
        while self.match(TokenType.PUNCTUATION, ","):
            exprs.append(self.parse_expression())
        return exprs

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
        if self.match(TokenType.KEYWORD, "IS"):
            negated = self.match(TokenType.KEYWORD, "NOT")  # True if there was a NOT
            self.expect(TokenType.KEYWORD, "NULL")
            return UnaryOp("IS NOT NULL" if negated else "IS NULL", left)
        if self.check(TokenType.OPERATOR) and self.peek().value in COMPARISON_OPERATORS:
            op = self.advance().value
            right = self.parse_primary()
            return BinaryOp(op, left, right)
        return left

    def parse_primary(self):
        """NUMBER | STRING | IDENTIFIER | ( expression )"""
        token = self.peek()
        if self.match(TokenType.KEYWORD, "NULL"):
            return Literal(None)

        if token.type in (TokenType.NUMBER, TokenType.STRING):
            self.advance()
            return Literal(token.value)

        if token.type == TokenType.IDENTIFIER:
            self.advance()
            # NAME( ... ) is a function call, a bare NAME is a column
            if self.match(TokenType.PUNCTUATION, "("):
                return self.parse_function_call(token.value)
            # NAME.COLUMN is a qualified column, e.g. e.name
            if self.match(TokenType.PUNCTUATION, "."):
                column_name = self.expect(TokenType.IDENTIFIER).value
                return Column(column_name, table=token.value)
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