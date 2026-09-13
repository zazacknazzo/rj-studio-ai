import subprocess
import sys
from pathlib import Path


def test_import_and_app_creation_do_not_initialize_database(tmp_path: Path) -> None:
    database_path = tmp_path / "state" / "app.db"
    script = f"""
from pathlib import Path
from rj_studio_ai.config import Settings
from rj_studio_ai.main import create_app

create_app(Settings(_env_file=None, database_path=Path({str(database_path)!r})))
"""

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )

    assert not database_path.exists()
    assert not database_path.parent.exists()
