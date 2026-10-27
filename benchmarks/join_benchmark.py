"""Compare nested loop join and hash join on generated tables of growing size.

Run from the project root:
    python -m benchmarks.join_benchmark
"""
import random
import time

from minisql.catalog import Table
from minisql.executor import HashJoin, NestedLoopJoin, Scan
from minisql.nodes import BinaryOp, Column

SIZES = [(500, 50), (1000, 100), (2000, 200), (4000, 400)]  # (employees, departments)


def make_tables(n_employees, n_departments, seed=42):
    """Generate an employees table and a departments table in memory."""
    rng = random.Random(seed)  # fixed seed: the same "random" data on every run
    departments = Table(
        "departments",
        ["id", "name"],
        [{"id": i, "name": f"Department {i}"} for i in range(1, n_departments + 1)],
    )
    employees = Table(
        "employees",
        ["id", "name", "department_id"],
        [
            {"id": i, "name": f"Employee {i}", "department_id": rng.randint(1, n_departments)}
            for i in range(1, n_employees + 1)
        ],
    )
    return employees, departments


def measure(join):
    """Run a join to the end; return (number of rows, seconds)."""
    start = time.perf_counter()
    # operators are lazy: nothing runs until we actually read every row
    count = sum(1 for _ in join)
    return count, time.perf_counter() - start


def main():
    left_key = Column("department_id", table="e")
    right_key = Column("id", table="d")
    condition = BinaryOp("=", left_key, right_key)

    print(f"{'employees':>10} {'depts':>6} {'comparisons':>12} "
          f"{'nested loop':>12} {'hash join':>10} {'speedup':>8}")
    for n, m in SIZES:
        employees, departments = make_tables(n, m)

        # fresh Scans for each join, over the same tables
        nested_rows, nested_time = measure(
            NestedLoopJoin(Scan(employees, "e"), Scan(departments, "d"), condition)
        )
        hash_rows, hash_time = measure(
            HashJoin(Scan(employees, "e"), Scan(departments, "d"), left_key, right_key)
        )

        assert nested_rows == hash_rows == n  # every employee has exactly one department

        print(f"{n:>10} {m:>6} {n * m:>12,} "
              f"{nested_time:>11.3f}s {hash_time:>9.4f}s {nested_time / hash_time:>7.0f}x")


if __name__ == "__main__":
    main()