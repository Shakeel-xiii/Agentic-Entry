
import json
import urllib.request
import urllib.error
from urllib.parse import quote
from urllib.parse import urlparse
import re
from datetime import datetime


REQUIREMENTS_FILE = "requirements.txt"
PYPI_URL = "https://pypi.org/pypi"


def parse_requirement(line):
    """Extract package name and an optional pinned version."""
    line = line.split("#", 1)[0].strip()

    if not line or line.startswith("-") or line.startswith("#"):
        return None

    match = re.match(
        r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(.*)$",
        line
    )

    if not match:
        return None

    package = match.group(1)
    specifier = match.group(2).strip()

    version = None
    pinned = re.search(r"===?\s*([A-Za-z0-9.+!_-]+)", specifier)

    if pinned:
        version = pinned.group(1)

    return package, version


def fetch_json(url):
    """Fetch JSON data from PyPI."""
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Agentic-Entry-Requirements-Checker/1.0"}
    )

    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def check_package(package, version):
    """Check a package and its pinned version against PyPI."""
    project_url = f"{PYPI_URL}/{quote(package, safe='')}/json"

    try:
        project_data = fetch_json(project_url)

    except urllib.error.HTTPError as error:
        if error.code == 404:
            return {
                "package": package,
                "status": "missing",
                "version": version
            }

        return {
            "package": package,
            "status": "error",
            "version": version,
            "message": f"HTTP {error.code}"
        }

    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        return {
            "package": package,
            "status": "error",
            "version": version,
            "message": str(error)
        }

    releases = project_data.get("releases", {})

    if version and version not in releases:
        return {
            "package": package,
            "status": "bad_version",
            "version": version
        }

    # Find the oldest release that actually has uploaded files.
    valid_releases = []

    for release, files in releases.items():
        upload_times = [
            file["upload_time"]
            for file in files
            if file.get("upload_time")
        ]

        if upload_times:
            valid_releases.append((release, min(upload_times)))

    oldest_release = None

    if valid_releases:
        oldest_release = min(
            valid_releases,
            key=lambda item: item[1]
        )[0]

    return {
        "package": package,
        "status": "ok",
        "version": version,
        "oldest_release": oldest_release
    }



def main():
    try:
        with open(REQUIREMENTS_FILE, "r", encoding="utf-8") as file:
            lines = file.readlines()
    except FileNotFoundError:
        print("Error: requirements.txt not found.")
        return

    results = []

    for line in lines:
        requirement = parse_requirement(line)
        if requirement is None:
            continue

        package, version = requirement
        results.append(check_package(package, version))

    checked = len(results)
    missing = sum(1 for r in results if r["status"] == "missing")
    bad_versions = sum(1 for r in results if r["status"] == "bad_version")

    oldest = None
    for result in results:
        if result["status"] == "ok" and result["version"]:
            if result["oldest_release"]:
                release = result["oldest_release"]
                year = next(
                    (
                        datetime.fromisoformat(item["upload_time"].replace("Z", "+00:00")).year
                        for item in fetch_json(
                            f"{PYPI_URL}/{quote(result['package'], safe='')}/{quote(release, safe='')}/json"
                        ).get("urls", [])
                        if item.get("upload_time")
                    ),
                    None
                )

                if year is not None:
                    oldest = (result["package"], release, year)
                    break

    print(f"dependencies checked: {checked}")
    print(f"Packages not on PyPI: {missing}")
    print(f"versions not on PyPI: {bad_versions}")

    if oldest:
        print(f"oldest pinned release: {oldest[0]}=={oldest[1]} ({oldest[2]})")
    else:
        print("oldest pinned release: none found")


if __name__ == "__main__":
    main()