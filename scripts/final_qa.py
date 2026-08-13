from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local RFQ final QA checks.")
    parser.add_argument("--db", default="outputs/rfq_extractions.db")
    parser.add_argument("--json", default="outputs/rfq_extractions.json")
    parser.add_argument("--skip-docker", action="store_true")
    parser.add_argument(
        "--docker-build",
        action="store_true",
        help="Also build the Docker image. Requires a running Docker daemon.",
    )
    args = parser.parse_args()

    checks = [
        ("project configuration", [sys.executable, "scripts/check_project_config.py"]),
        ("unit tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]),
        (
            "compile check",
            [sys.executable, "-m", "compileall", "agent_rfq_extractor", "database", "scripts", "tests"],
        ),
        (
            "output audit",
            [
                sys.executable,
                "scripts/audit_extraction_outputs.py",
                "--json",
                args.json,
                "--db",
                args.db,
                "--fixture-expectations",
            ],
        ),
        (
            "UI validation",
            [
                sys.executable,
                "scripts/validate_ui.py",
                "--db",
                args.db,
                "--json",
                args.json,
                "--fixture-expectations",
            ],
        ),
    ]

    if not args.skip_docker:
        if shutil.which("docker"):
            checks.append(("Docker Compose config", ["docker", "compose", "config", "--quiet"]))
            checks.append(
                (
                    "Docker Gmail override config",
                    [
                        "docker",
                        "compose",
                        "-f",
                        "docker-compose.yml",
                        "-f",
                        "docker-compose.gmail.yml",
                        "config",
                        "--quiet",
                    ],
                )
            )
            if args.docker_build:
                checks.append(("Docker image build", ["docker", "build", "-t", "glass-rfq-extractor:local-qa", "."]))
        else:
            print("Skipping Docker Compose config: docker is not installed.")

    failures: list[str] = []
    for name, command in checks:
        print(f"\n== {name} ==")
        result = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
        if result.returncode != 0:
            failures.append(name)

    if failures:
        print("\nFinal QA failed: " + ", ".join(failures))
        return 1

    print("\nFinal QA passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
