#!/usr/bin/env python3
"""Select upstream HEAD when its TDLib version is newer than our releases."""

import argparse
import base64
import json
import os
from pathlib import Path
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen


RELEASE_TAG = re.compile(r"0\.(\d+\.\d+\.\d+)-[0-9a-f]{7,40}")
PROJECT_VERSION = re.compile(r"^project\(TDLib VERSION (\d+\.\d+\.\d+)\s", re.MULTILINE)


def version_key(version):
    return tuple(int(part) for part in version.split("."))


class GitHub:
    def __init__(self, token):
        self.token = token

    def get(self, endpoint, **params):
        url = f"https://api.github.com/{endpoint}"
        if params:
            url += "?" + urlencode(params)
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "prebuilt-tdlib-update-check",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        with urlopen(Request(url, headers=headers), timeout=60) as response:
            return json.load(response)

    def paginate(self, endpoint, **params):
        page = 1
        while True:
            items = self.get(endpoint, per_page=100, page=page, **params)
            yield from items
            if len(items) < 100:
                return
            page += 1


def find_update(github, repository):
    published_versions = []
    for release in github.paginate(f"repos/{repository}/releases"):
        if release["draft"] or release["prerelease"]:
            continue
        match = RELEASE_TAG.fullmatch(release["tag_name"])
        if match:
            published_versions.append(version_key(match[1]))
    baseline = max(published_versions, default=None)

    # Resolve master once, then read and build that immutable revision. Commit
    # messages and the age of the version bump don't affect update discovery.
    revision = github.get("repos/tdlib/td/commits/master")["sha"]
    contents = github.get("repos/tdlib/td/contents/CMakeLists.txt", ref=revision)
    source = base64.b64decode(contents["content"]).decode()
    match = PROJECT_VERSION.search(source)
    if match is None:
        raise RuntimeError("Cannot read TDLib version from CMakeLists.txt")
    version = match[1]
    if baseline is not None and version_key(version) <= baseline:
        return None
    return {"ref": revision, "version": version}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--output", type=Path, default=os.environ.get("GITHUB_OUTPUT"))
    args = parser.parse_args()
    if not args.repository:
        parser.error("--repository or GITHUB_REPOSITORY is required")

    # Only published releases mark success. A failed build stays eligible on
    # the next scheduled run, even if metadata was already updated.
    candidate = find_update(GitHub(os.environ.get("GH_TOKEN")), args.repository)
    ref = candidate["ref"] if candidate else ""
    if args.output:
        with args.output.open("a") as output:
            output.write(f"ref={ref}\n")
    if candidate:
        print(f"Build TDLib {candidate['version']} from upstream commit {ref}")
    else:
        print("No newer TDLib version found.")


if __name__ == "__main__":
    main()
