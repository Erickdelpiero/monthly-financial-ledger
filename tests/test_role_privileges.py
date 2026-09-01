"""The database role used by the application/tests must be least privilege.

Hard rule from PHASE-2.6 §4.1, PHASE-2.7 §8, PHASE-2.11 §4.4, verified as a
mandatory test in PHASE-2.9 §12.2: the project role must never be able to
administer the PostgreSQL instance.

If this test fails you are almost certainly running the suite as a superuser
(e.g. the `postgres` role). Create the dedicated role with
`scripts/local_db_setup.sql` and point TEST_DATABASE_URL at it.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def test_app_role_has_no_instance_privileges(db_session: Session) -> None:
    row = db_session.execute(
        text(
            "SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolbypassrls "
            "FROM pg_roles WHERE rolname = current_user"
        )
    ).one()

    assert row.rolsuper is False, f"role {row.rolname!r} must NOT be SUPERUSER"
    assert row.rolcreatedb is False, f"role {row.rolname!r} must NOT have CREATEDB"
    assert row.rolcreaterole is False, f"role {row.rolname!r} must NOT have CREATEROLE"
    assert row.rolbypassrls is False, f"role {row.rolname!r} must NOT have BYPASSRLS"


def test_app_role_is_not_member_of_superuser_roles(db_session: Session) -> None:
    superuser_memberships = db_session.execute(
        text(
            """
            SELECT g.rolname
            FROM pg_auth_members m
            JOIN pg_roles g ON g.oid = m.roleid
            JOIN pg_roles u ON u.oid = m.member
            WHERE u.rolname = current_user AND g.rolsuper
            """
        )
    ).scalars().all()
    assert superuser_memberships == []
