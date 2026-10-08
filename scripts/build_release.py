import hashlib
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTRACTS = ("worklog.py", "skill_verifier.py", "score_registry.py")


def main():
    dist = os.path.join(ROOT, "dist")
    shutil.rmtree(dist, ignore_errors=True)
    os.makedirs(dist)
    lines = []
    for name in CONTRACTS:
        src = os.path.join(ROOT, "contracts", name)
        with open(src, encoding="utf-8") as handle:
            compile(handle.read(), src, "exec")
        target = os.path.join(dist, name)
        shutil.copyfile(src, target)
        with open(target, "rb") as handle:
            lines.append(hashlib.sha256(handle.read()).hexdigest() + "  " + name)
    with open(os.path.join(dist, "MANIFEST.sha256"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    print("built " + str(len(CONTRACTS)) + " deployable contracts into dist/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
