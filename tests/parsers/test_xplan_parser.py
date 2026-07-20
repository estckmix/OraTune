from parsers.xplan_parser import parse_xplan_rows


def test_parse_xplan_rows_with_pipe_format() -> None:
    rows: list[dict[str, object]] = [
        {"plan_table_output": "Plan hash value: 1234"},
        {"plan_table_output": ""},
        {"plan_table_output": "----------------------------------------------------"},
        {
            "plan_table_output": "| Id | Operation          | Name | Rows | Bytes | Cost |"
        },
        {"plan_table_output": "----------------------------------------------------"},
        {
            "plan_table_output": "|  0 | SELECT STATEMENT   |      |    1 |    13 |    3 |"
        },
        {
            "plan_table_output": "|  1 |  TABLE ACCESS FULL | EMP  |    1 |    13 |    3 |"
        },
        {"plan_table_output": "----------------------------------------------------"},
    ]
    nodes = parse_xplan_rows(rows)
    assert len(nodes) == 2
    assert nodes[0]["operation"] == "SELECT STATEMENT"
    assert nodes[1]["operation"] == "TABLE ACCESS FULL"
    assert nodes[1]["depth"] == 1
    assert nodes[1]["name"] == "EMP"


def test_parse_xplan_rows_empty_list() -> None:
    assert parse_xplan_rows([]) == []


def test_parse_xplan_rows_no_plan_table() -> None:
    rows: list[dict[str, object]] = [
        {"plan_table_output": "ERROR: table or view does not exist"}
    ]
    assert parse_xplan_rows(rows) == []


def test_parse_xplan_rows_handles_missing_key() -> None:
    rows: list[dict[str, object]] = [{"plan_table_output": ""}, {}]
    assert isinstance(parse_xplan_rows(rows), list)
