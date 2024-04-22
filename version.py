#!/usr/bin/env python3

import argparse
import json
import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from enum import Enum
from subprocess import CompletedProcess
from typing import Optional

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
        return ValueError("No branch found.")
    if _none_or_empty(ver.hash):
        return ValueError("No hash found.")

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
    if not ver.branch or len(ver.branch.strip()) == 0:
        return ValueError("No branch found.")

    ver.branch = re.sub(r"[^a-zA-Z0-9]", "-", ver.branch)
    return ver


def strip_branch_components(ctx: VersionContext, ver: Version) -> Version:
    if ctx.strip_branch_components:
        if not ver.branch or len(ver.branch.strip()) == 0:
            return ValueError("No branch found.")
        ver.branch = "/".join(ver.branch.split("/")[2:])
    return ver


def get_commit_count(ctx: VersionContext, ver: Version) -> Version:
    #
    # Get the number of commits since the last tag
    #
    if not ver.last_tag or len(ver.last_tag.strip()) == 0:
        return ValueError("No last_tag found.")

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
    if not ver.last_tag or len(ver.last_tag.strip()) == 0:
        return ValueError("No last_tag found.")

    parts = re.split(semver_rx, ver.last_tag.strip())
    if len(parts) != 3:
        return ValueError("Invalid tag format. Expected 1.2.3")

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


def build_tag(ctx: VersionContext, ver: Version) -> Version:
    if ver.major is None or ver.minor is None or ver.patch is None:
        return ValueError(
            f"major ({ver.major}), minor ({ver.minor}) or patch ({ver.patch}) values not set correctly."
        )

    ver.tag = f"{ver.major}.{ver.minor}.{ver.patch}"

    return ver


def _validate_semver(ctx: VersionContext, ver: Version) -> Version:
    if ver.major is None or ver.minor is None or ver.patch is None:
        return ValueError(
            f"major ({ver.major}), minor ({ver.minor}) or patch ({ver.patch}) values not set correctly."
        )
    if not ver.branch or len(ver.branch.strip()) == 0:
        return ValueError("No branch found.")
    if ver.commits is None:
        return ValueError("No commits found.")

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
    _validate_semver(ctx, ver)

    ver.semver = f"{ver.major}.{ver.minor}.{ver.patch}"
    ver.semver_full = f"{ver.semver}{_get_branch_full(ver)}"

    return ver


def build_pep440(ctx: VersionContext, ver: Version) -> Version:
    _validate_semver(ctx, ver)

    ver.pep440 = f"{ver.semver}{_get_branch_full(ver, separator='+')}"

    return ver


def build_nuget(ctx: VersionContext, ver: Version) -> Version:
    _validate_semver(ctx, ver)

    ver.nuget = f"{ver.semver}{_get_branch_full(ver)}"
    # nuget has a max length of 20 chars for prerelease versions
    # https://github.com/NuGet/Home/issues/1459
    if len(ver.nuget) > 20:
        ver.nuget = ver.nuget[:10] + ver.nuget[-10:]

    return ver


def apply_tag_prefix(ctx: VersionContext, ver: Version) -> Version:
    #
    # Stripts prefix off tag and adds prefix to version output (if it exists)
    #
    if not ver.last_tag or len(ver.last_tag.strip()) == 0:
        return ValueError("No last_tag found.")

    if ctx.tag_prefix and ver.last_tag.startswith(ctx.tag_prefix):
        ver.last_tag = ver.last_tag[len(ctx.tag_prefix):].strip()
        ver.tag_prefix = ctx.tag_prefix

    return ver


def get_last_tag(ctx: VersionContext, ver: Version) -> Version:
    #
    # Get the last tag version (1.2.3) prior to this commit
    # and strip the tag prefix if it exists
    #
    if not ver.hash or len(ver.hash.strip()) == 0:
        return ValueError("No hash found.")

    tag_prefix_option = f"--match={ctx.tag_prefix}*" if ctx.tag_prefix else ""
    result = exec(
        f"{_git_cmd_prefix(ctx)} describe --tags --abbrev=0 {tag_prefix_option} {ver.hash}^",
        capture=True,
    )
    if result.returncode == 0:
        ver.last_tag = result.stdout.strip()
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
        return ValueError("Invalid increment value. Must be major, minor, or patch")

    return ver


def get_version(
    ctx: VersionContext,
    funcs=[
        validate_context,
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
        [
            k
            for k in vars(Version()).keys()
            if k != "last_tag" and k != "last_hash" and k != "tag_prefix"
        ]
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
        default="comma",
        help=f"Format to display in. Default is comma separated. Values: comma, json, env",
    )
    parser.add_argument(
        "--pretty-json",
        help="Optional pretty formatting for json output",
        action="store_true",
    )
    parser.add_argument(
        "--comma-header",
        help="Optional header for comma output",
        action="store_true",
    )
    parser.add_argument(
        "--env-prefix", help="Optional prefix for output keys", default="VERSION_"
    )
    args = parser.parse_args()

    ctx = VersionContext(increment=VersionIncrement(args.component.upper()))
    if args.tag_prefix:
        ctx.tag_prefix = args.tag_prefix
    ver = get_version(ctx)
    ver_dict = vars(ver)
    del ver_dict["last_tag"]
    del ver_dict["last_hash"]
    del ver_dict["tag_prefix"]

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
        print(json.dumps(values, indent=4 if args.pretty_json else None))

    # print output in env format
    elif args.format == "env":
        for key in print_keys:
            print(f"{args.env_prefix.upper()}{key.upper()}={ver_dict[key]}")

    # print output in comma separated format
    else:
        if args.comma_header:
            print(",".join(print_keys))
        values = [str(ver_dict[key]) for key in print_keys]
        print(",".join(values))
