from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from agent.base import AgentException
from agent.bench import Bench


class TestBenchGeneratedAssets(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.bench_dir = self.test_dir / "bench"
        self.sites_dir = self.bench_dir / "sites"
        self.apps_dir = self.bench_dir / "apps"
        self.sites_assets_dir = self.sites_dir / "assets"
        self.sites_assets_dir.mkdir(parents=True)
        self.apps_dir.mkdir(parents=True)

        self.bench = object.__new__(Bench)
        self.bench.directory = str(self.bench_dir)
        self.bench.sites_directory = str(self.sites_dir)
        self.bench.apps_file = str(self.sites_dir / "apps.txt")
        self.bench.server = Mock()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _create_drive_app(self, asset_name="index-new.js", include_public_asset=True):
        app_root = self.apps_dir / "drive"
        app_public_assets = app_root / "drive" / "public" / "frontend" / "assets"
        app_www = app_root / "drive" / "www"
        app_public_assets.mkdir(parents=True)
        app_www.mkdir(parents=True)

        (app_root / "pyproject.toml").write_text(
            """
[tool.bench.assets]
index_html_path = "drive/www/drive.html"
""".strip()
        )
        (app_www / "drive.html").write_text(
            f'<script type="module" src="/assets/drive/frontend/assets/{asset_name}"></script>'
        )

        if include_public_asset:
            (app_public_assets / asset_name).write_text("console.log('drive')")

    def _create_drive_public_asset_without_config(self):
        app_public_assets = self.apps_dir / "drive" / "drive" / "public" / "frontend" / "assets"
        app_public_assets.mkdir(parents=True)
        (app_public_assets / "index-new.js").write_text("console.log('drive')")

    def test_sync_generated_app_assets_replaces_stale_assets(self):
        stale_assets = self.sites_assets_dir / "drive" / "frontend" / "assets"
        stale_assets.mkdir(parents=True)
        (stale_assets / "index-old.js").write_text("old")
        self._create_drive_app()

        result = self.bench.sync_generated_app_assets("drive")

        self.assertFalse(result["skipped"])
        self.assertEqual(result["missing_assets"], [])
        self.assertTrue(
            (self.sites_assets_dir / "drive" / "frontend" / "assets" / "index-new.js").exists()
        )
        self.assertFalse(
            (self.sites_assets_dir / "drive" / "frontend" / "assets" / "index-old.js").exists()
        )

    def test_sync_generated_app_assets_replaces_stale_symlink(self):
        stale_public = self.test_dir / "stale-public"
        stale_public.mkdir()
        (self.sites_assets_dir / "drive").symlink_to(stale_public)
        self._create_drive_app()

        result = self.bench.sync_generated_app_assets("drive")

        self.assertFalse(result["skipped"])
        self.assertFalse((self.sites_assets_dir / "drive").is_symlink())
        self.assertTrue(
            (self.sites_assets_dir / "drive" / "frontend" / "assets" / "index-new.js").exists()
        )

    def test_sync_generated_app_assets_copies_public_assets_without_config(self):
        self._create_drive_public_asset_without_config()

        result = self.bench.sync_generated_app_assets("drive")

        self.assertFalse(result["skipped"])
        self.assertEqual(result["missing_assets"], [])
        self.assertTrue(
            (self.sites_assets_dir / "drive" / "frontend" / "assets" / "index-new.js").exists()
        )

    def test_sync_generated_app_assets_copies_container_public_assets(self):
        with patch.object(
            self.bench,
            "docker_execute",
            return_value={"returncode": 0, "status": "Success", "output": ""},
        ) as docker_execute:
            result = self.bench.sync_generated_app_assets("drive")

        self.assertFalse(result["skipped"])
        docker_execute.assert_called_once()
        self.assertIn("bash -lc", docker_execute.call_args.args[0])
        self.assertIn("apps/drive/drive/public", docker_execute.call_args.args[0])
        self.assertIn("sites/assets/drive", docker_execute.call_args.args[0])

    def _create_dependency_fixture(self, name, relative=False, dangling=False):
        root = self.test_dir / name
        public = root / "apps" / "drive" / "drive" / "public"
        public.mkdir(parents=True)
        (root / "sites").symlink_to(self.sites_dir, target_is_directory=True)
        dependencies = root / "dependencies"
        if not dangling:
            for build in ("src-min-noconflict", "src-noconflict"):
                ace = dependencies / "ace-builds" / build
                ace.mkdir(parents=True)
                for filename in ("ace.js", "mode-python.js", "theme-textmate.js", "worker-json.js"):
                    (ace / filename).write_text(filename)
            (dependencies / "other.js").write_text("other dependency")
            (dependencies / ".bin").mkdir()
            (dependencies / ".bin" / "other").symlink_to("../other.js")
            (dependencies / ".bin" / "optional").symlink_to("../missing.js")
        target = os.path.relpath(dependencies, public) if relative else dependencies
        (public / "node_modules").symlink_to(target, target_is_directory=True)
        (public / "ordinary-link").symlink_to("missing-optional-file")
        return root, public, dependencies

    def _execute_container_script(self, command, root, env=None, **kwargs):
        args = shlex.split(command)
        self.assertEqual(args[:2], ["bash", "-lc"])
        self.assertEqual(len(args), 3)
        result = subprocess.run(
            ["bash", "-c", args[2]], cwd=root, capture_output=True, text=True, env=env
        )
        return {"returncode": result.returncode, "output": result.stdout + result.stderr}

    def _copy_fixture(self, root, public, container):
        if container:
            with patch.object(
                self.bench,
                "docker_execute",
                side_effect=lambda command, **kwargs: self._execute_container_script(
                    command, root, **kwargs
                ),
            ):
                self.assertTrue(self.bench.copy_container_public_assets("drive"))
        else:
            self.bench.copy_app_public_assets("drive", public)

    def test_public_node_modules_is_materialized_on_both_copy_paths(self):
        for container in (False, True):
            for relative in (False, True):
                with self.subTest(container=container, relative=relative):
                    root, public, dependencies = self._create_dependency_fixture(
                        f"fixture-{container}-{relative}", relative=relative
                    )
                    self._copy_fixture(root, public, container)
                    assets = self.sites_assets_dir / "drive"
                    copied = assets / "node_modules"
                    self.assertFalse(copied.is_symlink())
                    (assets / "stale.js").write_text("stale")
                    self._copy_fixture(root, public, container)
                    self.assertFalse((assets / "stale.js").exists())
                    self.assertFalse(copied.is_symlink())
                    shutil.rmtree(dependencies)
                    for build in ("src-min-noconflict", "src-noconflict"):
                        for filename in (
                            "ace.js",
                            "mode-python.js",
                            "theme-textmate.js",
                            "worker-json.js",
                        ):
                            self.assertEqual(
                                (copied / "ace-builds" / build / filename).read_text(), filename
                            )
                    self.assertEqual((copied / "other.js").read_text(), "other dependency")
                    self.assertEqual((copied / ".bin" / "other").read_text(), "other dependency")
                    self.assertEqual(os.readlink(copied / ".bin" / "other"), "../other.js")
                    self.assertTrue((copied / ".bin" / "optional").is_symlink())
                    self.assertTrue((assets / "ordinary-link").is_symlink())
                    self.assertEqual(list(self.sites_assets_dir.glob(".drive.sync-*")), [])

    def test_dangling_node_modules_link_is_preserved(self):
        for container in (False, True):
            with self.subTest(container=container):
                root, public, _ = self._create_dependency_fixture(
                    f"dangling-{container}", dangling=True
                )
                self._copy_fixture(root, public, container)
                copied = self.sites_assets_dir / "drive" / "node_modules"
                self.assertTrue(copied.is_symlink())
                self.assertEqual(os.readlink(copied), os.readlink(public / "node_modules"))

    def test_container_copy_replaces_stale_app_symlink(self):
        root, public, _ = self._create_dependency_fixture("stale-container")
        stale = self.test_dir / "stale-public"
        stale.mkdir()
        (stale / "keep.js").write_text("keep")
        (self.sites_assets_dir / "drive").symlink_to(stale)
        self._copy_fixture(root, public, container=True)
        self.assertFalse((self.sites_assets_dir / "drive").is_symlink())
        self.assertEqual((stale / "keep.js").read_text(), "keep")

    def test_container_missing_public_directory_is_skipped(self):
        with patch.object(
            self.bench,
            "docker_execute",
            side_effect=lambda command, **kwargs: self._execute_container_script(
                command, self.bench_dir, **kwargs
            ),
        ):
            result = self.bench.sync_generated_app_assets("drive")
        self.assertTrue(result["skipped"])
        self.assertEqual(result["reason"], "no_public_assets")
        self.assertEqual(list(self.sites_assets_dir.iterdir()), [])

    def test_container_copy_errors_are_not_reported_as_missing_public(self):
        for returncode in (1, 2, 125, 127):
            with self.subTest(returncode=returncode):
                with patch.object(
                    self.bench,
                    "docker_execute",
                    return_value={"returncode": returncode, "output": "copy failed"},
                ):
                    with self.assertRaises(AgentException) as error:
                        self.bench.sync_generated_app_assets("drive")
                self.assertEqual(error.exception.data["output"], "copy failed")
                self.assertIn("drive", error.exception.data["message"])

    def test_failed_dependency_copy_preserves_live_assets_and_cleans_staging(self):
        assets = self.sites_assets_dir / "drive"
        assets.mkdir()
        (assets / "keep.js").write_text("working assets")
        for container in (False, True):
            with self.subTest(container=container):
                root, public, dependencies = self._create_dependency_fixture(f"fail-{container}")
                if container:
                    bin_dir = root / "bin"
                    bin_dir.mkdir()
                    copy_command = bin_dir / "cp"
                    copy_command.write_text(
                        "#!/bin/sh\n"
                        'if [ "$2" = "$FAIL_COPY_SOURCE" ]; then\n'
                        '  printf "dependency copy failed\\n" >&2; exit 1\n'
                        "fi\n"
                        f'exec {shlex.quote(shutil.which("cp"))} "$@"\n'
                    )
                    copy_command.chmod(0o755)
                    env = {
                        **os.environ,
                        "PATH": f"{bin_dir}:{os.environ['PATH']}",
                        "FAIL_COPY_SOURCE": str(dependencies),
                    }
                    with patch.object(
                        self.bench,
                        "docker_execute",
                        side_effect=lambda command, **kwargs: self._execute_container_script(
                            command, root, env=env, **kwargs
                        ),
                    ):
                        with self.assertRaises(AgentException):
                            self.bench.copy_container_public_assets("drive")
                else:
                    copytree = shutil.copytree

                    def fail_dependency_copy(source, destination, *args, **kwargs):
                        if Path(source) == dependencies:
                            raise OSError("dependency copy failed")
                        return copytree(source, destination, *args, **kwargs)

                    with patch("agent.bench.shutil.copytree", side_effect=fail_dependency_copy):
                        with self.assertRaises(OSError):
                            self.bench.copy_app_public_assets("drive", public)
                self.assertEqual((assets / "keep.js").read_text(), "working assets")
                self.assertEqual(list(self.sites_assets_dir.glob(".drive.sync-*")), [])

    def test_sync_generated_app_assets_reports_missing_references(self):
        self._create_drive_app(asset_name="missing.js", include_public_asset=False)

        result = self.bench.sync_generated_app_assets("drive")

        self.assertEqual(result["missing_assets"], ["/assets/drive/frontend/assets/missing.js"])

    def test_sync_generated_assets_raises_when_any_app_is_missing_assets(self):
        (self.sites_dir / "apps.txt").write_text("frappe\ndrive\n")

        with patch.object(
            self.bench,
            "sync_generated_app_assets",
            return_value={
                "skipped": False,
                "reason": None,
                "missing_assets": ["/assets/drive/frontend/assets/missing.js"],
            },
        ) as sync_app_assets:
            with self.assertRaises(AgentException):
                self.bench.sync_generated_assets()

        self.assertEqual(
            [call.args[0] for call in sync_app_assets.call_args_list],
            ["drive", "frappe"],
        )

    def test_rebuild_syncs_generated_assets_after_successful_build(self):
        with (
            patch.object(
                self.bench,
                "docker_execute",
                return_value={"returncode": 0, "status": "Success", "output": ""},
            ) as docker_execute,
            patch.object(self.bench, "sync_generated_assets", return_value={"ok": True}) as sync_assets,
        ):
            result = self.bench.rebuild(apps=["drive"])

        self.assertEqual(result["status"], "Success")
        docker_execute.assert_called_once_with("bench build --app drive")
        sync_assets.assert_called_once_with()

    def test_rebuild_does_not_sync_generated_assets_after_failed_build(self):
        with (
            patch.object(
                self.bench,
                "docker_execute",
                side_effect=AgentException({"ok": False, "message": "build failed"}),
            ),
            patch.object(self.bench, "sync_generated_assets") as sync_assets,
            self.assertRaises(AgentException),
        ):
            self.bench.rebuild(apps=["drive"])

        sync_assets.assert_not_called()


if __name__ == "__main__":
    unittest.main()
