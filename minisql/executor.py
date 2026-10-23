from ast import expr
import operator
from dataclasses import dataclass

from minisql.nodes import (BinaryOp, Column, FunctionCall, Literal, SelectItem, Star, UnaryOp,)
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
    """Reads every row of a table. Each value is stored twice:
    under its plain name ("name") and under alias.name ("e.name")."""

    def __init__(self, table, alias=None):
        self.table = table
        self.alias = alias or table.name

    def __iter__(self):
        for row in self.table.rows:
            out = {}
            for column, value in row.items():
                out[column] = value
                out[f"{self.alias}.{column}"] = value
            yield out

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
        # e.name is looked up as "e.name", a bare name as "name"
        key = f"{expr.table}.{expr.name}" if expr.table else expr.name
        if key not in row:
            raise ExecutionError(f"Column '{key}' does not exist")
        return row[key]

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

    if isinstance(expr, FunctionCall):
        # after Aggregate, the row already contains the result under the
        # function's name, e.g. row["COUNT(*)"]
        name = expr_name(expr)
        if name in row:
            return row[name]
        raise ExecutionError(f"Aggregate function {name} is not allowed here")

    raise ExecutionError(f"Unsupported expression: {expr}")


def expr_name(expr):
    """Turn an expression back into text, used as a column header, e.g. 'AVG(salary)'."""
    if isinstance(expr, Column):
        return f"{expr.table}.{expr.name}" if expr.table else expr.name
    if isinstance(expr, Star):
        return "*"
    if isinstance(expr, Literal):
        # strings get quotes: 'Nis', numbers don't: 30
        return repr(expr.value) if isinstance(expr.value, str) else str(expr.value)
    if isinstance(expr, FunctionCall):
        return f"{expr.name}({', '.join(expr_name(arg) for arg in expr.args)})"
    if isinstance(expr, BinaryOp):
        left = expr_name(expr.left)
        right = expr_name(expr.right)
        # wrap nested operations in brackets so the text is not ambiguous
        if isinstance(expr.left, BinaryOp):
            left = f"({left})"
        if isinstance(expr.right, BinaryOp):
            right = f"({right})"
        return f"{left} {expr.op} {right}"
    if isinstance(expr, UnaryOp):
        return f"{expr.op} {expr_name(expr.operand)}"
    return str(expr)


def collect_columns(expr):
    """Return the set of all column names used anywhere inside an expression."""
    if isinstance(expr, Column):
        return {expr_name(expr)}
    if isinstance(expr, BinaryOp):
        return collect_columns(expr.left) | collect_columns(expr.right)
    if isinstance(expr, UnaryOp):
        return collect_columns(expr.operand)
    if isinstance(expr, FunctionCall):
        names = set()
        for arg in expr.args:
            names |= collect_columns(arg)
        return names
    return set()  # Literal, Star: no columns


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


def sort_key(value):
    """Sort key that puts NULL (None) after every other value."""
    if value is None:
        return (1, 0)
    return (0, value)


class Sort(Operator):
    """Reads ALL rows from the child, sorts them, then passes them on."""

    def __init__(self, child, order_by):
        self.child = child
        self.order_by = order_by  # list of OrderItem

    def __iter__(self):
        rows = list(self.child)
        try:
            # sort by the last item first; Python's sort is stable,
            # so the earlier items end up deciding the final order
            for item in reversed(self.order_by):
                rows.sort(
                    key=lambda row: sort_key(evaluate(item.expr, row)),
                    reverse=item.descending,
                )
        except TypeError:
            raise ExecutionError("Cannot sort values of different types")
        yield from rows

# ---------- Aggregate functions ----------

class Accumulator:
    """Base class: sees values one by one, then returns one result."""

    def add(self, value):
        raise NotImplementedError

    def result(self):
        raise NotImplementedError


class CountStar(Accumulator):
    """COUNT(*): counts rows, including rows with NULL values."""

    def __init__(self):
        self.count = 0

    def add(self, value):
        self.count += 1

    def result(self):
        return self.count


class Sum(Accumulator):
    """SUM(x): ignores NULL; NULL if there were no values."""

    def __init__(self):
        self.total = None

    def add(self, value):
        if value is None:
            return
        self.total = value if self.total is None else self.total + value

    def result(self):
        return self.total


class Count(Accumulator):
    """COUNT(x): counts only non-NULL values."""

    def __init__(self):
        self.count = 0

    def add(self, value):
        if value is not None:
            self.count += 1

    def result(self):
        return self.count


class Avg(Accumulator):
    """AVG(x): average of non-NULL values; NULL if there were none."""

    def __init__(self):
        self.total = 0
        self.count = 0

    def add(self, value):
        if value is None:
            return
        self.total += value
        self.count += 1

    def result(self):
        if self.count == 0:
            return None
        return self.total / self.count


class Min(Accumulator):
    """MIN(x): smallest non-NULL value; NULL if there were none."""

    def __init__(self):
        self.value = None

    def add(self, value):
        if value is not None and (self.value is None or value < self.value):
            self.value = value

    def result(self):
        return self.value


class Max(Accumulator):
    """MAX(x): largest non-NULL value; NULL if there were none."""

    def __init__(self):
        self.value = None

    def add(self, value):
        if value is not None and (self.value is None or value > self.value):
            self.value = value

    def result(self):
        return self.value

AGGREGATES = {"COUNT": Count, "SUM": Sum, "AVG": Avg, "MIN": Min, "MAX": Max}


def make_accumulator(call):
    """Create the right Accumulator for a FunctionCall like COUNT(*) or AVG(salary)."""
    if call.name not in AGGREGATES:
        raise ExecutionError(f"Unknown function {call.name}")
    if len(call.args) != 1:
        raise ExecutionError(f"{call.name} takes exactly one argument")
    if isinstance(call.args[0], Star):
        if call.name != "COUNT":
            raise ExecutionError(f"{call.name}(*) is not allowed, only COUNT(*)")
        return CountStar()
    return AGGREGATES[call.name]()  # look up the class and create an object


class Aggregate(Operator):
    """Groups rows with a hash table and computes aggregate functions for each group."""

    def __init__(self, child, group_by, aggregates):
        self.child = child
        self.group_by = group_by      # list of expressions, e.g. [Column("city")]
        self.aggregates = aggregates  # list of FunctionCall, e.g. [COUNT(*), AVG(salary)]

    def __iter__(self):
        groups = {}  # key (tuple of GROUP BY values) -> list of accumulators

        for row in self.child:
            key = tuple(evaluate(expr, row) for expr in self.group_by)
            if key not in groups:
                groups[key] = [make_accumulator(call) for call in self.aggregates]
            for call, acc in zip(self.aggregates, groups[key]):
                if isinstance(call.args[0], Star):
                    acc.add(None)  # COUNT(*) only counts rows, the value doesn't matter
                else:
                    acc.add(evaluate(call.args[0], row))

        # No GROUP BY and no rows (e.g. SELECT COUNT(*) FROM empty): still one result row
        if not groups and not self.group_by:
            groups[()] = [make_accumulator(call) for call in self.aggregates]

        # One output row per group, as a dict: {"city": "Nis", "COUNT(*)": 2, ...}
        for key, accumulators in groups.items():
            out = {}
            for expr, value in zip(self.group_by, key):
                out[expr_name(expr)] = value
            for call, acc in zip(self.aggregates, accumulators):
                out[expr_name(call)] = acc.result()
            yield out

class NestedLoopJoin(Operator):
    """For every left row, check every right row: O(n * m). Works with any condition."""

    def __init__(self, left, right, condition):
        self.left = left
        self.right = right
        self.condition = condition

    def __iter__(self):
        # read the right side once: it is needed again for every left row,
        # and an operator can't safely be iterated more than once
        right_rows = list(self.right)
        for left_row in self.left:
            for right_row in right_rows:
                row = {**left_row, **right_row}  # one dict with the keys of both rows
                if evaluate(self.condition, row) is True:
                    yield row


class HashJoin(Operator):
    """Equality join in two phases, O(n + m):
    build a hash table from the right side, then probe it with each left row."""

    def __init__(self, left, right, left_key, right_key):
        self.left = left
        self.right = right
        self.left_key = left_key    # expression for the left side, e.g. e.department_id
        self.right_key = right_key  # expression for the right side, e.g. d.id

    def __iter__(self):
        buckets = {}  # key value -> list of right rows with that value
        for right_row in self.right:                      # build phase
            key = evaluate(self.right_key, right_row)
            if key is None:
                continue                                  # NULL never matches anything
            buckets.setdefault(key, []).append(right_row)
        for left_row in self.left:                        # probe phase
            key = evaluate(self.left_key, left_row)
            # a NULL or missing key finds no bucket, so it gives no rows
            for right_row in buckets.get(key, []):
                yield {**left_row, **right_row}


def make_join(left, left_aliases, right, right_alias, condition):
    """Choose the join algorithm (a tiny query planner)."""
    if (
        isinstance(condition, BinaryOp)
        and condition.op == "="
        and isinstance(condition.left, Column)
        and isinstance(condition.right, Column)
    ):
        a, b = condition.left, condition.right
        if a.table in left_aliases and b.table == right_alias:
            return HashJoin(left, right, a, b)
        if b.table in left_aliases and a.table == right_alias:
            return HashJoin(left, right, b, a)  # ON d.id = e.department_id: swap the sides
    return NestedLoopJoin(left, right, condition)

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
    """Computes the SELECT expressions for each row."""

    def __init__(self, child, exprs):
        self.child = child
        self.exprs = exprs

    def __iter__(self):
        for row in self.child:
            yield [evaluate(expr, row) for expr in self.exprs]


# ---------- Planning and execution ----------

def expand_star(stmt, scope):
    """SELECT * -> one SelectItem per column of every table in the query."""
    if len(stmt.columns) == 1 and isinstance(stmt.columns[0].expr, Star):
        if len(scope) == 1:
            table = next(iter(scope.values()))
            return [SelectItem(Column(name)) for name in table.columns]
        return [
            SelectItem(Column(name, table=alias))
            for alias, table in scope.items()
            for name in table.columns
        ]
    return stmt.columns

def column_refs(expr):
    """All Column nodes inside an expression (like collect_columns, but keeps the nodes)."""
    if isinstance(expr, Column):
        return [expr]
    if isinstance(expr, BinaryOp):
        return column_refs(expr.left) + column_refs(expr.right)
    if isinstance(expr, UnaryOp):
        return column_refs(expr.operand)
    if isinstance(expr, FunctionCall):
        refs = []
        for arg in expr.args:
            refs += column_refs(arg)
        return refs
    return []


def check_column(column, scope):
    """scope maps alias -> Table. Checks that a column exists and is not ambiguous."""
    if column.table is not None:
        if column.table not in scope:
            raise ExecutionError(f"Unknown table or alias '{column.table}'")
        if column.name not in scope[column.table].columns:
            raise ExecutionError(f"Column '{column.table}.{column.name}' does not exist")
        return
    owners = [alias for alias, table in scope.items() if column.name in table.columns]
    if not owners:
        if len(scope) == 1:
            table = next(iter(scope.values()))
            raise ExecutionError(f"Column '{column.name}' does not exist in table '{table.name}'")
        raise ExecutionError(f"Column '{column.name}' does not exist")
    if len(owners) > 1:
        raise ExecutionError(
            f"Column '{column.name}' is ambiguous: it exists in {', '.join(owners)}"
        )

def find_aggregates(items, order_by):
    """All aggregate function calls used in SELECT and ORDER BY, without duplicates."""
    found = {}
    for expr in [item.expr for item in items] + [item.expr for item in order_by]:
        if isinstance(expr, FunctionCall):
            found[expr_name(expr)] = expr
    return list(found.values())


def validate_grouping(items, group_by):
    """In a GROUP BY query, every non-aggregate SELECT item may only use grouped columns."""
    grouped = {expr_name(expr) for expr in group_by}
    for item in items:
        if isinstance(item.expr, FunctionCall):
            continue
        if expr_name(item.expr) in grouped:
            continue  # the exact expression is in GROUP BY, e.g. GROUP BY age > 30
        missing = collect_columns(item.expr) - grouped
        if missing:
            column = sorted(missing)[0]
            raise ExecutionError(
                f"Column '{column}' must appear in GROUP BY or be used in an aggregate function"
            )

def validate_columns(stmt, items, scope):
    """Fail fast: check every column used anywhere in the query."""
    exprs = [item.expr for item in items] + list(stmt.group_by)
    exprs += [join.condition for join in stmt.joins]
    if stmt.where is not None:
        exprs.append(stmt.where)
    exprs += [item.expr for item in stmt.order_by]
    for expr in exprs:
        for column in column_refs(expr):
            check_column(column, scope)

def header(item):
    """Column header: the alias, or the bare column name (e.name -> name), or the expression."""
    if item.alias:
        return item.alias
    if isinstance(item.expr, Column):
        return item.expr.name
    return expr_name(item.expr)

def execute(stmt, catalog):
    """Build the plan of operators for a SelectStatement and run it."""
    table = catalog.get_table(stmt.table)
    alias = stmt.alias or stmt.table
    scope = {alias: table}  # alias -> Table, for every table in the query
    plan = Scan(table, alias)

    for join in stmt.joins:
        join_table = catalog.get_table(join.table)
        join_alias = join.alias or join.table
        if join_alias in scope:
            raise ExecutionError(f"Table alias '{join_alias}' is used more than once")
        left_aliases = set(scope)
        scope[join_alias] = join_table
        plan = make_join(plan, left_aliases, Scan(join_table, join_alias), join_alias, join.condition)

    items = expand_star(stmt, scope)
    validate_columns(stmt, items, scope)

    aggregates = find_aggregates(items, stmt.order_by)
    if stmt.group_by or aggregates:
        validate_grouping(items, stmt.group_by)

    if stmt.where is not None:
        plan = Filter(plan, stmt.where)
    if stmt.group_by or aggregates:
        plan = Aggregate(plan, stmt.group_by, aggregates)
    if stmt.order_by:
        plan = Sort(plan, stmt.order_by)
    if stmt.limit is not None:
        plan = Limit(plan, stmt.limit)
    plan = Project(plan, [item.expr for item in items])

    return Result([header(item) for item in items], list(plan))


def run(sql, catalog):
    """Parse and execute a SQL string."""
    return execute(parse(sql), catalog)