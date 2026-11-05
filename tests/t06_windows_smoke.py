"""Windows CI: real T05 loopback server and headless smoke of the WPF client's C# source."""

import subprocess
import tempfile
from pathlib import Path

from t06_fixture import setup_fixture


def main():
    root = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory() as folder:
        servers = setup_fixture(Path(folder), web=False)
        try:
            subprocess.run(
                ["dotnet", "build", str(root / "integrations/windows/KnowledgeHelpDemo/KnowledgeHelpDemo.csproj"),
                 "-c", "Release", "--nologo"],
                check=True, timeout=180,
            )
            subprocess.run(
                ["dotnet", "run", "--project",
                 str(root / "integrations/windows/KnowledgeHelpSmoke/KnowledgeHelpSmoke.csproj"),
                 "-c", "Release", "--", "http://127.0.0.1:8765/"],
                check=True, timeout=180,
            )
        finally:
            for server in servers:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    main()
