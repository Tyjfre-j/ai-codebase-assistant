import pytest


@pytest.fixture
def project(tmp_path):
    """Builds a tiny fake project on disk:
    project/
      app/
        services.py
        api/
          routes/
            users.py   <- imports from services (relative + absolute + bare)
    """
    root = tmp_path / "project"
    (root / "app" / "api" / "routes").mkdir(parents=True)

    (root / "app" / "__init__.py").write_text("")
    (root / "app" / "api" / "__init__.py").write_text("")
    (root / "app" / "api" / "routes" / "__init__.py").write_text("")

    (root / "app" / "services.py").write_text(
        "def get_user(id):\n    pass\n"
    )

    users_py = root / "app" / "api" / "routes" / "users.py"
    users_py.write_text(
        "from ...services import get_user as gu\n"
        "from ...services import get_user\n"
        "import os\n"
        "import os as operating_system\n"
        "\n"
        "def handler():\n"
        "    return gu(1)\n"
    )

    return {
        "root": str(root),
        "users_py": str(users_py),
    }