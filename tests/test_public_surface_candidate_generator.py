#!/usr/bin/env python3
"""Phase 3B-1 tests: explicit source-root, isolated output, dependency inventory.

Standard-library unittest only (no third-party dependency). These tests cover
the isolated candidate mode of the public-surface authority-map builder and the
preflight / verify-inventory modes of the public-metadata validator:

- historical-target verification and validator backward compatibility;
- source/generator separation (content read only from the explicit source root);
- output/inventory isolation outside both roots;
- path traversal and symlink/reparse-point escape rejection;
- deterministic snapshot and inventory bytes;
- dependency-inventory schema, coverage, ordering, and identity recomputation;
- source-root Python import isolation (no execution of source-tree modules);
- historical artifact identity (exactly 92,903 bytes / 30 records);
- historical generator isolation: verification writes nothing, and no expanded
  output can resolve to the historical artifact path;
- pinned-commit historical identity (exactly 83,727 bytes / 27 records);
- source-root and generator-root no-write proofs on success and failure.

Two evaluation contexts, deliberately decoupled so each is validated against its
own state (no working-tree overlay is ever introduced into the pinned checkout):

* DefaultModeTests validate the CURRENT working tree in place. The working tree
  carries the 30-record public registry, so its production identity is the
  EXPECTED_* constants below (30 records / 161 edges / 39 inventory items).
  These tests no longer write the tracked artifact: in-place regeneration is
  retired, and both the zero-argument invocation and --target historical are
  verify-only.

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

import contextlib
import errno
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
from unittest import mock


GENERATOR_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = GENERATOR_ROOT / "scripts"
FIXTURE = GENERATOR_ROOT / "tests" / "fixtures" / "public-surface-candidate"
# Pinned historical commit reconstructed and validated by IntegrationTests using
# its own tooling. This is an existing commit that carries a 27-record registry
# together with the isolated-mode builder/validator (its own EXPECTED_RECORD_COUNT
# is 27), so IntegrationTests stay hermetic to it without any working-tree overlay.
INTEGRATION_SHA = "89550fea8317e535f9569461e71fec8d46e9ad8e"

# Historical artifact identity (the frozen 30-record public registry snapshot).
# Used by DefaultModeTests, which verify the tracked data.json without writing
# it: in-place regeneration of this path is retired.
EXPECTED_DATA_BYTES = 92903
EXPECTED_DATA_SHA256 = "3b1e5993a52cbce340b85472fea1ae5ea6f921cf8f7751d2d635edc7b17216ea"
EXPECTED_DATA_BLOB = "2d59c4fdd07a2a9ddfad94e2e214a2d1c84912af"
EXPECTED_NODES = 30
EXPECTED_EDGES = 161
EXPECTED_INVENTORY_COUNT = 39
EXPECTED_BOUNDARY_REFERENCE_EDGES = 132
EXPECTED_SOURCE_USE_REFERENCE_EDGES = 29
EXPECTED_SELF_REFERENCES_OMITTED = 7

# Source commit the historical artifact is reconstructed from. Distinct from
# INTEGRATION_SHA, which pins a different, earlier state.
HISTORICAL_SOURCE_COMMIT = "3219fa03149b4bf1a229f059b4912b632028422b"

HISTORICAL_DATA_RELATIVE = "visualizations/public-surface-authority-map/data.json"
HISTORICAL_DATA_PATH = GENERATOR_ROOT / "visualizations" / "public-surface-authority-map" / "data.json"

# Expanded target: a separate generation target with its own record count and no
# implicit output path. No expanded artifact is produced by these tests.
EXPANDED_RECORD_COUNT = 59

# Pinned generation source commit for the expanded adjacency product (P5). Used
# only by the synthetic expanded fixture manifest below.
EXPANDED_SOURCE_COMMIT = "933274af9693d6d1d9fac36819aafdf56f9ab81d"

# The pre-expansion registry size. After P3 the live registry carries 59 records,
# so the expanded target's record-count protection is proved against an isolated
# synthetic source of this size rather than against the live registry.
HISTORICAL_RECORD_COUNT_FIXTURE = 30

# Stable failure tokens emitted by the builder.
FAILURE_HISTORICAL_ARTIFACT_IDENTITY_MISMATCH = "HISTORICAL_ARTIFACT_IDENTITY_MISMATCH"
FAILURE_HISTORICAL_OUTPUT_PATH_COLLISION = "HISTORICAL_OUTPUT_PATH_COLLISION"
FAILURE_EXPANDED_TARGET_REQUIRES_OUTPUT = "EXPANDED_TARGET_REQUIRES_OUTPUT"

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


def materialise_commit(sha: str, dest: Path, label: str) -> None:
    """Extract a pinned commit into a clean temporary directory."""
    dest.mkdir(parents=True, exist_ok=True)
    archived = subprocess.run(
        ["git", "-C", str(GENERATOR_ROOT), "archive", "--format=tar", sha],
        capture_output=True,
    )
    if archived.returncode != 0:
        raise unittest.SkipTest(
            f"{label} commit is not available locally: "
            + archived.stderr.decode("utf-8", "replace")
        )
    with tarfile.open(fileobj=io.BytesIO(archived.stdout)) as tar:
        tar.extractall(dest)


def materialise_integration_source(dest: Path) -> None:
    materialise_commit(INTEGRATION_SHA, dest, "integration source")


class DefaultModeTests(BaseCase):
    """Zero-argument and explicit-historical behaviour.

    The former default mode rebuilt the tracked data.json in place and restored
    it afterwards. That behaviour is retired: the historical artifact is
    immutable and both invocations are verify-only. Every assertion the previous
    builder test made about the produced bytes is retained here against the
    tracked artifact, which the builder no longer writes.
    """

    def test_historical_artifact_identity(self):
        produced = HISTORICAL_DATA_PATH.read_bytes()
        result = run_cli("build_public_surface_authority_map.py", [], cwd=GENERATOR_ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)

        self.assertEqual(len(produced), EXPECTED_DATA_BYTES)
        self.assertEqual(sha256_bytes(produced), EXPECTED_DATA_SHA256)
        self.assertEqual(git_blob_sha1_bytes(produced), EXPECTED_DATA_BLOB)
        parsed = json.loads(produced)
        self.assertEqual(len(parsed["nodes"]), EXPECTED_NODES)
        self.assertEqual(len(parsed["edges"]), EXPECTED_EDGES)

        # The dependency-inventory count is deliberately NOT recomputed here.
        # It is a property of HISTORICAL_SOURCE_COMMIT, not of the live working
        # tree, and rebuilding it from the live root would couple historical
        # verification to current registry contents. It is asserted against the
        # pinned source in HistoricalReconstructionTests instead.

        # Structural invariants the artifact itself carries.
        self.assertEqual(
            parsed["edge_counts"]["boundary_reference"], EXPECTED_BOUNDARY_REFERENCE_EDGES
        )
        self.assertEqual(
            parsed["edge_counts"]["source_use_reference"], EXPECTED_SOURCE_USE_REFERENCE_EDGES
        )
        self.assertEqual(
            parsed["self_references_omitted_count"], EXPECTED_SELF_REFERENCES_OMITTED
        )

        # The bytes on disk are still the bytes read before the run.
        self.assertEqual(HISTORICAL_DATA_PATH.read_bytes(), produced)

    def test_historical_verification_reports_pinned_identity(self):
        for args in ([], ["--target", "historical"]):
            with self.subTest(args=args):
                result = run_cli("build_public_surface_authority_map.py", args, cwd=GENERATOR_ROOT)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Nothing was written", result.stdout)
                self.assertIn(HISTORICAL_SOURCE_COMMIT, result.stdout)
                for pinned in (
                    str(EXPECTED_DATA_BYTES),
                    EXPECTED_DATA_SHA256,
                    EXPECTED_DATA_BLOB,
                    str(EXPECTED_BOUNDARY_REFERENCE_EDGES),
                    str(EXPECTED_SOURCE_USE_REFERENCE_EDGES),
                    str(EXPECTED_SELF_REFERENCES_OMITTED),
                    str(EXPECTED_INVENTORY_COUNT),
                ):
                    self.assertIn(pinned, result.stdout)

    def test_pinned_constants_match_generator_specification(self):
        # The builder's pinned historical specification and this module's
        # expectations cannot drift apart.
        self.assertEqual(builder.HISTORICAL_DATA_BYTES, EXPECTED_DATA_BYTES)
        self.assertEqual(builder.HISTORICAL_DATA_SHA256, EXPECTED_DATA_SHA256)
        self.assertEqual(builder.HISTORICAL_DATA_BLOB, EXPECTED_DATA_BLOB)
        self.assertEqual(builder.HISTORICAL_NODE_COUNT, EXPECTED_NODES)
        self.assertEqual(builder.HISTORICAL_EDGE_COUNT, EXPECTED_EDGES)
        self.assertEqual(
            builder.HISTORICAL_BOUNDARY_REFERENCE_EDGES, EXPECTED_BOUNDARY_REFERENCE_EDGES
        )
        self.assertEqual(
            builder.HISTORICAL_SOURCE_USE_REFERENCE_EDGES, EXPECTED_SOURCE_USE_REFERENCE_EDGES
        )
        self.assertEqual(
            builder.HISTORICAL_SELF_REFERENCES_OMITTED, EXPECTED_SELF_REFERENCES_OMITTED
        )
        self.assertEqual(
            builder.HISTORICAL_DEPENDENCY_INVENTORY_COUNT, EXPECTED_INVENTORY_COUNT
        )
        self.assertEqual(builder.HISTORICAL_SOURCE_COMMIT, HISTORICAL_SOURCE_COMMIT)
        self.assertEqual(builder.HISTORICAL_RECORD_COUNT, EXPECTED_NODES)
        self.assertEqual(builder.EXPANDED_RECORD_COUNT, EXPANDED_RECORD_COUNT)
        self.assertEqual(builder.HISTORICAL_OUTPUT_FILE, HISTORICAL_DATA_RELATIVE)
        self.assertEqual(
            builder.FAILURE_HISTORICAL_ARTIFACT_IDENTITY_MISMATCH,
            FAILURE_HISTORICAL_ARTIFACT_IDENTITY_MISMATCH,
        )
        self.assertEqual(
            builder.FAILURE_HISTORICAL_OUTPUT_PATH_COLLISION,
            FAILURE_HISTORICAL_OUTPUT_PATH_COLLISION,
        )
        self.assertEqual(
            builder.FAILURE_EXPANDED_TARGET_REQUIRES_OUTPUT,
            FAILURE_EXPANDED_TARGET_REQUIRES_OUTPUT,
        )

    def test_default_validator_passes(self):
        result = run_cli("validate_public_metadata.py", [], cwd=GENERATOR_ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Public metadata validation passed.", result.stdout)


class HistoricalReconstructionTests(BaseCase):
    """Git-pinned reconstruction of the historical artifact.

    This is the ONLY place the 39-entry dependency-inventory count is proven.
    That count is a property of HISTORICAL_SOURCE_COMMIT, not of the live
    registry, so it is asserted here against a clean extract of that commit
    rather than recomputed from the working tree. Historical verification must
    keep passing when the live registry changes; recomputing the inventory from
    the live root would break that guarantee.

    Distinct from IntegrationTests, which pin a different, earlier commit and
    run that commit's own tooling. This class runs the CURRENT tree's isolated
    candidate mode against the pinned historical source.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.src = cls._tmp / "historical-source"
        materialise_commit(HISTORICAL_SOURCE_COMMIT, cls.src, "historical source")

    def test_pinned_source_reconstructs_the_tracked_artifact(self):
        out_dir = self.out_dir()
        out = out_dir / "data.json"
        inv = out_dir / "inventory.json"

        # Outputs live outside both the source root and the generator root.
        for target in (out, inv):
            self.assertFalse(str(target).startswith(str(self.src.resolve())))
            self.assertFalse(str(target).startswith(str(GENERATOR_ROOT.resolve())))

        result = run_cli(
            "build_public_surface_authority_map.py",
            [
                "--source-root", str(self.src),
                "--output", str(out),
                "--inventory-output", str(inv),
            ],
            cwd=self._cwd,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        produced = out.read_bytes()
        self.assertEqual(len(produced), EXPECTED_DATA_BYTES)
        self.assertEqual(sha256_bytes(produced), EXPECTED_DATA_SHA256)
        self.assertEqual(git_blob_sha1_bytes(produced), EXPECTED_DATA_BLOB)
        parsed = json.loads(produced)
        self.assertEqual(len(parsed["nodes"]), EXPECTED_NODES)
        self.assertEqual(len(parsed["edges"]), EXPECTED_EDGES)

        # The 39-entry inventory identity, proven from the pinned source.
        inventory = json.loads(inv.read_text("utf-8"))
        self.assertEqual(inventory["dependency_count"], EXPECTED_INVENTORY_COUNT)
        self.assertEqual(len(inventory["files"]), EXPECTED_INVENTORY_COUNT)

        # Byte-identical to the tracked historical artifact.
        self.assertEqual(produced, HISTORICAL_DATA_PATH.read_bytes())

        # Temporary reconstruction files are removed.
        shutil.rmtree(out_dir)
        self.assertFalse(out_dir.exists())

    def test_reconstruction_leaves_the_tracked_artifact_untouched(self):
        before = HISTORICAL_DATA_PATH.read_bytes()
        before_mtime_ns = HISTORICAL_DATA_PATH.stat().st_mtime_ns
        out_dir = self.out_dir()
        result = run_cli(
            "build_public_surface_authority_map.py",
            [
                "--source-root", str(self.src),
                "--output", str(out_dir / "data.json"),
                "--inventory-output", str(out_dir / "inventory.json"),
            ],
            cwd=self._cwd,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(HISTORICAL_DATA_PATH.read_bytes(), before)
        self.assertEqual(HISTORICAL_DATA_PATH.stat().st_mtime_ns, before_mtime_ns)
        shutil.rmtree(out_dir)


class HistoricalLiveRegistryIsolationTests(BaseCase):
    """Historical verification must not depend on live registry contents.

    P3 expands the registry from 30 to 59 records without touching P2 files, so
    verification has to keep passing across that change. These tests prove the
    dependency does not exist, rather than asserting it will not matter.
    """

    def test_verification_never_builds_the_live_inventory(self):
        def explode(*args, **kwargs):
            raise AssertionError(
                "historical verification must not touch live-registry code paths"
            )

        for name in (
            "build_dependency_inventory",
            "collect_read_purposes",
            "assemble_map_data",
            "load_json",
        ):
            with self.subTest(function=name):
                with mock.patch.object(builder, name, explode), \
                        contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(builder.run_historical(), 0)

    def test_cli_verifies_without_any_registry_present(self):
        # A generator root holding only the builder and the artifact: no
        # mwe-public-documents.json, no mwe-public-surface.json. Verification
        # must still succeed, which is only possible if it reads neither.
        root = self.out_dir() / "generator-root"
        (root / "scripts").mkdir(parents=True)
        shutil.copy2(
            SCRIPTS / "build_public_surface_authority_map.py", root / "scripts"
        )
        artifact_dir = root / "visualizations" / "public-surface-authority-map"
        artifact_dir.mkdir(parents=True)
        shutil.copy2(HISTORICAL_DATA_PATH, artifact_dir / "data.json")

        self.assertFalse((root / "mwe-public-documents.json").exists())
        self.assertFalse((root / "mwe-public-surface.json").exists())

        for args in ([], ["--target", "historical"]):
            with self.subTest(args=args):
                result = run_cli_from(
                    root / "scripts",
                    "build_public_surface_authority_map.py",
                    args,
                    cwd=self._cwd,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Nothing was written", result.stdout)
                # The pinned inventory count is reported, not recomputed.
                self.assertIn(str(EXPECTED_INVENTORY_COUNT), result.stdout)

    def test_cli_verifies_against_a_divergent_registry(self):
        # Same isolated generator root, but carrying a registry that does not
        # describe the artifact. Verification must be indifferent to it.
        root = self.out_dir() / "generator-root-divergent"
        (root / "scripts").mkdir(parents=True)
        shutil.copy2(
            SCRIPTS / "build_public_surface_authority_map.py", root / "scripts"
        )
        artifact_dir = root / "visualizations" / "public-surface-authority-map"
        artifact_dir.mkdir(parents=True)
        shutil.copy2(HISTORICAL_DATA_PATH, artifact_dir / "data.json")
        (root / "mwe-public-documents.json").write_text(
            json.dumps({"record_count": EXPANDED_RECORD_COUNT, "@graph": []}) + "\n",
            encoding="utf-8",
        )

        result = run_cli_from(
            root / "scripts", "build_public_surface_authority_map.py", [], cwd=self._cwd
        )
        self.assertEqual(result.returncode, 0, result.stderr)


class HistoricalNoWriteTests(BaseCase):
    """Proof that verification never touches the tracked artifact."""

    def _snapshot(self):
        stat = HISTORICAL_DATA_PATH.stat()
        data = HISTORICAL_DATA_PATH.read_bytes()
        return {
            "bytes": data,
            "length": len(data),
            "sha256": sha256_bytes(data),
            "git_blob": git_blob_sha1_bytes(data),
            "mtime_ns": stat.st_mtime_ns,
        }

    def _assert_no_write(self, args):
        before = self._snapshot()
        result = run_cli("build_public_surface_authority_map.py", args, cwd=GENERATOR_ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        after = self._snapshot()
        for key in ("bytes", "length", "sha256", "git_blob", "mtime_ns"):
            self.assertEqual(before[key], after[key], f"{key} changed for args {args!r}")

    def test_zero_argument_invocation_writes_nothing(self):
        self._assert_no_write([])

    def test_explicit_historical_target_writes_nothing(self):
        self._assert_no_write(["--target", "historical"])

    def test_verification_creates_no_sibling_artifact(self):
        directory = HISTORICAL_DATA_PATH.parent
        before = sorted(p.name for p in directory.iterdir())
        for args in ([], ["--target", "historical"]):
            result = run_cli("build_public_surface_authority_map.py", args, cwd=GENERATOR_ROOT)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, sorted(p.name for p in directory.iterdir()))

    def test_explicit_historical_target_rejects_output_flags(self):
        # An explicit historical target must never be able to regenerate the
        # artifact, so it accepts no output-bearing flag at all.
        out = self.out_dir() / "data.json"
        for args in (
            ["--target", "historical", "--output", str(out)],
            ["--target", "historical", "--source-root", str(FIXTURE)],
            ["--target", "historical", "--inventory-output", str(out)],
        ):
            with self.subTest(args=args):
                before = self._snapshot()
                result = run_cli("build_public_surface_authority_map.py", args, cwd=GENERATOR_ROOT)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("verify-only", result.stderr)
                self.assertFalse(out.exists())
                self.assertEqual(before, self._snapshot())


class HistoricalIdentityFailureTests(BaseCase):
    """HISTORICAL_ARTIFACT_IDENTITY_MISMATCH, proven without touching the
    tracked artifact.

    The mismatch path is exercised through dependency injection against an
    isolated temporary copy. The tracked historical file is never edited and
    never restored.
    """

    def _run_against(self, data: bytes | None):
        path = self.out_dir() / "injected-data.json"
        if data is not None:
            path.write_bytes(data)
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                builder.run_historical(path)
        return raised.exception.code, stderr.getvalue()

    def test_missing_artifact_emits_failure_token(self):
        before = HISTORICAL_DATA_PATH.read_bytes()
        code, stderr = self._run_against(None)
        self.assertNotEqual(code, 0)
        self.assertIn(FAILURE_HISTORICAL_ARTIFACT_IDENTITY_MISMATCH, stderr)
        self.assertEqual(HISTORICAL_DATA_PATH.read_bytes(), before)

    def test_altered_bytes_emit_failure_token(self):
        before_stat = HISTORICAL_DATA_PATH.stat()
        before = HISTORICAL_DATA_PATH.read_bytes()
        code, stderr = self._run_against(before + b"\n")
        self.assertNotEqual(code, 0)
        self.assertIn(FAILURE_HISTORICAL_ARTIFACT_IDENTITY_MISMATCH, stderr)
        self.assertIn("byte length", stderr)
        self.assertIn("sha256", stderr)
        self.assertIn("git blob", stderr)
        # The tracked artifact was never the subject of the run.
        self.assertEqual(HISTORICAL_DATA_PATH.read_bytes(), before)
        self.assertEqual(HISTORICAL_DATA_PATH.stat().st_mtime_ns, before_stat.st_mtime_ns)

    def test_structurally_unreadable_artifact_emits_failure_token(self):
        # Readable bytes, unparseable content. Distinct from the filesystem
        # read failure covered below.
        code, stderr = self._run_against(b"{ not valid json ")
        self.assertNotEqual(code, 0)
        self.assertIn(FAILURE_HISTORICAL_ARTIFACT_IDENTITY_MISMATCH, stderr)

    def test_permission_error_emits_failure_token(self):
        # A file that exists but cannot be read must fail closed with the stable
        # token, not with a traceback. The tracked artifact's permissions are
        # never altered; the failure is injected at the read call.
        path = self.out_dir() / "denied.json"
        path.write_bytes(b"placeholder")
        before = HISTORICAL_DATA_PATH.read_bytes()
        before_mtime_ns = HISTORICAL_DATA_PATH.stat().st_mtime_ns

        def denied(self_, *args, **kwargs):
            raise PermissionError(errno.EACCES, "denied")

        stderr = io.StringIO()
        with mock.patch.object(Path, "read_bytes", denied), \
                contextlib.redirect_stderr(stderr), \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                builder.run_historical(path)

        self.assertNotEqual(raised.exception.code, 0)
        message = stderr.getvalue()
        self.assertIn(FAILURE_HISTORICAL_ARTIFACT_IDENTITY_MISMATCH, message)
        self.assertIn("unable to read tracked historical artifact", message)
        self.assertIn("denied", message)
        self.assertEqual(HISTORICAL_DATA_PATH.read_bytes(), before)
        self.assertEqual(HISTORICAL_DATA_PATH.stat().st_mtime_ns, before_mtime_ns)

    def test_os_error_on_read_emits_failure_token(self):
        # Any OSError, not only PermissionError, fails closed the same way.
        path = self.out_dir() / "io-error.json"
        path.write_bytes(b"placeholder")

        def io_error(self_, *args, **kwargs):
            raise OSError(errno.EIO, "input/output error")

        stderr = io.StringIO()
        with mock.patch.object(Path, "read_bytes", io_error), \
                contextlib.redirect_stderr(stderr), \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                builder.run_historical(path)

        self.assertNotEqual(raised.exception.code, 0)
        self.assertIn(FAILURE_HISTORICAL_ARTIFACT_IDENTITY_MISMATCH, stderr.getvalue())

    def test_structural_invariants_are_checked(self):
        original = json.loads(HISTORICAL_DATA_PATH.read_text("utf-8"))

        def mutated(mutate):
            data = json.loads(json.dumps(original))
            mutate(data)
            return json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"

        cases = {
            "nodes": lambda d: d["nodes"].pop(),
            "edges": lambda d: d["edges"].pop(),
            "boundary-reference edges": lambda d: d["edge_counts"].update(
                {"boundary_reference": 0}
            ),
            "source-use-reference edges": lambda d: d["edge_counts"].update(
                {"source_use_reference": 0}
            ),
            "self-references omitted": lambda d: d.update(
                {"self_references_omitted_count": 0}
            ),
        }
        for label, mutate in cases.items():
            with self.subTest(invariant=label):
                mismatches = builder.historical_identity_mismatches(mutated(mutate))
                self.assertTrue(
                    any(entry.startswith(label + ":") for entry in mismatches),
                    f"{label} not reported in {mismatches}",
                )

    def test_unmodified_bytes_report_no_mismatch(self):
        self.assertEqual(
            builder.historical_identity_mismatches(HISTORICAL_DATA_PATH.read_bytes()), []
        )


class ExpandedTargetTests(BaseCase):
    """Expanded-target contract and the historical path-collision guard."""

    def _snapshot(self):
        stat = HISTORICAL_DATA_PATH.stat()
        data = HISTORICAL_DATA_PATH.read_bytes()
        return data, stat.st_mtime_ns

    def _thirty_record_generator_root(self, name: str) -> Path:
        """Build an isolated generator root carrying a deliberate 30-record registry.

        The expanded target's record-count protection used to be provable against
        the live registry, because the live registry held 30 records. P3 expands
        it to 59, so that assumption is stale. The contract itself is unchanged
        and is proved here against an isolated historical-shape source instead:
        a synthetic 30-record registry, outside the repository, that the expanded
        target must refuse because it expects 59.

        Nothing here reads or writes the live registry, and no expanded artifact
        is produced. The temporary root is removed with the class temp directory.
        """
        root = self.out_dir() / name
        (root / "scripts").mkdir(parents=True)
        shutil.copy2(SCRIPTS / "build_public_surface_authority_map.py", root / "scripts")

        # A clearly synthetic fixture standing in for the pre-expansion registry
        # shape: the count is what the target checks, not the record contents.
        fixture_records = [
            {"repository_path": f"fixture-record-{index:02d}.md"}
            for index in range(1, HISTORICAL_RECORD_COUNT_FIXTURE + 1)
        ]
        (root / "mwe-public-documents.json").write_text(
            json.dumps(
                {
                    "record_count": HISTORICAL_RECORD_COUNT_FIXTURE,
                    "@graph": fixture_records,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        # Read-only copies: the surface manifest is loaded for scope
        # confirmation, and the artifact copy lets the path-collision guard
        # establish identity instead of failing closed on a missing artifact.
        shutil.copy2(GENERATOR_ROOT / "mwe-public-surface.json", root)
        artifact_dir = root / "visualizations" / "public-surface-authority-map"
        artifact_dir.mkdir(parents=True)
        shutil.copy2(HISTORICAL_DATA_PATH, artifact_dir / "data.json")

        # P5 makes --visualization-manifest mandatory for the expanded target.
        # A syntactically valid placeholder manifest is written here so the
        # record-count guard below is still what stops the run: the registry
        # count is checked before any manifest content is compared, so this
        # fixture proves the same contract it always did.
        manifest_dir = root / "visualizations" / "public-surface-adjacency-map"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "visualization-manifest.json").write_text(
            json.dumps(
                {
                    "$schema": "./visualization-manifest.schema.json",
                    "manifest_version": "1.0",
                    "describes": "../../mwe-public-documents.json",
                    "scope": "expanded_public_surface_visualization_membership",
                    "authority_ceiling": "visualization_membership_and_rendering_policy_only",
                    "source_commit": EXPANDED_SOURCE_COMMIT,
                    "record_count": EXPANDED_RECORD_COUNT,
                    "records": [],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return root

    def _fixture_manifest(self, root: Path) -> Path:
        return (
            root
            / "visualizations"
            / "public-surface-adjacency-map"
            / "visualization-manifest.json"
        )

    def test_missing_output_emits_failure_token(self):
        before = self._snapshot()
        result = run_cli(
            "build_public_surface_authority_map.py", ["--target", "expanded"], cwd=GENERATOR_ROOT
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(FAILURE_EXPANDED_TARGET_REQUIRES_OUTPUT, result.stderr)
        self.assertEqual(before, self._snapshot())

    def test_expanded_expects_fifty_nine_records(self):
        # The expanded target must stop on its own record-count protection
        # rather than accept a 30-record source as a valid expanded dataset.
        # Proved against an isolated 30-record source, not the live registry.
        before = self._snapshot()
        root = self._thirty_record_generator_root("thirty-record-source")
        out = self.out_dir() / "expanded.json"
        result = run_cli_from(
            root / "scripts",
            "build_public_surface_authority_map.py",
            [
                "--target",
                "expanded",
                "--visualization-manifest",
                str(self._fixture_manifest(root)),
                "--output",
                str(out),
            ],
            cwd=self._cwd,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(str(EXPANDED_RECORD_COUNT), result.stderr)
        self.assertIn(str(HISTORICAL_RECORD_COUNT_FIXTURE), result.stderr)
        self.assertFalse(out.exists(), "expanded target left an artifact behind")
        self.assertEqual(builder.EXPANDED_RECORD_COUNT, EXPANDED_RECORD_COUNT)
        self.assertNotEqual(builder.EXPANDED_RECORD_COUNT, builder.HISTORICAL_RECORD_COUNT)
        # The live registry was neither read for this nor written to, and the
        # frozen artifact is untouched.
        self.assertEqual(before, self._snapshot())

    def test_expanded_count_guard_at_the_assembly_helper(self):
        # The same contract at unit level: the assembly helper refuses a
        # 30-record source under the expanded count. No output path is involved,
        # so no expanded artifact can be produced even transiently.
        root = self._thirty_record_generator_root("thirty-record-helper-source")
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()) as err:
            builder.assemble_map_data(root.resolve(), builder.EXPANDED_RECORD_COUNT)
        self.assertIn(str(EXPANDED_RECORD_COUNT), err.getvalue())

    def _assert_collision_rejected(self, output_arg, cwd):
        before_bytes, before_mtime_ns = self._snapshot()
        directory = HISTORICAL_DATA_PATH.parent
        before_names = sorted(p.name for p in directory.iterdir())

        result = run_cli(
            "build_public_surface_authority_map.py",
            ["--target", "expanded", "--output", str(output_arg)],
            cwd=cwd,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(FAILURE_HISTORICAL_OUTPUT_PATH_COLLISION, result.stderr)

        after_bytes, after_mtime_ns = self._snapshot()
        self.assertEqual(before_bytes, after_bytes)
        self.assertEqual(before_mtime_ns, after_mtime_ns)
        # No temporary replacement file was left beside the artifact.
        self.assertEqual(before_names, sorted(p.name for p in directory.iterdir()))
        return result

    def test_exact_historical_relative_path_rejected(self):
        self._assert_collision_rejected(HISTORICAL_DATA_RELATIVE, GENERATOR_ROOT)

    def test_absolute_historical_path_rejected(self):
        self._assert_collision_rejected(HISTORICAL_DATA_PATH.resolve(), self._cwd)

    def test_parent_traversal_to_historical_path_rejected(self):
        traversing = (
            GENERATOR_ROOT.resolve()
            / "scripts"
            / ".."
            / "visualizations"
            / "public-surface-authority-map"
            / "data.json"
        )
        self.assertIn("..", traversing.parts)
        self._assert_collision_rejected(traversing, self._cwd)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unsupported on platform")
    def test_symlink_alias_of_historical_path_rejected(self):
        link = self.out_dir() / "historical-alias.json"
        try:
            os.symlink(HISTORICAL_DATA_PATH.resolve(), link)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlink creation unsupported: {exc}")
        self.assertTrue(link.is_symlink())
        self._assert_collision_rejected(link, self._cwd)

    def _hard_link_to_historical(self, name):
        """Create a hard link to the tracked artifact outside the repository.

        Tries the shared temporary root first, then a directory on the same
        filesystem as the repository, so a cross-device temporary directory does
        not turn a real gap into a silent skip. Skips only when hard links are
        genuinely unavailable or the filesystem documents them as unsupported.
        """
        if not hasattr(os, "link"):
            self.skipTest("os.link is unavailable on this platform")

        source = HISTORICAL_DATA_PATH.resolve()
        unsupported = {errno.EXDEV, errno.EPERM, errno.EMLINK, errno.EOPNOTSUPP, errno.ENOSYS}
        candidates = [self.out_dir()]
        beside_repository = Path(tempfile.mkdtemp(dir=GENERATOR_ROOT.parent))
        self.addCleanup(shutil.rmtree, beside_repository, ignore_errors=True)
        candidates.append(beside_repository)

        last = None
        for directory in candidates:
            link = directory / name
            try:
                os.link(source, link)
            except NotImplementedError as exc:
                self.skipTest(f"hard links unsupported on this platform: {exc}")
            except OSError as exc:
                if exc.errno in unsupported:
                    last = exc
                    continue
                raise
            return link
        self.skipTest(f"hard links unsupported on the available filesystems: {last}")

    def test_hard_link_alias_of_historical_path_rejected(self):
        link = self._hard_link_to_historical("historical-hardlink.json")

        # A hard link is a distinct pathname that resolves to itself, so
        # resolved-path equality alone cannot catch it.
        self.assertFalse(link.is_symlink())
        self.assertNotEqual(link.resolve(), HISTORICAL_DATA_PATH.resolve())
        self.assertTrue(link.samefile(HISTORICAL_DATA_PATH))

        link_before = link.read_bytes()
        result = self._assert_collision_rejected(link, self._cwd)

        # Rejection happens before record-count processing: the expanded
        # target's 59-record error never appears.
        self.assertNotIn("record_count", result.stderr)
        self.assertNotIn(str(EXPANDED_RECORD_COUNT), result.stderr)
        self.assertEqual(link.read_bytes(), link_before)
        self.assertTrue(link.samefile(HISTORICAL_DATA_PATH))

    def test_hard_link_guard_is_same_file_identity(self):
        link = self._hard_link_to_historical("historical-hardlink-unit.json")
        with self.assertRaises(SystemExit):
            builder.resolve_expanded_output(str(link))

    def test_ordinary_existing_output_is_not_a_collision(self):
        # The same-file check must not reject an unrelated file that merely
        # exists: such a path proceeds and stops on the record-count guard.
        # Run against the isolated 30-record source so the guard is observed
        # without generating an expanded dataset from the live 59-record registry.
        root = self._thirty_record_generator_root("thirty-record-collision-source")
        existing = self.out_dir() / "unrelated.json"
        existing.write_text("{}\n", encoding="utf-8")
        result = run_cli_from(
            root / "scripts",
            "build_public_surface_authority_map.py",
            [
                "--target",
                "expanded",
                "--visualization-manifest",
                str(self._fixture_manifest(root)),
                "--output",
                str(existing),
            ],
            cwd=self._cwd,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(FAILURE_HISTORICAL_OUTPUT_PATH_COLLISION, result.stderr)
        self.assertIn(str(EXPANDED_RECORD_COUNT), result.stderr)
        self.assertEqual(existing.read_text("utf-8"), "{}\n")

    def test_guard_compares_resolved_paths(self):
        # Unit-level proof that the guard resolves rather than string-matches.
        with self.assertRaises(SystemExit):
            builder.resolve_expanded_output(str(HISTORICAL_DATA_PATH.resolve()))
        safe = builder.resolve_expanded_output(str(self.out_dir() / "elsewhere.json"))
        self.assertNotEqual(safe, HISTORICAL_DATA_PATH.resolve())

    def test_expanded_target_rejects_isolated_flags(self):
        out = self.out_dir() / "expanded.json"
        inv = self.out_dir() / "inventory.json"
        for extra in (["--source-root", str(FIXTURE)], ["--inventory-output", str(inv)]):
            with self.subTest(extra=extra):
                result = run_cli(
                    "build_public_surface_authority_map.py",
                    ["--target", "expanded", "--output", str(out), *extra],
                    cwd=GENERATOR_ROOT,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(out.exists())


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
