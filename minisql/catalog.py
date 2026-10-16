import csv
from dataclasses import dataclass
from pathlib import Path


class CatalogError(Exception):
    pass


@dataclass
class Table:
    name: str
    columns: list  # column names, in order, e.g. ["id", "name", "age"]
    rows: list     # one dict per row, e.g. {"id": 1, "name": "Ana", "age": 34}


def convert_value(text):
    """Convert a CSV string to int, float or None; otherwise keep it as a string."""
    # an empty cell means NULL
    if text == "":
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


class Catalog:
    def __init__(self, data_dir="data"):
        self.data_dir = Path(data_dir)

    def table_names(self):
        """Return the names of all tables (CSV files without .csv), sorted."""
        return sorted(p.stem for p in self.data_dir.glob("*.csv"))

    def get_table(self, name):
        """Load a table from <data_dir>/<name>.csv."""
        path = self.data_dir / f"{name}.csv"
        if not path.exists():
            raise CatalogError(f"Table '{name}' does not exist")

        rows = []
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            columns = reader.fieldnames
            for row in reader:
                rows.append({col: convert_value(value) for col, value in row.items()})
        return Table(name, columns, rows)