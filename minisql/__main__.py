import sys

from minisql.catalog import Catalog, CatalogError
from minisql.executor import ExecutionError, run
from minisql.formatter import format_result
from minisql.parser import ParseError
from minisql.tokenizer import TokenizerError


def main():
    if len(sys.argv) < 2:
        print('Usage: python -m minisql "SELECT ... FROM ..."')
        return
    try:
        result = run(sys.argv[1], Catalog())
    except (TokenizerError, ParseError, CatalogError, ExecutionError) as error:
        print(f"Error: {error}")
        return
    print(format_result(result))


if __name__ == "__main__":
    main()