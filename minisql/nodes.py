from dataclasses import dataclass, field


@dataclass
class Column:
    """A column reference, e.g. name or users.name."""
    name: str
    table: str | None = None


@dataclass
class Star:
    """The * in SELECT *."""
    pass


@dataclass
class SelectItem:
    """One item in the SELECT list, with an optional alias (AS ...)."""
    expr: object
    alias: str | None = None


@dataclass
class SelectStatement:
    """A full SELECT query."""
    columns: list
    table: str
    where: object = None
    group_by: list = field(default_factory=list)
    order_by: list = field(default_factory=list)
    limit: int | None = None

@dataclass
class Literal:
    """A constant value: a number or a string, e.g. 30 or 'Belgrade'."""
    value: int | float | str


@dataclass
class BinaryOp:
    """An operation with two sides: age > 30, a AND b, a OR b..."""
    op: str
    left: object
    right: object


@dataclass
class UnaryOp:
    """An operation with one side: NOT ..."""
    op: str
    operand: object

@dataclass
class OrderItem:
    """One item in ORDER BY, e.g. salary DESC."""
    expr: object
    descending: bool = False