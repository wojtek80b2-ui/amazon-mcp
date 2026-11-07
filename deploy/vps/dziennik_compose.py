"""Dopisuje do docker-compose.mcp.yml trwały wolumen dziennika zmian reklam dla usługi amazon-mcp.

Użycie: python3 dziennik_compose.py /home/debian/mcp/docker-compose.mcp.yml
Idempotentne: gdy wolumen już jest, nic nie zmienia. Kopię i walidację robi aktualizuj.sh.
Dodaje w usłudze amazon-mcp: volumes: [amazon_dziennik:/dane] i ADS_CHANGE_LOG=/dane/ads-changes.jsonl,
a na najwyższym poziomie volumes: amazon_dziennik.
"""

from __future__ import annotations

import re
import sys


def patch(text: str) -> str:
    if "amazon_dziennik" in text:
        return text
    lines = text.split("\n")
    try:
        start = lines.index("  amazon-mcp:")
    except ValueError:
        raise SystemExit("Nie znaleziono usługi amazon-mcp w compose")
    end = start + 1
    while end < len(lines) and (lines[end].startswith("    ") or not lines[end].strip()):
        end += 1
    block = lines[start:end]
    try:
        tmpfs = next(i for i, line in enumerate(block) if line.startswith("    tmpfs:"))
        env = next(i for i, line in enumerate(block) if line == "    environment:")
    except StopIteration:
        raise SystemExit("Usługa amazon-mcp bez tmpfs: albo environment: — dopisz wolumen ręcznie")
    if any(line.startswith("    volumes:") for line in block):
        raise SystemExit("Usługa amazon-mcp ma już volumes: — dopisz wolumen ręcznie")
    block.insert(env + 1, "      ADS_CHANGE_LOG: /dane/ads-changes.jsonl")
    block[tmpfs + 1:tmpfs + 1] = ["    volumes:", "      - amazon_dziennik:/dane"]
    lines[start:end] = block
    try:
        top = lines.index("volumes:")
    except ValueError:
        raise SystemExit("Brak sekcji volumes: na najwyższym poziomie compose")
    lines.insert(top + 1, "  amazon_dziennik:")
    return "\n".join(lines)


if __name__ == "__main__":
    path = sys.argv[1]
    with open(path, encoding="utf-8", newline="") as fh:
        before = fh.read()
    after = patch(before)
    if after != before:
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(after)
        print("Compose: dodany wolumen amazon_dziennik:/dane i ADS_CHANGE_LOG")
