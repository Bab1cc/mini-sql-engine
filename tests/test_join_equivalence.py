from benchmarks.join_benchmark import make_tables
from minisql.executor import HashJoin, NestedLoopJoin, Scan
from minisql.nodes import BinaryOp, Column


def pairs(join):
    return [(row["e.id"], row["d.id"]) for row in join]


def test_hash_join_and_nested_loop_join_agree_on_random_data():
    left_key = Column("department_id", table="e")
    right_key = Column("id", table="d")
    condition = BinaryOp("=", left_key, right_key)
    for seed in range(5):
        employees, departments = make_tables(200, 20, seed=seed)
        nested = NestedLoopJoin(Scan(employees, "e"), Scan(departments, "d"), condition)
        hashed = HashJoin(Scan(employees, "e"), Scan(departments, "d"), left_key, right_key)
        assert pairs(nested) == pairs(hashed)