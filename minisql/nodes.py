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