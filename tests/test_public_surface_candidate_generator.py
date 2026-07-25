#!/usr/bin/env python3
"""Phase 3B-1 tests: explicit source-root, isolated output, dependency inventory.

Standard-library unittest only (no third-party dependency). These tests cover
the isolated candidate mode of the public-surface authority-map builder and the
preflight / verify-inventory modes of the public-metadata validator:

- default builder and validator backward compatibility;
- source/generator separation (content read only from the explicit source root);
- output/inventory isolation outside both roots;
- path traversal and symlink/reparse-point escape rejection;
- deterministic snapshot and inventory bytes;
- dependency-inventory schema, coverage, ordering, and identity recomputation;
- source-root Python import isolation (no execution of source-tree modules);
- default-mode working-tree identity (exactly 92,903 bytes / 30 records);
- pinned-commit historical identity (exactly 83,727 bytes / 27 records);
- source-root and generator-root no-write proofs on success and failure.

Two evaluation contexts, deliberately decoupled so each is validated against its
own state (no working-tree overlay is ever introduced into the pinned checkout):

* DefaultModeTests validate the CURRENT working tree in place. The working tree
  carries the 30-record public registry, so its production identity is the
  EXPECTED_* constants below (30 records / 161 edges / 39 inventory items).

* IntegrationTests reconstruct and validate a FIXED HISTORICAL commit
  (INTEGRATION_SHA) hermetically, using that commit's OWN builder and validator
  extracted alongside its content. The pinned commit carries a 27-record
  registry together with its own isolated-mode tooling, so its known output is
  the INTEGRATION_EXPECTED_* constants below (27 records / 146 edges / 36
  inventory items). The builder/validator are run from a clean generator extract
  of the pinned commit, never from the working tree, so the pinned commit's own
  record-count expectation (27) governs the build rather than the working tree's
  current expectation (30). This preserves the integration test's purpose —
  verifying that a fixed historical repository state can be reconstructed and
  validated consistently — without repointing INTEGRATION_SHA to a non-existent
  commit and without overlaying working-tree content.

Two fixture levels are used:

A. A checked-in minimal synthetic fixture (tests/fixtures/public-surface-candidate)
   for CLI, isolation, inventory, and import-isolation unit tests.
B. A full production integration source (and its own generator), materialised at
   test time from the pinned commit into temporary directories (never committed).
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path


GENERATOR_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = GENERATOR_ROOT / "scripts"
FIXTURE = GENERATOR_ROOT / "tests" / "fixtures" / "public-surface-candidate"
# Pinned historical commit reconstructed and validated by IntegrationTests using
# its own tooling. This is an existing commit that carries a 27-record registry
# together with the isolated-mode builder/validator (its own EXPECTED_RECORD_COUNT
# is 27), so IntegrationTests stay hermetic to it without any working-tree overlay.
INTEGRATION_SHA = "89550fea8317e535f9569461e71fec8d46e9ad8e"

# Default-mode / working-tree identity (current 30-record public registry).
# Used by DefaultModeTests, which build the tracked data.json in place.
EXPECTED_DATA_BYTES = 92903
EXPECTED_DATA_SHA256 = "3b1e5993a52cbce340b85472fea1ae5ea6f921cf8f7751d2d635edc7b17216ea"
EXPECTED_DATA_BLOB = "2d59c4fdd07a2a9ddfad94e2e214a2d1c84912af"
EXPECTED_NODES = 30
EXPECTED_EDGES = 161
EXPECTED_INVENTORY_COUNT = 39

# Pinned-commit historical identity (27-record registry at INTEGRATION_SHA),
# produced by that commit's own builder. Used by IntegrationTests only. These are
# intentionally distinct from the working-tree constants above: the integration
# test evaluates the pinned state against itself, not against the working tree.
INTEGRATION_EXPECTED_DATA_BYTES = 83727
INTEGRATION_EXPECTED_DATA_SHA256 = "82f7f74b98a9b3b94a9ed0b12a394f1db2d9b5d256f700d311061c1353f4ef1e"
INTEGRATION_EXPECTED_DATA_BLOB = "aa25de9c60b0c0bcb2f8fec1f82bafc135e1f10b"
INTEGRATION_EXPECTED_NODES = 27
INTEGRATION_EXPECTED_EDGES = 146
INTEGRATION_EXPECTED_INVENTORY_COUNT = 36

ALL_PURPOSES = {
    "direct_input",
    "scope_context",
    "registry_referenced_document",
    "classification_evidence",
    "reference_existence_check",
    "schema",
}


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load_module("builder_under_test", "build_public_surface_authority_map.py")
validator = load_module("validator_under_test", "validate_public_metadata.py")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_sha1_bytes(data: bytes) -> str:
    """Compute Git blob identity without depending on either builder module."""
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def tree_digest(root: Path) -> str:
    """Order-independent digest of a directory tree (paths + content)."""
    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_file() or path.is_symlink():
            rel = str(path.relative_to(root))
            try:
                data = path.read_bytes()
            except OSError:
                data = b"<unreadable>"
            entries.append(rel + ":" + sha256_bytes(data))
    return sha256_bytes("\n".join(entries).encode("utf-8"))


def isolated_env() -> dict:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PYTHONNOUSERSITE"] = "1"
    return env


def run_cli_from(scripts_dir: Path, script: str, args, cwd: Path):
    """Run a builder/validator script from an explicit scripts directory.

    Lets IntegrationTests invoke the pinned commit's OWN tooling (extracted into a
    clean generator directory) rather than the working-tree scripts, keeping the
    integration build hermetic to INTEGRATION_SHA and governed by that commit's
    record-count expectation.
    """
    return subprocess.run(
        [sys.executable, str(scripts_dir / script), *args],
        cwd=str(cwd),
        env=isolated_env(),
        capture_output=True,
        text=True,
    )


def run_cli(script: str, args, cwd: Path):
    return run_cli_from(SCRIPTS, script, args, cwd)


class BaseCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = Path(tempfile.mkdtemp(prefix="phase3b1-"))
        # Working directory kept strictly outside both roots.
        cls._cwd = cls._tmp / "cwd"
        cls._cwd.mkdir()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def out_dir(self) -> Path:
        d = Path(tempfile.mkdtemp(prefix="out-", dir=self._tmp))
        return d


def materialise_integration_source(dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    archived = subprocess.run(
        ["git", "-C", str(GENERATOR_ROOT), "archive", "--format=tar", INTEGRATION_SHA],
        capture_output=True,
    )
    if archived.returncode != 0:
        raise unittest.SkipTest(
            "integration source commit is not available locally: "
            + archived.stderr.decode("utf-8", "replace")
        )
    with tarfile.open(fileobj=io.BytesIO(archived.stdout)) as tar:
        tar.extractall(dest)


class DefaultModeTests(BaseCase):
    def test_default_builder_bytes_identical(self):
        # Snapshot the tracked production data.json, run the default builder in
        # place, and confirm the bytes are unchanged and match the identity.
        data_path = GENERATOR_ROOT / "visualizations" / "public-surface-authority-map" / "data.json"
        original = data_path.read_bytes()
        try:
            result = run_cli("build_public_surface_authority_map.py", [], cwd=GENERATOR_ROOT)
            self.assertEqual(result.returncode, 0, result.stderr)
            produced = data_path.read_bytes()
            self.assertEqual(len(produced), EXPECTED_DATA_BYTES)
            self.assertEqual(sha256_bytes(produced), EXPECTED_DATA_SHA256)
            self.assertEqual(git_blob_sha1_bytes(produced), EXPECTED_DATA_BLOB)
            parsed = json.loads(produced)
            self.assertEqual(len(parsed["nodes"]), EXPECTED_NODES)
            self.assertEqual(len(parsed["edges"]), EXPECTED_EDGES)
            inventory = builder.build_dependency_inventory(GENERATOR_ROOT.resolve())
            self.assertEqual(inventory["dependency_count"], EXPECTED_INVENTORY_COUNT)
            self.assertEqual(produced, original, "default builder changed tracked data.json")
        finally:
            data_path.write_bytes(original)

    def test_default_validator_passes(self):
        result = run_cli("validate_public_metadata.py", [], cwd=GENERATOR_ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Public metadata validation passed.", result.stdout)


class IntegrationTests(BaseCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Source content and generator tooling are both materialised from the
        # pinned commit, into SEPARATE directories. The generator is a clean
        # extract (never the source under test), which keeps source/generator
        # separation intact and lets the import-isolation test poison the source
        # without touching the generator that actually runs.
        cls.src = cls._tmp / "prod-source"
        materialise_integration_source(cls.src)
        cls.gen = cls._tmp / "prod-generator"
        materialise_integration_source(cls.gen)
        cls.gen_scripts = cls.gen / "scripts"

    def _build(self, out_dir: Path, source_root: Path | None = None):
        source = self.src if source_root is None else source_root
        out = out_dir / "data.json"
        inv = out_dir / "inventory.json"
        result = run_cli_from(
            self.gen_scripts,
            "build_public_surface_authority_map.py",
            ["--source-root", str(source), "--output", str(out), "--inventory-output", str(inv)],
            cwd=self._cwd,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return out, inv

    def test_integration_exact_identity(self):
        out, inv = self._build(self.out_dir())
        data = out.read_bytes()
        self.assertEqual(len(data), INTEGRATION_EXPECTED_DATA_BYTES)
        self.assertEqual(sha256_bytes(data), INTEGRATION_EXPECTED_DATA_SHA256)
        self.assertEqual(git_blob_sha1_bytes(data), INTEGRATION_EXPECTED_DATA_BLOB)
        parsed = json.loads(data)
        self.assertEqual(len(parsed["nodes"]), INTEGRATION_EXPECTED_NODES)
        self.assertEqual(len(parsed["edges"]), INTEGRATION_EXPECTED_EDGES)
        inventory = json.loads(inv.read_text("utf-8"))
        self.assertEqual(inventory["dependency_count"], INTEGRATION_EXPECTED_INVENTORY_COUNT)

    def test_two_runs_byte_identical(self):
        a_out, a_inv = self._build(self.out_dir())
        b_out, b_inv = self._build(self.out_dir())
        self.assertEqual(a_out.read_bytes(), b_out.read_bytes())
        self.assertEqual(a_inv.read_bytes(), b_inv.read_bytes())

    def test_output_and_inventory_outside_both_roots(self):
        out_dir = self.out_dir()
        out, inv = self._build(out_dir)
        for produced in (out, inv):
            resolved = produced.resolve()
            self.assertFalse(str(resolved).startswith(str(self.src.resolve())))
            self.assertFalse(str(resolved).startswith(str(self.gen.resolve())))
            self.assertFalse(str(resolved).startswith(str(GENERATOR_ROOT.resolve())))
            self.assertTrue(produced.is_file())

    def test_source_root_unchanged_after_success(self):
        before = tree_digest(self.src)
        self._build(self.out_dir())
        self.assertEqual(before, tree_digest(self.src))

    def test_generator_root_unchanged_after_run(self):
        # The generator that actually runs is the pinned extract (cls.gen); a
        # successful isolated build must not modify it. The working-tree scripts
        # are also confirmed untouched (the run never invokes them).
        watched = [
            self.gen / "scripts" / "build_public_surface_authority_map.py",
            self.gen / "scripts" / "validate_public_metadata.py",
            self.gen / "visualizations" / "public-surface-authority-map" / "data.json",
            SCRIPTS / "build_public_surface_authority_map.py",
            SCRIPTS / "validate_public_metadata.py",
        ]
        before = {p: p.read_bytes() for p in watched}
        self._build(self.out_dir())
        for p, data in before.items():
            self.assertEqual(p.read_bytes(), data, f"generator file changed: {p}")

    def test_content_derived_from_source(self):
        # Modify a node name only in the source; the output must reflect it and
        # therefore differ from the pinned known-output identity.
        src2 = self._tmp / "prod-source-modified"
        shutil.copytree(self.src, src2)
        docs_path = src2 / "mwe-public-documents.json"
        docs = json.loads(docs_path.read_text("utf-8"))
        docs["@graph"][0]["name"] = "SOURCE-DERIVED-MARKER"
        docs_path.write_text(json.dumps(docs, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        out, _ = self._build(self.out_dir(), source_root=src2)
        produced = out.read_text("utf-8")
        self.assertIn("SOURCE-DERIVED-MARKER", produced)
        self.assertNotEqual(sha256_bytes(out.read_bytes()), INTEGRATION_EXPECTED_DATA_SHA256)

    def test_preflight_passes_without_inventory(self):
        result = run_cli_from(
            self.gen_scripts,
            "validate_public_metadata.py",
            ["--source-root", str(self.src), "--mode", "preflight"],
            cwd=self._cwd,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_verify_inventory_passes(self):
        out, inv = self._build(self.out_dir())
        result = run_cli_from(
            self.gen_scripts,
            "validate_public_metadata.py",
            ["--source-root", str(self.src), "--mode", "verify-inventory", "--inventory", str(inv)],
            cwd=self._cwd,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_verify_inventory_requires_inventory(self):
        result = run_cli_from(
            self.gen_scripts,
            "validate_public_metadata.py",
            ["--source-root", str(self.src), "--mode", "verify-inventory"],
            cwd=self._cwd,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_verify_rejects_tampered_inventories(self):
        out, inv = self._build(self.out_dir())
        base = json.loads(inv.read_text("utf-8"))

        def check_rejected(mutate):
            data = json.loads(json.dumps(base))
            mutate(data)
            path = self.out_dir() / "tampered.json"
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            result = run_cli_from(
                self.gen_scripts,
                "validate_public_metadata.py",
                ["--source-root", str(self.src), "--mode", "verify-inventory", "--inventory", str(path)],
                cwd=self._cwd,
            )
            self.assertNotEqual(result.returncode, 0)

        def add_extra(d):
            d["files"].append(
                {"path": "AGENTS.md", "byte_length": 1, "sha256": "0" * 64,
                 "git_blob_sha1": "0" * 40, "read_purposes": ["schema"]}
            )
            d["dependency_count"] = len(d["files"])

        def drop_entry(d):
            d["files"] = d["files"][1:]
            d["dependency_count"] = len(d["files"])

        def mismatch_identity(d):
            d["files"][10]["byte_length"] += 1

        def uppercase_digest(d):
            d["files"][0]["sha256"] = d["files"][0]["sha256"].upper()

        def unknown_field(d):
            d["files"][0]["surprise"] = True

        def wrong_purpose(d):
            for f in d["files"]:
                if f["path"] == "scripts/validate_public_metadata.py":
                    f["read_purposes"] = ["schema"]

        for mutate in (add_extra, drop_entry, mismatch_identity, uppercase_digest, unknown_field, wrong_purpose):
            with self.subTest(mutate=mutate.__name__):
                check_rejected(mutate)

    def test_inventory_identities_and_ordering(self):
        out, inv = self._build(self.out_dir())
        inventory = json.loads(inv.read_text("utf-8"))
        files = inventory["files"]
        paths = [f["path"] for f in files]
        self.assertEqual(paths, sorted(paths))
        self.assertEqual(len(paths), len(set(paths)))
        universe = set()
        for f in files:
            self.assertEqual(f["read_purposes"], sorted(set(f["read_purposes"])))
            self.assertTrue(set(f["read_purposes"]).issubset(ALL_PURPOSES))
            self.assertRegex(f["sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(f["git_blob_sha1"], r"^[0-9a-f]{40}$")
            self.assertNotIn("\\", f["path"])
            self.assertFalse(f["path"].startswith("/"))
            data = (self.src / f["path"]).read_bytes()
            self.assertEqual(f["byte_length"], len(data))
            self.assertEqual(f["sha256"], sha256_bytes(data))
            self.assertEqual(f["git_blob_sha1"], git_blob_sha1_bytes(data))
            universe |= set(f["read_purposes"])
        self.assertEqual(universe, ALL_PURPOSES)

    def test_inventory_has_no_volatile_evidence(self):
        out, inv = self._build(self.out_dir())
        text = inv.read_text("utf-8")
        inventory = json.loads(text)
        self.assertEqual(set(inventory), {
            "inventory_schema_version", "source_repository", "interface_version",
            "dependency_count", "aggregate_sha256", "files",
        })
        # No absolute source path, home path, or obvious timestamp leaks.
        self.assertNotIn(str(self.src), text)
        self.assertNotIn(str(self.src.resolve()), text)
        self.assertNotIn("/home/", text)
        for token in ("timestamp", "generated_at", "runtime", "hostname", "username", "run_id"):
            self.assertNotIn(token, text)

    def test_boundary_statements_unchanged(self):
        out, _ = self._build(self.out_dir())
        data = json.loads(out.read_text("utf-8"))
        self.assertEqual(
            data["boundary_statements"],
            [
                "Selected public surface only.",
                "Visual position does not indicate conceptual importance or internal authority.",
                "Reference routing does not establish a confirmed conceptual relation.",
                "Omission does not imply nonexistence.",
            ],
        )
        self.assertEqual(data["edges"][0]["relation_status"], "navigation_only")

    def test_import_isolation_source_modules_not_executed(self):
        # Copy the integration source and plant poison modules that raise on
        # import (a stdlib shadow and a builder shadow). A correct isolated run
        # must succeed, proving the source root is never on sys.path and its
        # Python is treated only as data.
        poisoned = self._tmp / "poisoned-source"
        shutil.copytree(self.src, poisoned)
        (poisoned / "json.py").write_text('raise RuntimeError("source json.py imported")\n', "utf-8")
        (poisoned / "scripts" / "build_public_surface_authority_map.py").write_text(
            'raise RuntimeError("source builder imported")\n', "utf-8"
        )
        out = self.out_dir() / "data.json"
        inv = self.out_dir() / "inventory.json"
        # The generator is the clean pinned extract (self.gen_scripts); the source
        # is the poisoned copy. A correct run never executes the poisoned source
        # Python, proving the source root is never placed on sys.path.
        build = run_cli_from(
            self.gen_scripts,
            "build_public_surface_authority_map.py",
            ["--source-root", str(poisoned), "--output", str(out), "--inventory-output", str(inv)],
            cwd=self._cwd,
        )
        self.assertEqual(build.returncode, 0, build.stderr)
        self.assertNotIn("RuntimeError", build.stderr)
        self.assertEqual(len(out.read_bytes()), INTEGRATION_EXPECTED_DATA_BYTES)
        verify = run_cli_from(
            self.gen_scripts,
            "validate_public_metadata.py",
            ["--source-root", str(poisoned), "--mode", "verify-inventory", "--inventory", str(inv)],
            cwd=self._cwd,
        )
        self.assertEqual(verify.returncode, 0, verify.stderr)
        self.assertNotIn("RuntimeError", verify.stderr)


class RejectionTests(BaseCase):
    def test_missing_direct_input_fails(self):
        empty = self._tmp / "empty-source"
        empty.mkdir(exist_ok=True)
        out = self.out_dir() / "data.json"
        inv = self.out_dir() / "inventory.json"
        result = run_cli(
            "build_public_surface_authority_map.py",
            ["--source-root", str(empty), "--output", str(out), "--inventory-output", str(inv)],
            cwd=self._cwd,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(out.exists())

    def test_missing_indirect_referenced_file_fails(self):
        # Remove a referenced source file; inventory identity read must fail.
        src = self._tmp / "fixture-missing-ref"
        shutil.copytree(FIXTURE, src)
        (src / "doc-a.md").unlink()
        with self.assertRaises(SystemExit):
            builder.build_dependency_inventory(src.resolve())

    def test_malformed_metadata_fails_without_repair(self):
        src = self._tmp / "fixture-malformed"
        shutil.copytree(FIXTURE, src)
        (src / "mwe-public-documents.json").write_text("{ not valid json ", "utf-8")
        before = tree_digest(src)  # snapshot the malformed state; builder must not repair it
        out = self.out_dir() / "data.json"
        inv = self.out_dir() / "inventory.json"
        result = run_cli(
            "build_public_surface_authority_map.py",
            ["--source-root", str(src), "--output", str(out), "--inventory-output", str(inv)],
            cwd=self._cwd,
        )
        self.assertNotEqual(result.returncode, 0)
        # Source not repaired (still malformed), and no output written.
        self.assertIn("not valid json", (src / "mwe-public-documents.json").read_text("utf-8"))
        self.assertEqual(before, tree_digest(src))
        self.assertFalse(out.exists())

    def test_output_inside_source_rejected(self):
        src = self._tmp / "fixture-outsrc"
        if not src.exists():
            shutil.copytree(FIXTURE, src)
        inside = src / "sneaky-data.json"
        inv = self.out_dir() / "inventory.json"
        result = run_cli(
            "build_public_surface_authority_map.py",
            ["--source-root", str(src), "--output", str(inside), "--inventory-output", str(inv)],
            cwd=self._cwd,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(inside.exists())

    def test_inventory_inside_source_rejected(self):
        src = self._tmp / "fixture-invsrc"
        if not src.exists():
            shutil.copytree(FIXTURE, src)
        out = self.out_dir() / "data.json"
        inside = src / "sneaky-inv.json"
        result = run_cli(
            "build_public_surface_authority_map.py",
            ["--source-root", str(src), "--output", str(out), "--inventory-output", str(inside)],
            cwd=self._cwd,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(inside.exists())

    def test_output_inside_generator_rejected(self):
        src = self._tmp / "fixture-outgen"
        if not src.exists():
            shutil.copytree(FIXTURE, src)
        inside = GENERATOR_ROOT / "phase3b1-should-not-exist.json"
        inv = self.out_dir() / "inventory.json"
        result = run_cli(
            "build_public_surface_authority_map.py",
            ["--source-root", str(src), "--output", str(inside), "--inventory-output", str(inv)],
            cwd=self._cwd,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(inside.exists())

    def test_inventory_inside_generator_rejected(self):
        src = self._tmp / "fixture-invgen"
        if not src.exists():
            shutil.copytree(FIXTURE, src)
        out = self.out_dir() / "data.json"
        inside = GENERATOR_ROOT / "phase3b1-inv-should-not-exist.json"
        result = run_cli(
            "build_public_surface_authority_map.py",
            ["--source-root", str(src), "--output", str(out), "--inventory-output", str(inside)],
            cwd=self._cwd,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(inside.exists())

    def test_isolated_mode_requires_all_three_flags(self):
        src = self._tmp / "fixture-partial"
        if not src.exists():
            shutil.copytree(FIXTURE, src)
        result = run_cli(
            "build_public_surface_authority_map.py",
            ["--source-root", str(src)],
            cwd=self._cwd,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires", result.stderr)


class PathResolutionUnitTests(BaseCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(dir=self._tmp)).resolve()
        (self.root / "inside.md").write_text("ok\n", "utf-8")

    def test_relative_traversal_rejected(self):
        self.assertIsNone(builder.resolve_under_root(self.root, "../escape.md"))
        self.assertIsNone(builder.resolve_under_root(self.root, "a/../../escape.md"))

    def test_absolute_input_rejected(self):
        self.assertIsNone(builder.resolve_under_root(self.root, "/etc/passwd"))

    def test_drive_absolute_input_rejected_on_current_host(self):
        self.assertIsNone(builder.resolve_under_root(self.root, "C:/x"))

    def test_drive_relative_input_rejected_on_current_host(self):
        self.assertIsNone(builder.resolve_under_root(self.root, "C:relative"))

    def test_inside_path_accepted(self):
        resolved = builder.resolve_under_root(self.root, "inside.md")
        self.assertIsNotNone(resolved)
        self.assertTrue(str(resolved).startswith(str(self.root)))

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unsupported on platform")
    def test_symlink_escape_rejected(self):
        outside = self._tmp / "outside-secret.md"
        outside.write_text("secret\n", "utf-8")
        link = self.root / "evil.md"
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlink creation unsupported: {exc}")
        self.assertIsNone(builder.resolve_under_root(self.root, "evil.md"))

    def test_reparse_point_platform_note(self):
        if os.name != "nt":
            self.skipTest(
                "NTFS junctions / reparse points are Windows-only; POSIX symlink "
                "escape is covered by test_symlink_escape_rejected. Reparse-point "
                "coverage is not established on this platform."
            )

    def test_output_isolation_helper(self):
        gen = self.root  # pretend generator root
        src = Path(tempfile.mkdtemp(dir=self._tmp)).resolve()
        with self.assertRaises(SystemExit):
            builder.resolve_isolated_output(str(src / "x.json"), src, gen, "--output")
        with self.assertRaises(SystemExit):
            builder.resolve_isolated_output(str(gen / "y.json"), src, gen, "--output")
        ok = builder.resolve_isolated_output(str(self._tmp / "safe.json"), src, gen, "--output")
        self.assertTrue(str(ok).startswith(str(self._tmp.resolve())))


class InventorySchemaUnitTests(BaseCase):
    def _valid_inventory(self):
        return builder.build_dependency_inventory(FIXTURE.resolve())

    def test_fixture_inventory_structurally_valid(self):
        errors = []
        self.assertTrue(validator.validate_inventory_structure(self._valid_inventory(), errors))
        self.assertEqual(errors, [])

    def _assert_inventory_path_rejected(self, path):
        inventory = self._valid_inventory()
        inventory["files"][0]["path"] = path
        errors = []
        validator.validate_inventory_structure(inventory, errors)
        self.assertTrue(any("repository-relative" in error for error in errors), errors)

    def test_rejects_drive_absolute_inventory_path_on_current_host(self):
        self._assert_inventory_path_rejected("C:/x")

    def test_rejects_drive_relative_inventory_path_on_current_host(self):
        self._assert_inventory_path_rejected("C:relative")

    def test_rejects_unknown_top_field(self):
        inv = self._valid_inventory()
        inv["unexpected"] = 1
        errors = []
        validator.validate_inventory_structure(inv, errors)
        self.assertTrue(any("unknown top-level" in e for e in errors))

    def test_rejects_unknown_item_field(self):
        inv = self._valid_inventory()
        inv["files"][0]["unexpected"] = 1
        errors = []
        validator.validate_inventory_structure(inv, errors)
        self.assertTrue(any("unknown fields" in e for e in errors))

    def test_rejects_uppercase_sha256(self):
        inv = self._valid_inventory()
        inv["files"][0]["sha256"] = inv["files"][0]["sha256"].upper()
        errors = []
        validator.validate_inventory_structure(inv, errors)
        self.assertTrue(any("sha256" in e for e in errors))

    def test_rejects_bad_git_blob(self):
        inv = self._valid_inventory()
        inv["files"][0]["git_blob_sha1"] = "XYZ"
        errors = []
        validator.validate_inventory_structure(inv, errors)
        self.assertTrue(any("git_blob_sha1" in e for e in errors))

    def test_rejects_unsorted_purposes(self):
        inv = self._valid_inventory()
        for f in inv["files"]:
            if len(f["read_purposes"]) > 1:
                f["read_purposes"] = list(reversed(f["read_purposes"]))
                break
        errors = []
        validator.validate_inventory_structure(inv, errors)
        self.assertTrue(any("unique and sorted" in e for e in errors))

    def test_rejects_bad_purpose_value(self):
        inv = self._valid_inventory()
        inv["files"][0]["read_purposes"] = ["not_a_real_purpose"]
        errors = []
        validator.validate_inventory_structure(inv, errors)
        self.assertTrue(any("invalid read_purposes" in e for e in errors))

    def test_rejects_count_mismatch(self):
        inv = self._valid_inventory()
        inv["dependency_count"] += 1
        errors = []
        validator.validate_inventory_structure(inv, errors)
        self.assertTrue(any("dependency_count" in e for e in errors))

    def test_fixture_covers_all_purposes(self):
        purposes = builder.collect_read_purposes(FIXTURE.resolve())
        universe = set()
        for values in purposes.values():
            universe |= values
        self.assertEqual(universe, ALL_PURPOSES)


class SchemaFileAndHygieneTests(BaseCase):
    def test_inventory_schema_file_is_strict(self):
        schema_path = GENERATOR_ROOT / "mwe-public-surface-dependency-inventory.schema.json"
        schema = json.loads(schema_path.read_text("utf-8"))
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertFalse(schema["additionalProperties"])
        item = schema["properties"]["files"]["items"]
        self.assertFalse(item["additionalProperties"])
        path_pattern = item["properties"]["path"]["pattern"]
        self.assertEqual(path_pattern, r"^(?!/)(?![A-Za-z]:)(?!.*\.\.)(?!.*\\)[^\\]+$")
        for rejected in ("C:/x", "C:relative", "/absolute", "../escape", r"directory\file.json"):
            self.assertIsNone(re.fullmatch(path_pattern, rejected), rejected)
        for accepted in (
            "mwe-public-documents.json",
            "scripts/validate_public_metadata.py",
            "directory/file.json",
        ):
            self.assertIsNotNone(re.fullmatch(path_pattern, accepted), accepted)
        self.assertEqual(item["properties"]["sha256"]["pattern"], "^[0-9a-f]{64}$")
        self.assertEqual(item["properties"]["git_blob_sha1"]["pattern"], "^[0-9a-f]{40}$")
        self.assertEqual(
            set(item["properties"]["read_purposes"]["items"]["enum"]), ALL_PURPOSES
        )

    def test_scripts_use_standard_library_only(self):
        forbidden = ("import requests", "urllib", "http.client", "socket", "subprocess", "pip ", "import pip")
        for name in ("build_public_surface_authority_map.py", "validate_public_metadata.py"):
            text = (SCRIPTS / name).read_text("utf-8")
            for token in forbidden:
                self.assertNotIn(token, text, f"{name} references forbidden module token {token!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
