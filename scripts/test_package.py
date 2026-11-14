"""Inspect built archives without service credentials or network requests."""

from __future__ import annotations

import hashlib
import re
import tarfile
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PARTS = {
    ".git",
    ".venv",
    "venv",
    "cleanvenv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
}
TOKEN_PATTERN = re.compile(
    rb"(?:pypi-[A-Za-z0-9_-]{30,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    rb"github_pat_[A-Za-z0-9_]{30,}|AKIA[0-9A-Z]{16}|"
    rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)"
)


def check_members(members: dict[str, bytes]) -> None:
    for name, content in members.items():
        path = PurePosixPath(name)
        if (
            path.is_absolute()
            or ".." in path.parts
            or any(part in FORBIDDEN_PARTS or part.startswith(".venv") for part in path.parts)
        ):
            raise SystemExit(f"Forbidden distribution path: {name}")
        if path.name.startswith(".env") and path.name != ".env.example":
            raise SystemExit(f"Environment file must not be distributed: {name}")
        if b"{{" + b"secret:" in content or TOKEN_PATTERN.search(content):
            raise SystemExit(f"Potential credential in distribution member: {name}")


def main() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    if project["name"] != "langchain-adscrawl":
        raise SystemExit("Unexpected project name")
    version = project["version"]
    archives = sorted((ROOT / "dist").iterdir())
    wheel_name = f"langchain_adscrawl-{version}-py3-none-any.whl"
    source_name = f"langchain_adscrawl-{version}.tar.gz"
    if {archive.name for archive in archives} != {wheel_name, source_name}:
        raise SystemExit("dist/ must contain exactly this version's wheel and source archive")

    for archive in archives:
        if archive.suffix == ".whl":
            with zipfile.ZipFile(archive) as wheel:
                members = {
                    name: wheel.read(name) for name in wheel.namelist() if not name.endswith("/")
                }
            required = {
                "langchain_adscrawl/__init__.py",
                "langchain_adscrawl/tools.py",
                "langchain_adscrawl/py.typed",
            }
            if not required <= members.keys():
                raise SystemExit("Wheel is missing a public module or typing marker")
            metadata_path = f"langchain_adscrawl-{version}.dist-info/METADATA"
        else:
            with tarfile.open(archive, "r:gz") as source:
                members = {}
                for member in source.getmembers():
                    if member.issym() or member.islnk():
                        raise SystemExit(f"Distribution must not contain links: {member.name}")
                    if member.isfile():
                        content = source.extractfile(member)
                        if content is None:
                            raise SystemExit("Unreadable source archive member")
                        members[member.name] = content.read()
            metadata_path = f"langchain_adscrawl-{version}/PKG-INFO"
            if f"langchain_adscrawl-{version}/README.md" not in members:
                raise SystemExit("Source archive is missing README.md")

        check_members(members)
        metadata = BytesParser().parsebytes(members[metadata_path])
        if metadata["Name"] != project["name"] or metadata["Version"] != version:
            raise SystemExit("Archive identity does not match pyproject.toml")
        if metadata["Requires-Python"] != project["requires-python"]:
            raise SystemExit("Archive Python requirement differs from project metadata")
        licenses = [content for name, content in members.items() if name.endswith("/LICENSE")]
        if not licenses or not all(b"MIT License" in content for content in licenses):
            raise SystemExit("Archive must include the project's MIT license")
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        print(f"{archive.name}: PASS ({len(members)} members), SHA256 {digest}")

    print("No real service calls were made. Pattern scanning is not a complete secret detector.")


if __name__ == "__main__":
    main()
