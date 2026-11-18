# SPDX-License-Identifier: Apache-2.0
"""A small, deliberately conservative reader for MeshBeacon's AppArmor file rules.

It understands only what apparmor.txt uses: path rules (`/path/glob perms,`), `deny` path rules,
`@{PROC}`, `*`, `**` and `{a,b}` globs. It ignores includes, capability, network, signal and
other non-file rules. It is used to check, without an AppArmor-enabled kernel, that every program
the container runs may be executed and that every script may also be read by its interpreter —
the condition that broke startup on the reference Raspberry Pi (/init is a shell script).

The real kernel test runs in CI on an AppArmor-enabled runner (tests/container, MESHBEACON_APPARMOR).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

VARIABLES = {"@{PROC}": "/proc", "@{pid}": "{[1-9]*,[1-9][0-9]*}"}
RULE = re.compile(r"^(?P<deny>deny\s+)?(?P<path>/\S*)\s+(?P<perms>[rwaxlkmiuUpPcC]+)\s*(->\s*\S+)?\s*,\s*$")


def glob_to_regex(glob: str) -> re.Pattern[str]:
    for var, value in VARIABLES.items():
        glob = glob.replace(var, value)
    out, i = "", 0
    while i < len(glob):
        c = glob[i]
        if glob.startswith("**", i):
            out += ".*"
            i += 2
            continue
        if c == "*":
            out += "[^/]*"
        elif c == "?":
            out += "[^/]"
        elif c == "{":
            j = glob.index("}", i)
            out += "(?:" + "|".join(glob_to_regex(p).pattern[1:-1] for p in glob[i + 1 : j].split(",")) + ")"
            i = j
        elif c == "[":
            j = glob.index("]", i)
            out += glob[i : j + 1]
            i = j
        else:
            out += re.escape(c)
        i += 1
    return re.compile("^" + out + "$")


@dataclass
class Profile:
    allow: list[tuple[re.Pattern[str], str]]
    deny: list[tuple[re.Pattern[str], str]]
    name: str

    @classmethod
    def parse(cls, text: str) -> Profile:
        allow, deny, name = [], [], ""
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip() if not raw.strip().startswith("#include") else ""
            if line.startswith("profile "):
                name = line.split()[1]
                continue
            m = RULE.match(line)
            if m:
                (deny if m.group("deny") else allow).append((glob_to_regex(m.group("path")), m.group("perms")))
        return cls(allow, deny, name)

    def perms(self, path: str) -> set[str]:
        granted: set[str] = set()
        for regex, perms in self.allow:
            if regex.match(path):
                granted |= set(perms)
        for regex, perms in self.deny:
            if regex.match(path):
                granted -= set(perms)
        return granted

    def can_exec(self, path: str) -> bool:
        return "x" in self.perms(path)

    def can_read(self, path: str) -> bool:
        return "r" in self.perms(path)


def load(path: Path) -> Profile:
    return Profile.parse(path.read_text())
