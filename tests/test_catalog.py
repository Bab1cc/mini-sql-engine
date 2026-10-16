import pytest

from minisql.catalog import Catalog, CatalogError, convert_value


def test_convert_value():
    assert convert_value("42") == 42
    assert isinstance(convert_value("42"), int)
    assert convert_value("3.5") == 3.5
    assert convert_value("Belgrade") == "Belgrade"
    assert convert_value("") is None


@pytest.fixture
def catalog(tmp_path):
    (tmp_path / "users.csv").write_text(
        "id,name,age\n1,Ana,34\n2,Marko,28\n", encoding="utf-8"
    )
    (tmp_path / "cities.csv").write_text("name\nBelgrade\n", encoding="utf-8")
    return Catalog(tmp_path)


def test_table_names(catalog):
    assert catalog.table_names() == ["cities", "users"]


def test_get_table(catalog):
    table = catalog.get_table("users")
    assert table.name == "users"
    assert table.columns == ["id", "name", "age"]
    assert table.rows == [
        {"id": 1, "name": "Ana", "age": 34},
        {"id": 2, "name": "Marko", "age": 28},
    ]


def test_missing_table_raises(catalog):
    with pytest.raises(CatalogError):
        catalog.get_table("orders")

def test_csv_with_bom(tmp_path):
    # Files saved by Excel/Notepad on Windows often start with an invisible BOM
    (tmp_path / "users.csv").write_text("id,name\n1,Ana\n", encoding="utf-8-sig")
    assert Catalog(tmp_path).get_table("users").columns == ["id", "name"]


def test_column_names_are_trimmed(tmp_path):
    (tmp_path / "users.csv").write_text("  id , name\n1,Ana\n", encoding="utf-8")
    table = Catalog(tmp_path).get_table("users")
    assert table.columns == ["id", "name"]
    assert table.rows == [{"id": 1, "name": "Ana"}]