import pytest

from minisql.catalog import Catalog, CatalogError
from minisql.executor import ExecutionError, Limit, Operator, run


@pytest.fixture
def catalog(tmp_path):
    (tmp_path / "users.csv").write_text(
        "id,name,age\n1,Ana,34\n2,Marko,28\n3,Jovan,41\n", encoding="utf-8"
    )
    return Catalog(tmp_path)


def test_select_star(catalog):
    result = run("SELECT * FROM users", catalog)
    assert result.columns == ["id", "name", "age"]
    assert result.rows == [[1, "Ana", 34], [2, "Marko", 28], [3, "Jovan", 41]]


def test_select_columns_in_requested_order(catalog):
    result = run("SELECT age, name FROM users", catalog)
    assert result.columns == ["age", "name"]
    assert result.rows == [[34, "Ana"], [28, "Marko"], [41, "Jovan"]]


def test_limit(catalog):
    result = run("SELECT name FROM users LIMIT 2", catalog)
    assert result.rows == [["Ana"], ["Marko"]]


def test_limit_zero(catalog):
    assert run("SELECT name FROM users LIMIT 0", catalog).rows == []


def test_unknown_column_raises(catalog):
    with pytest.raises(ExecutionError):
        run("SELECT salary FROM users", catalog)


def test_unknown_table_raises(catalog):
    with pytest.raises(CatalogError):
        run("SELECT * FROM orders", catalog)


def test_limit_stops_reading_early():
    pulled = []

    class CountingSource(Operator):
        def __iter__(self):
            for i in range(1000):
                pulled.append(i)
                yield {"n": i}

    rows = list(Limit(CountingSource(), 3))
    assert len(rows) == 3
    assert len(pulled) < 10  # Limit must not read all 1000 rows