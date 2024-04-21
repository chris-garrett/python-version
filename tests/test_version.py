import os
import re
import shutil
import sys

import pytest

from tests.configure import git, git_repo, init_git
from version import (Version, VersionContext, VersionIncrement,
                     apply_tag_prefix, build_version_components, exec,
                     get_branch, get_commit_count, get_detached_branch,
                     get_github_branch, get_hash, get_last_tag, get_version,
                     sanitize_branch_name, strip_branch_components,
                     validate_context)

# Setup main and a single branch
# (main) 0.1.0 -> 0.2.0 -> 0.3.0
#                    \
#               (chore/branch1) -> branch-change-one -> branch-change-two
#
# returns a dict with the commit hashes
# {
#   main_1 : baf0ecc29174091053b64209d55d702dd70f1287   note: main, 0.1.0 | mysevice-v0.1.0
#   main_2 : 705fa6edc2e529a0794a9f473e65502c4cd08c15   note: main, 0.2.0 | mysevice-v0.2.0
#   main_3 : 5f3a33aa9c68bbf7d1da6cca4c3b97c9d9f867a2   note: main, 0.3.0 | mysevice-v0.3.0
#   branch_1 : 32ad125ad05fdcc12d3e2b2c8ca2134e408a3c5f note: chore/branch1, no tag, branched off 0.2.0
#   branch_2 : 63e520ae66faaa16fc3d72ece793f59fc5b9a871 note: chore/branch1, no tag, branched off 0.2.0
# }
hashes = init_git()
# print(hashes)
semver_rx = re.compile(r"\.")
tag_prefix_data = [None, "myservice-v"]


def default_context() -> VersionContext:
    return VersionContext(increment=VersionIncrement.MINOR, work_tree=git_repo)


def test_hash():
    """
    Test getting the hash of the current commit (main_3)
    """
    git("switch main")
    c = default_context()
    v = Version()
    v = get_hash(c, v)
    assert v.hash == hashes["main_3"]


@pytest.mark.parametrize("tag_prefix", tag_prefix_data)
def test_get_last_tag(tag_prefix):
    """
    Test getting the last tag of the current commit (main_3)
    Tag should be from main_2
    """
    git("switch main")
    c = default_context()
    c.tag_prefix = tag_prefix
    v = Version(hash=hashes["main_3"])
    v = get_last_tag(c, v)
    assert v.last_tag in ("0.2.0", "myservice-v0.2.0")


@pytest.mark.parametrize("tag", ["0.2.0", "myservice-v0.2.0"])
def test_get_commit_count(tag):
    """
    Test getting the commit count of the current commit (main_3)
    """
    git("switch chore/branch1")
    c = default_context()
    v = Version(last_tag=tag)
    v = get_commit_count(c, v)
    assert v.commits == 2


@pytest.mark.parametrize("tag_prefix", tag_prefix_data)
def test_apply_tag_prefix(tag_prefix):
    """
    Tests stripping the tag prefix from the last_tag if there is one
    """
    last_tag = "0.2.0" if tag_prefix is None else "myservice-v0.2.0"

    git("switch chore/branch1")
    c = default_context()
    c.tag_prefix = tag_prefix
    v = Version(last_tag=last_tag)
    v = apply_tag_prefix(c, v)
    assert v.last_tag == "0.2.0"
    assert v.tag_prefix == tag_prefix


def test_build_version_major():
    """
    Tests populating the version components from the last tag and increment value
    """
    c = VersionContext(increment=VersionIncrement.MAJOR)
    v = Version(last_tag="1.2.3")
    v = build_version_components(c, v)
    assert v.major == 2
    assert v.minor == 0
    assert v.patch == 0


def test_build_version_minor():
    """
    Tests populating the version components from the last tag and increment value
    """
    c = VersionContext(increment=VersionIncrement.MINOR)
    v = Version(last_tag="1.2.3")
    v = build_version_components(c, v)
    assert v.major == 1
    assert v.minor == 3
    assert v.patch == 0


def test_build_version_patch():
    """
    Tests populating the version components from the last tag and increment value
    """
    c = VersionContext(increment=VersionIncrement.PATCH)
    v = Version(last_tag="1.2.3")
    v = build_version_components(c, v)
    assert v.major == 1
    assert v.minor == 2
    assert v.patch == 4


def test_get_github_branch():
    """
    Tests getting the branch from the GITHUB_HEAD_REF environment variable
    """
    c = default_context()
    v = Version()

    github_head_ref = None

    # test without GITHUB_HEAD_REF
    # if we are running this test in github actions, GITHUB_HEAD_REF will be set
    if "GITHUB_HEAD_REF" in os.environ:
        github_head_ref = os.environ["GITHUB_HEAD_REF"]
        del os.environ["GITHUB_HEAD_REF"]
    branch = get_github_branch(c, v).branch
    assert branch is None

    # test with GITHUB_HEAD_REF
    os.environ["GITHUB_HEAD_REF"] = "foo/bar/baz"
    branch = get_github_branch(c, v).branch
    assert branch == "foo/bar/baz"
    del os.environ["GITHUB_HEAD_REF"]

    # set it back if it was set
    if github_head_ref is not None:
        os.environ["GITHUB_HEAD_REF"] = github_head_ref


def test_get_branch():
    """
    Tests getting the branch from the git repository if it was not already set
    """
    c = default_context()
    v = Version()

    # test with branch set
    v.branch = "foo/bar/baz"
    branch = get_branch(c, v).branch

    # test with branch unset (not set by previous middleware)
    git("switch chore/branch1")
    v.branch = None
    branch = get_branch(c, v).branch
    assert len(branch) > 3

    assert branch == "chore/branch1"


def test_get_detached_branch():
    c = default_context()
    v = Version()
    v.hash = hashes["branch_2"]

    git("switch main")
    git(f"checkout {hashes['branch_2']}")

    # test with branch set that is not detached (HEAD)
    v.branch = "foo/bar/baz"
    v = get_detached_branch(c, v)
    assert v.branch == "foo/bar/baz"

    # test with detached HEAD
    v.branch = "HEAD"
    v = get_detached_branch(c, v)
    assert v.branch == "chore/branch1"


def test_sanitize_branch_name():
    c = default_context()
    v = Version()

    # test with a branch name that is already sanitized
    v.branch = "main-one-two-three"
    v = sanitize_branch_name(c, v)
    assert v.branch == "main-one-two-three"

    # test with a branch name that offensive
    v.branch = "main/one/two-three"
    v = sanitize_branch_name(c, v)


def test_strip_branch_components():
    c = default_context()
    v = Version()

    # test with a branch name that offensive
    v.branch = "main/one/two-three"
    v = strip_branch_components(c, v)
    assert v.branch == "main/one/two-three"

    # remove first 2 components
    c.strip_branch_components = 2
    v.branch = "dev/name/jira-1234-do-something"
    v = strip_branch_components(c, v)
    assert v.branch == "jira-1234-do-something"


def test_build_tag():
    pass


def test_build_semver():
    pass


def test_build_pep440():
    pass


def test_build_nuget():
    pass


def test_build_apple():
    pass


def test_happy_path_integration_main():
    c = default_context()
    c.tag_prefix = "myservice-v"
    git("switch main")
    v = get_version(c)
    assert v.major == 0
    assert v.minor == 3
    assert v.patch == 0
    assert v.commits == 1
    assert v.branch == "main"
    assert v.hash == hashes["main_3"]
    assert v.last_tag == "0.2.0"
    assert v.last_hash is None
    assert v.tag_prefix == "myservice-v"
    assert v.tag == "0.3.0"
    assert v.semver == "0.3.0"
    assert v.semver_full == "0.3.0"
    assert v.pep440 == "0.3.0"
    assert v.nuget == "0.3.0"


def test_happy_path_integration_long_branch():
    c = default_context()
    c.tag_prefix = "myservice-v"
    c.strip_branch_components = 2
    git("switch dev/some-name/jira-1234-this-is-a-really-cool-feature-i-think")

    v = get_version(c)
    assert v.major == 0
    assert v.minor == 3
    assert v.patch == 0
    assert v.commits == 1
    assert v.branch == "jira-1234-this-is-a-really-cool-feature-i-think"
    assert v.hash == hashes["main_3"]
    assert v.last_tag == "0.2.0"
    assert v.last_hash is None
    assert v.tag_prefix == "myservice-v"
    assert v.tag == "0.3.0"
    assert v.semver == "0.3.0"
    assert v.semver_full == "0.3.0-jira-1234-this-is-a-really-cool-feature-i-think.1"
    assert v.pep440 == "0.3.0+jira-1234-this-is-a-really-cool-feature-i-think.1"
    assert v.nuget == "0.3.0-jira-i-think.1"