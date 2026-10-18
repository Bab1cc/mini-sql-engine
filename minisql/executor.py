import operator
from dataclasses import dataclass

from minisql.nodes import BinaryOp, Column, Literal, Star, UnaryOp
from minisql.parser import parse


class ExecutionError(Exception):
    pass


@dataclass
class Result:
    columns: list  # column names, e.g. ["name", "city"]
    rows: list     # one list of values per row, e.g. [["Marko", "Belgrade"], ...]


# ---------- Operators ----------

class Operator:
    """Base class: every operator produces rows when you iterate over it."""

    def __iter__(self):
        raise NotImplementedError


class Scan(Operator):
    """Reads every row of a table (given as an example)."""

    def __init__(self, table):
        self.table = table

    def __iter__(self):
        for row in self.table.rows:
            yield row

# ---------- Evaluating expressions ----------

# Maps each SQL comparison to a Python function, e.g. ">" -> operator.gt(a, b), which means a > b
COMPARISONS = {
    "=": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    ">": operator.gt,
    "<=": operator.le,
    ">=": operator.ge,
}


def sql_and(left, right):
    """AND with SQL's NULL rules: False wins, then NULL (None), otherwise True."""
    if left is False or right is False:
        return False
    if left is None or right is None:
        return None
    return True


def sql_or(left, right):
    """OR with SQL's NULL rules: True wins, then NULL (None), otherwise False."""
    if left is True or right is True:
        return True
    if left is None or right is None:
        return None
    return False


def evaluate(expr, row):
    """Compute the value of an expression for one row (a dict of column -> value)."""
    if isinstance(expr, Literal):
        return expr.value

    if isinstance(expr, Column):
        if expr.name not in row:
            raise ExecutionError(f"Column '{expr.name}' does not exist")
        return row[expr.name]

    if isinstance(expr, UnaryOp) and expr.op == "NOT":
        value = evaluate(expr.operand, row)
        return None if value is None else not value

    if isinstance(expr, BinaryOp):
        if expr.op == "AND":
            return sql_and(evaluate(expr.left, row), evaluate(expr.right, row))
        if expr.op == "OR":
            return sql_or(evaluate(expr.left, row), evaluate(expr.right, row))

        # Otherwise it is a comparison: =, !=, <, >, <=, >=
        left = evaluate(expr.left, row)
        right = evaluate(expr.right, row)
        if left is None or right is None:
            return None  # comparing with NULL is unknown
        if expr.op in COMPARISONS:
            try:
                return COMPARISONS[expr.op](left, right)
            except TypeError:
                raise ExecutionError(f"Cannot compare {left!r} with {right!r} using '{expr.op}'")

    raise ExecutionError(f"Unsupported expression: {expr}")


class Filter(Operator):
    """Passes through only the rows where the condition is True."""

    def __init__(self, child, condition):
        self.child = child
        self.condition = condition

    def __iter__(self):
        for row in self.child:
            # NULL (None) and False both drop the row
            if evaluate(self.condition, row) is True:
                yield row


class Limit(Operator):
    """Passes through only the first `count` rows."""

    def __init__(self, child, count):
        self.child = child
        self.count = count

    def __iter__(self):
        remaining = self.count  # local copy, so the operator can be iterated again
        if remaining <= 0:
            return
        for row in self.child:
            yield row
            remaining -= 1
            if remaining == 0:
                return  # stop right away, don't pull another row from the child


class Project(Operator):
    """Turns each row (a dict) into a list with only the requested columns, in order."""

    def __init__(self, child, columns):
        self.child = child
        self.columns = columns

    def __iter__(self):
        for row in self.child:
            yield [row[col] for col in self.columns]
        pass


# ---------- Planning and execution ----------

def resolve_columns(stmt, table):
    """Return the list of column names the query asks for."""
    if len(stmt.columns) == 1 and isinstance(stmt.columns[0].expr, Star):
        return list(table.columns)  # a copy, so callers can't change the table's own list

    names = []
    for item in stmt.columns:
        name = item.expr.name
        if name not in table.columns:
            raise ExecutionError(f"Column '{name}' does not exist in table '{table.name}'")
        names.append(name)
    return names


def execute(stmt, catalog):
    """Build the plan of operators for a SelectStatement and run it."""
    table = catalog.get_table(stmt.table)
    columns = resolve_columns(stmt, table)

    plan = Scan(table)
    if stmt.where is not None:
        plan = Filter(plan, stmt.where)
    if stmt.limit is not None:
        plan = Limit(plan, stmt.limit)
    plan = Project(plan, columns)

    return Result(columns, list(plan))


def run(sql, catalog):
    """Parse and execute a SQL string."""
    return execute(parse(sql), catalog)