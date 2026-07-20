from core.models import ConnectionProfile


def test_direct_profile_defaults() -> None:
    cp = ConnectionProfile(
        name="dev",
        connection_type="direct",
        host="db.example.com",
        service="ORCL",
        username="scott",
        password="tiger",
    )
    assert cp.port == 1521
    assert cp.alias == ""


def test_tns_profile_fields() -> None:
    cp = ConnectionProfile(
        name="prod",
        connection_type="tns",
        alias="PRODDB",
        username="scott",
        password="tiger",
    )
    assert cp.host == ""
    assert cp.port == 1521
    assert cp.alias == "PRODDB"


def test_profile_name_stored() -> None:
    cp = ConnectionProfile(
        name="my-db",
        connection_type="direct",
        host="localhost",
        service="XE",
        username="hr",
        password="hr",
    )
    assert cp.name == "my-db"
