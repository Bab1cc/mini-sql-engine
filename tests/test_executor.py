import pytest

from minisql.catalog import Catalog, CatalogError
from minisql.executor import ExecutionError, Limit, Operator, run, sql_and, sql_or


@pytest.fixture
def catalog(tmp_path):
    (tmp_path / "users.csv").write_text(
        "id,name,age\n1,Ana,34\n2,Marko,28\n3,Jovan,41\n", encoding="utf-8"
    )
    # Jelena's age is an empty cell, which means NULL
    (tmp_path / "people.csv").write_text(
        "id,name,age\n1,Ana,34\n2,Jelena,\n3,Jovan,41\n", encoding="utf-8"
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

# ---------- WHERE ----------

def test_where_filters_rows(catalog):
    result = run("SELECT name FROM users WHERE age > 30", catalog)
    assert result.rows == [["Ana"], ["Jovan"]]


def test_where_string_equality(catalog):
    assert run("SELECT id FROM users WHERE name = 'Marko'", catalog).rows == [[2]]


def test_where_no_matches(catalog):
    assert run("SELECT name FROM users WHERE age > 100", catalog).rows == []


def test_where_and_or_with_brackets(catalog):
    sql = "SELECT name FROM users WHERE (age > 30 AND name != 'Ana') OR id = 2"
    assert run(sql, catalog).rows == [["Marko"], ["Jovan"]]


def test_where_not(catalog):
    assert run("SELECT name FROM users WHERE NOT age > 30", catalog).rows == [["Marko"]]


def test_where_runs_before_limit(catalog):
    # if LIMIT ran first, it would keep only Ana and the filter would drop her
    assert run("SELECT name FROM users WHERE age < 30 LIMIT 1", catalog).rows == [["Marko"]]


# ---------- WHERE with NULL ----------

def test_where_comparison_with_null_drops_row(catalog):
    assert run("SELECT name FROM people WHERE age > 30", catalog).rows == [["Ana"], ["Jovan"]]


def test_where_not_null_is_still_null(catalog):
    # NOT (NULL < 35) is NULL, so Jelena is still dropped
    assert run("SELECT name FROM people WHERE NOT age < 35", catalog).rows == [["Jovan"]]


def test_where_null_or_true_keeps_row(catalog):
    sql = "SELECT name FROM people WHERE age > 30 OR name = 'Jelena'"
    assert run(sql, catalog).rows == [["Ana"], ["Jelena"], ["Jovan"]]


def test_where_null_and_true_drops_row(catalog):
    assert run("SELECT name FROM people WHERE age > 30 AND name = 'Jelena'", catalog).rows == []


@pytest.mark.parametrize("left, right, expected", [
    (True, True, True),
    (True, False, False),
    (False, None, False),
    (True, None, None),
    (None, None, None),
])
def test_sql_and(left, right, expected):
    assert sql_and(left, right) is expected
    assert sql_and(right, left) is expected


@pytest.mark.parametrize("left, right, expected", [
    (False, False, False),
    (True, False, True),
    (True, None, True),
    (False, None, None),
    (None, None, None),
])
def test_sql_or(left, right, expected):
    assert sql_or(left, right) is expected
    assert sql_or(right, left) is expected


# ---------- WHERE errors ----------

def test_where_unknown_column_raises(catalog):
    with pytest.raises(ExecutionError, match="Column 'salary' does not exist"):
        run("SELECT name FROM users WHERE salary > 1000", catalog)


def test_where_compare_string_with_number_raises(catalog):
    with pytest.raises(ExecutionError, match="Cannot compare 'Ana' with 5 using '>'"):
        run("SELECT name FROM users WHERE name > 5", catalog)
