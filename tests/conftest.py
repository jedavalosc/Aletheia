import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def db_url():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set (needs an empty Postgres database)")
    return url


@pytest.fixture(scope="session")
def demo_db(db_url, tmp_path_factory):
    """Fresh schema + demo edition, approved by a test editor, site built."""
    env = {**os.environ, "DATABASE_URL": db_url}
    from sqlalchemy import create_engine, text
    eng = create_engine(db_url.replace("postgresql://", "postgresql+psycopg://", 1) if db_url.startswith("postgresql://") else db_url)
    with eng.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    subprocess.run(["alembic", "upgrade", "head"], cwd=ROOT, env=env, check=True, capture_output=True)
    os.environ["DATABASE_URL"] = db_url
    site = tmp_path_factory.mktemp("site") / "site"
    os.environ["SITE_DIR"] = str(site)
    from app import db
    db._engine = None
    db._Session = None
    from app.seed.demo import seed_demo
    with db.session() as s:
        seed_demo(s)
    return {"url": db_url, "site": site}
