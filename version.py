#!/usr/bin/env python3

#
# git@github.com:chris-garrett/python-version.git
#

# CHANGELOG
#
# Tue, May 7, 2024  - fix: strip-components wasnt actually using the value, add better error message, skip if 0
#                   - fix: dont return ValueErrors, raise them!
#
# Fri, May 3, 2024  - feat: expose strip-branch-components as a cli arg
#
# Thu, May 2, 2024  - fix: moved shell shebang to top of file
#                   - feat: dont strip tag prefix from tag. populate last_tag, last_hash, add timestamp (utc)
#                   - feat: cleanup cli args so they are more consistent. csv and csv-header, json and json-pretty
#
# Sun, Apr 21, 2024 - initial version
#

import argparse
import json
import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from subprocess import CompletedProcess

semver_rx = re.compile(r"\.")


class VersionIncrement(str, Enum):
    MAJOR = "MAJOR"
    MINOR = "MINOR"
    PATCH = "PATCH"

    def __str__(self) -> str:
        return self.value


@dataclass
class VersionContext:
    increment: VersionIncrement
    tag_prefix: str = None
    work_tree: str = None
    strip_branch_components: int = None


@dataclass
class Version:
    major: int = None
    minor: int = None
    patch: int = None
    commits: int = None
    hash: str = None
    branch: str = None

    last_tag: str = None
    last_hash: str = None
    tag: str = None
    tag_prefix: str = None

    semver: str = None
    semver_full: str = None
    pep440: str = None
    nuget: str = None
    timestamp: str = None


def exec(
    cmd: str,
    cwd: str = None,
    capture: bool = False,
    input: str = None,
) -> CompletedProcess[str]:
    args = [arg.strip() for arg in shlex.split(cmd.strip())]
    try:
        return subprocess.run(
            args,
            check=False,
            text=True,
            cwd=cwd,
            capture_output=capture,
            input=input,
        )
    except Exception as ex:
        return CompletedProcess(args=args, returncode=1, stdout="", stderr=str(ex))


def _none_or_empty(s: str) -> bool:
    return not s or len(s.strip()) == 0


def _git_cmd_prefix(ctx: VersionContext) -> str:
    work_tree = f"-C {ctx.work_tree}" if ctx.work_tree else ""
    return f"git {work_tree}"


def get_github_branch(ctx: VersionContext, ver: Version) -> Version:
    """
    If running in github actions use the GITHUB_HEAD_REF env var
    """
    if "GITHUB_HEAD_REF" in os.environ:
        ver.branch = os.environ["GITHUB_HEAD_REF"].strip()
    return ver


def get_branch(ctx: VersionContext, ver: Version) -> Version:
    """
    Get the branch name if not already set
    """
    if _none_or_empty(ver.branch):
        result = exec(
            f"{_git_cmd_prefix(ctx)} rev-parse --abbrev-ref HEAD", capture=True
        )
        if result.returncode != 0:
            raise ValueError("No git branch found.")
        ver.branch = result.stdout.strip()

    return ver


def get_detached_branch(ctx: VersionContext, ver: Version) -> Version:
    """
    Try to determine the branch name if we are detached (branch == HEAD)
    """
    if _none_or_empty(ver.branch):
        raise ValueError("No branch found.")
    if _none_or_empty(ver.hash):
        raise ValueError("No hash found.")

    if ver.branch.strip().lower() == "head":
        git_hash = ver.hash
        raw_branches = exec(
            f"{_git_cmd_prefix(ctx)} branch --contains {git_hash}", capture=True
        ).stdout.strip()
        branches = [l.strip()
                    for l in raw_branches.splitlines() if "HEAD" not in l]
        if len(branches) > 1:
            raise ValueError(
                f"Multiple branches found for {git_hash}. Could not determine branch name"
            )
        ver.branch = branches[0]
    return ver


def sanitize_branch_name(ctx: VersionContext, ver: Version) -> Version:
    """
    Removes special characters from the branch name
    """
    if _none_or_empty(ver.branch):
        raise ValueError("No branch found.")

    ver.branch = re.sub(r"[^a-zA-Z0-9]", "-", ver.branch)
    return ver


def strip_branch_components(ctx: VersionContext, ver: Version) -> Version:
    if ctx.strip_branch_components:
        if ctx.strip_branch_components == 0:
            return ver

        if _none_or_empty(ver.branch):
            raise ValueError("No branch found.")

        parts = ver.branch.split("/")
        remaining = len(parts) - ctx.strip_branch_components
        if remaining < 1:
            raise ValueError(
                f"Cannot strip {ctx.strip_branch_components} components from a branch '{ver.branch}' with only {len(parts)} component(s)"
            )

        ver.branch = "/".join(ver.branch.split("/")
                              [ctx.strip_branch_components:])
    return ver


def get_commit_count(ctx: VersionContext, ver: Version) -> Version:
    #
    # Get the number of commits since the last tag
    #
    if _none_or_empty(ver.last_tag):
        raise ValueError("No last_tag found.")

    result = exec(
        f"{_git_cmd_prefix(ctx)} rev-list --ancestry-path {ver.last_tag}..HEAD --count",
        capture=True,
    )
    if result.returncode == 0:
        ver.commits = int(result.stdout.strip())

    return ver


def get_hash(ctx: VersionContext, ver: Version) -> Version:
    """
    Get the latest commit hash
    """
    result = exec(f"{_git_cmd_prefix(ctx)} rev-parse HEAD", capture=True)
    if result.returncode == 0:
        ver.hash = result.stdout.strip()
    return ver


def build_version_components(ctx: VersionContext, ver: Version) -> Version:
    #
    # Populate the version components from the tag
    #
    if _none_or_empty(ver.last_tag):
        raise ValueError("No last_tag found.")

    last_ver = ver.last_tag
    if ver.tag_prefix and len(ver.tag_prefix) > 0:
        last_ver = ver.last_tag[len(ver.tag_prefix):].strip()

    parts = re.split(semver_rx, last_ver)
    if (
        len(parts) != 3
        or not parts[0].isdigit()
        or not parts[1].isdigit()
        or not parts[2].isdigit()
    ):
        raise ValueError("Invalid tag format. Expected 1.2.3")

    ver.major = int(parts[0])
    ver.minor = int(parts[1])
    ver.patch = int(parts[2])

    if ctx.increment == VersionIncrement.MAJOR:
        ver.major += 1
        ver.minor = 0
        ver.patch = 0
    elif ctx.increment == VersionIncrement.MINOR:
        ver.minor += 1
        ver.patch = 0
    elif ctx.increment == VersionIncrement.PATCH:
        ver.patch += 1

    return ver


def is_int(v) -> bool:
    return isinstance(v, int)


def validate_version_components(ver: Version) -> Version:
    if is_int(ver.major) and is_int(ver.minor) and is_int(ver.patch):
        return ver

    raise ValueError(
        f"major ({ver.major}), minor ({ver.minor}) or patch ({ver.patch}) values not set correctly."
    )


def validate_semver(ver: Version) -> Version:
    validate_version_components(ver)

    if _none_or_empty(ver.branch):
        raise ValueError("No branch found.")
    if ver.commits is None:
        raise ValueError("No commits found.")

    return ver


def build_tag(ctx: VersionContext, ver: Version) -> Version:
    validate_version_components(ver)

    tag_prefix = f"{ver.tag_prefix}" if ver.tag_prefix else ""
    ver.tag = f"{tag_prefix}{ver.major}.{ver.minor}.{ver.patch}"

    return ver


def _get_branch_full(ver: Version, separator: str = "-") -> str:
    branch_value = (
        f"{separator}{ver.branch}" if ver.branch not in (
            "main", "master") else ""
    )
    commits_value = f".{ver.commits}" if ver.branch not in (
        "main", "master") else ""
    return f"{branch_value}{commits_value}"


def build_semver(ctx: VersionContext, ver: Version) -> Version:
    validate_semver(ver)

    ver.semver = f"{ver.major}.{ver.minor}.{ver.patch}"
    ver.semver_full = f"{ver.semver}{_get_branch_full(ver)}"

    return ver


def build_pep440(ctx: VersionContext, ver: Version) -> Version:
    validate_semver(ver)

    ver.pep440 = f"{ver.semver}{_get_branch_full(ver, separator='+')}"

    return ver


def build_nuget(ctx: VersionContext, ver: Version) -> Version:
    validate_semver(ver)

    ver.nuget = f"{ver.semver}{_get_branch_full(ver)}"
    # nuget has a max length of 20 chars for prerelease versions
    # https://github.com/NuGet/Home/issues/1459
    if len(ver.nuget) > 20:
        ver.nuget = ver.nuget[:10] + ver.nuget[-10:]

    return ver


def apply_tag_prefix(ctx: VersionContext, ver: Version) -> Version:
    #
    # Adds prefix to version output (if it exists)
    #
    if _none_or_empty(ver.last_tag):
        raise ValueError("No last_tag found.")

    if ctx.tag_prefix and ver.last_tag.startswith(ctx.tag_prefix):
        ver.tag_prefix = ctx.tag_prefix

    return ver


def get_last_tag(ctx: VersionContext, ver: Version) -> Version:
    #
    # Get the last tag version (1.2.3) prior to this commit
    #
    if _none_or_empty(ver.hash):
        raise ValueError("No hash found.")

    # get last tag
    tag_prefix_option = f"--match={ctx.tag_prefix}*" if ctx.tag_prefix else ""
    result = exec(
        f"{_git_cmd_prefix(ctx)} describe --tags --abbrev=0 {tag_prefix_option} {ver.hash}^",
        capture=True,
    )
    if result.returncode == 0:
        ver.last_tag = result.stdout.strip()

    # get last tag hash
    result = exec(
        f"{_git_cmd_prefix(ctx)} rev-list -n 1 {ver.last_tag}",
        capture=True,
    )
    if result.returncode == 0:
        ver.last_hash = result.stdout.strip()

    return ver


def get_timestamp(ctx: VersionContext, ver: Version) -> Version:
    now = datetime.utcnow()
    ver.timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    return ver


def validate_context(ctx: VersionContext, ver: Version) -> Version:
    #
    # Validate the increment type
    #
    if ctx.increment not in [
        VersionIncrement.MAJOR,
        VersionIncrement.MINOR,
        VersionIncrement.PATCH,
    ]:
        raise ValueError(
            "Invalid increment value. Must be major, minor, or patch")

    return ver


def get_version(
    ctx: VersionContext,
    funcs=[
        validate_context,
        get_timestamp,
        get_hash,
        get_last_tag,
        get_commit_count,
        apply_tag_prefix,
        get_github_branch,
        get_branch,
        get_detached_branch,
        strip_branch_components,
        sanitize_branch_name,
        build_version_components,
        build_tag,
        build_semver,
        build_pep440,
        build_nuget,
    ],
) -> Version:
    i = 1
    v = Version()
    for f in funcs:
        # print(i, f.__name__, v)
        v = f(ctx, v)
        i += 1
    return v


if __name__ == "__main__":
    doc_keys = ",".join(
        [k for k in vars(Version()).keys() if k !=
         "last_tag" and k != "last_hash"]
    )
    parser = argparse.ArgumentParser(
        description="Increment a semantic version component of a git tag."
    )
    parser.add_argument(
        "component",
        choices=["major", "minor", "patch"],
        help="The version component to increment",
    )
    parser.add_argument(
        "--tag-prefix", help="Optional prefix for git tags", default="")
    parser.add_argument(
        "--show",
        default="all",
        help=f"Comma separated fields to show. Default is all. Valid fields are: {doc_keys}",
    )
    parser.add_argument(
        "--format",
        default="csv",
        help=f"Format to display in. Default is comma separated. Values: csv, json, env",
    )
    parser.add_argument(
        "--json-pretty",
        help="Optional pretty formatting for json output",
        action="store_true",
    )
    parser.add_argument(
        "--csv-header",
        help="Optional header for csv output",
        action="store_true",
    )
    parser.add_argument(
        "--env-prefix", help="Optional prefix for output keys", default="VERSION_"
    )
    parser.add_argument(
        "--strip-branch-components",
        help="Optional number of branch components (paths) to strip from the start of the branch name",
    )
    args = parser.parse_args()

    ctx = VersionContext(increment=VersionIncrement(args.component.upper()))
    if args.tag_prefix:
        ctx.tag_prefix = args.tag_prefix
    if args.strip_branch_components:
        ctx.strip_branch_components = int(args.strip_branch_components)
    ver = get_version(ctx)
    ver_dict = vars(ver)

    # get/validate list of keys to print
    print_keys = []
    if args.show:
        if args.show == "all":
            print_keys = list(ver_dict.keys())
        else:
            for key in args.show.split(","):
                if key not in ver_dict:
                    raise ValueError(f"Field '{key}' not found.")
            print_keys = args.show.split(",")
    else:
        print_keys.append(ver.semver_full)

    # print output in json
    if args.format == "json":
        values = {key: ver_dict[key] for key in print_keys}
        print(json.dumps(values, indent=4 if args.json_pretty else None))

    # print output in env format
    elif args.format == "env":
        for key in print_keys:
            value = ver_dict[key]
            print_value = ""
            if value is not None:
                if isinstance(value, str):
                    print_value = f'"{value}"'
                else:
                    print_value = str(value)
            print(f"{args.env_prefix.upper()}{key.upper()}={print_value}")

    # print output in csv separated format
    else:
        if args.csv_header:
            print(",".join(print_keys))

        values = [
            "" if ver_dict[key] is None else str(ver_dict[key]) for key in print_keys
        ]
        print(",".join(values))
