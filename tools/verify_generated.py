#!/usr/bin/env python3
"""Verify committed generated code matches current generator output."""

import argparse
import difflib
import filecmp
import sys
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Verify generated code is up to date")
    parser.add_argument("--ir", default="schema/ir/niri-ipc-ir.json")
    parser.add_argument("--generated-dir", default="src/niri_pypc/types/generated/")
    args = parser.parse_args()

    generated_dir = Path(args.generated_dir)
    ir_path = Path(args.ir)

    if not generated_dir.is_dir():
        print(f"ERROR: Generated directory not found: {generated_dir}", file=sys.stderr)
        sys.exit(1)

    if not ir_path.is_file():
        print(f"ERROR: IR file not found: {ir_path}", file=sys.stderr)
        sys.exit(1)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Run generate_types to produce fresh output
        import subprocess

        result = subprocess.run(
            [
                "python",
                "tools/generate_types.py",
                "--ir",
                str(ir_path),
                "--output-dir",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            print(f"ERROR: Generator failed:\n{result.stderr}", file=sys.stderr)
            sys.exit(1)

        # Compare file sets
        committed_files = sorted(generated_dir.rglob("*.py"))
        fresh_files = sorted(tmp_path.rglob("*.py"))

        committed_names = {f.relative_to(generated_dir) for f in committed_files}
        fresh_names = {f.relative_to(tmp_path) for f in fresh_files}

        only_committed = committed_names - fresh_names
        only_fresh = fresh_names - committed_names

        diff_found = False

        if only_committed:
            print(f"Files only in {generated_dir}:")
            for name in sorted(only_committed):
                print(f"  - {name}")
            diff_found = True

        if only_fresh:
            print("Files only in fresh generation:")
            for name in sorted(only_fresh):
                print(f"  + {name}")
            diff_found = True

        # Compare common files
        common = committed_names & fresh_names
        for name in sorted(common):
            committed_file = generated_dir / name
            fresh_file = tmp_path / name

            if not filecmp.cmp(committed_file, fresh_file, shallow=False):
                print(f"Differences in {name}:")
                with open(committed_file) as f1, open(fresh_file) as f2:
                    diff = difflib.unified_diff(
                        f1.readlines(),
                        f2.readlines(),
                        fromfile=str(committed_file),
                        tofile=str(fresh_file),
                    )
                for line in diff:
                    sys.stdout.write(line)
                diff_found = True

        if diff_found:
            print("\nERROR: Generated code is out of date.", file=sys.stderr)
            print("Run: normalize-ir && generate-types", file=sys.stderr)
            sys.exit(1)
        else:
            print("Generated code is up to date.")
            sys.exit(0)


if __name__ == "__main__":
    main()
