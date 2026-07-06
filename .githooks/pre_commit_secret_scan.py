from __future__ import annotations

import re
import shutil
import subprocess
import sys


SECRET_ASSIGNMENT = re.compile(
    r"\b([A-Z0-9_-]*(?:PASSWORD|PASSWD|PWD|SECRET|API[_-]?KEY|TOKEN|PRIVATE[_-]?KEY|SMTP|HUNTER|HOSTINGER|COMPANIES_HOUSE)[A-Z0-9_-]*)\b\s*[:=]\s*([^\s#,'\"]+)"
)
UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
LONG_TOKEN = re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9_\-]{36,}(?![A-Za-z0-9])")
PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
ALLOW_EMPTY = {"", "''", '""'}
PLACEHOLDERS = {
    "your-password",
    "your-mailbox-password",
    "your-mailbox@example.com",
    "your-api-key",
    "placeholder",
    "changeme",
    "change-me",
    "example",
    "redacted",
    "<redacted>",
}
CONFIG_ALLOWLIST = {
    "HOSTINGER_IMAP_HOST",
    "HOSTINGER_IMAP_PORT",
    "HOSTINGER_DRAFTS_FOLDER",
}


def run(*args: str) -> str:
    return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL)


def staged_files() -> list[str]:
    output = run("git", "diff", "--cached", "--name-only", "--diff-filter=ACMR")
    return [line.strip() for line in output.splitlines() if line.strip()]


def staged_content(path: str) -> str:
    return run("git", "show", f":{path}")


def scan_staged() -> list[str]:
    findings: list[str] = []
    for path in staged_files():
        if path.startswith(".git/"):
            continue
        if path == ".githooks/pre_commit_secret_scan.py":
            continue
        try:
            content = staged_content(path)
        except Exception:
            continue
        if "\0" in content[:2048]:
            continue
        for line_no, line in enumerate(content.splitlines(), 1):
            if PRIVATE_KEY.search(line):
                findings.append(f"{path}:{line_no}: private key block")
            for match in SECRET_ASSIGNMENT.finditer(line):
                name = match.group(1)
                value = match.group(2).strip()
                if name in CONFIG_ALLOWLIST:
                    continue
                if value in ALLOW_EMPTY or value.casefold() in PLACEHOLDERS:
                    continue
                if len(value) >= 8:
                    findings.append(f"{path}:{line_no}: secret assignment for {name}")
            upper_line = line.upper()
            if "API_KEY" in upper_line or "TOKEN" in upper_line or "PASSWORD" in upper_line:
                if UUID.search(line) or LONG_TOKEN.search(line):
                    findings.append(f"{path}:{line_no}: key-shaped token near sensitive name")
    return findings


def main() -> int:
    if shutil.which("gitleaks"):
        return subprocess.call(["gitleaks", "protect", "--staged", "--redact"])

    findings = scan_staged()
    if not findings:
        return 0

    print("Secret scan blocked this commit. Findings:")
    for item in findings:
        print(f"- {item}")
    print("Install gitleaks for stronger scanning: https://github.com/gitleaks/gitleaks")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
