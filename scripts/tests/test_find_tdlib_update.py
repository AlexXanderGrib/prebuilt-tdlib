import base64
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError


spec = importlib.util.spec_from_file_location(
    "find_tdlib_update", Path(__file__).resolve().parents[1] / "find-tdlib-update.py"
)
updates = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updates)

REPOSITORY = "example/prebuilt-tdlib"


def release(version, **kwargs):
    return {
        "tag_name": f"0.{version}-abcdef0",
        "draft": False,
        "prerelease": False,
        **kwargs,
    }


HEAD = "c" * 40


class UpdateTests(unittest.TestCase):
    def github(self, releases, version="1.8.70", source=None):
        github = updates.GitHub(None)

        def get(endpoint, **params):
            if endpoint.endswith("/releases"):
                start = (params["page"] - 1) * params["per_page"]
                return releases[start:start + params["per_page"]]
            if endpoint == "repos/tdlib/td/commits/master":
                return {"sha": HEAD, "commit": {"message": "Ordinary upstream change."}}
            if endpoint == "repos/tdlib/td/contents/CMakeLists.txt":
                self.assertEqual(params, {"ref": HEAD})
                cmake = source if source is not None else (
                    f"project(TDLib VERSION {version} LANGUAGES CXX C)\n"
                )
                return {"content": base64.b64encode(cmake.encode()).decode()}
            self.fail(f"Unexpected API endpoint: {endpoint}")

        github.get = Mock(side_effect=get)
        return github

    def test_catches_up_to_latest_version_at_upstream_head(self):
        github = self.github([release("1.8.67")])
        self.assertEqual(
            updates.find_update(github, REPOSITORY),
            {"ref": HEAD, "version": "1.8.70"},
        )

    def test_published_version_is_not_built_again(self):
        github = self.github([release("1.8.70")])
        self.assertIsNone(updates.find_update(github, REPOSITORY))

    def test_does_not_downgrade_published_version(self):
        github = self.github([release("1.8.71")])
        self.assertIsNone(updates.find_update(github, REPOSITORY))

    def test_unpublished_build_is_selected_again(self):
        github = self.github([release("1.8.67")])
        first = updates.find_update(github, REPOSITORY)
        self.assertIsNotNone(first)
        self.assertEqual(updates.find_update(github, REPOSITORY), first)

    def test_ignores_drafts_prereleases_and_unrelated_releases(self):
        releases = [
            release("1.8.70", draft=True),
            release("1.8.70", prerelease=True),
            release("1.8.70", tag_name="tools-v9"),
            release("1.8.67"),
        ]
        self.assertEqual(
            updates.find_update(self.github(releases), REPOSITORY)["version"], "1.8.70"
        )

    def test_compares_versions_numerically_not_release_order(self):
        github = self.github([release("1.8.9"), release("1.8.99")], "1.8.100")
        self.assertEqual(updates.find_update(github, REPOSITORY)["version"], "1.8.100")

    def test_empty_repository_starts_at_upstream_head(self):
        self.assertEqual(
            updates.find_update(self.github([]), REPOSITORY),
            {"ref": HEAD, "version": "1.8.70"},
        )

    def test_paginates_releases(self):
        github = self.github([release("1.8.67")] * 100 + [release("1.8.70")])
        self.assertIsNone(updates.find_update(github, REPOSITORY))
        github.get.assert_any_call(f"repos/{REPOSITORY}/releases", per_page=100, page=2)

    def test_rejects_missing_or_malformed_cmake_version(self):
        for source in ["", "project(Other VERSION 1.8.70 LANGUAGES CXX)",
                       "project(TDLib VERSION 1.8 LANGUAGES CXX)"]:
            with self.subTest(source=source), self.assertRaisesRegex(
                RuntimeError, "Cannot read TDLib version"
            ):
                updates.find_update(self.github([], source=source), REPOSITORY)

    def test_api_failure_fails_check_without_writing_output(self):
        error = HTTPError("https://api.github.com", 403, "Forbidden", {}, None)
        github = Mock()
        github.paginate.side_effect = error
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            with patch.object(updates, "GitHub", return_value=github), patch.dict(
                os.environ, {"GITHUB_REPOSITORY": REPOSITORY, "GITHUB_OUTPUT": str(output)}
            ), patch("sys.argv", ["find-tdlib-update.py"]):
                with self.assertRaises(HTTPError):
                    updates.main()
            self.assertFalse(output.exists())

    def test_writes_github_output_for_update_and_no_update(self):
        for candidate, expected in [({"ref": "a" * 40, "version": "1.8.68"}, "a" * 40), (None, "")]:
            with self.subTest(candidate=candidate), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "output"
                with patch.object(updates, "find_update", return_value=candidate), patch.dict(
                    os.environ, {"GITHUB_REPOSITORY": REPOSITORY, "GITHUB_OUTPUT": str(output)}
                ), patch("sys.argv", ["find-tdlib-update.py"]), patch("builtins.print"):
                    updates.main()
                self.assertEqual(output.read_text(), f"ref={expected}\n")


if __name__ == "__main__":
    unittest.main()
