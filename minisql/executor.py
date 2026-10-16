from dataclasses import dataclass

from minisql.nodes import Star
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
    if stmt.limit is not None:
        plan = Limit(plan, stmt.limit)
    plan = Project(plan, columns)

    return Result(columns, list(plan))


def run(sql, catalog):
    """Parse and execute a SQL string."""
    return execute(parse(sql), catalog)