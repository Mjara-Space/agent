from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
