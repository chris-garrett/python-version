import os
import re
import shutil
import sys

import pytest

root_dir = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, root_dir)

from version import exec  # noqa: E402

git_repo = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.local/testgit"))


def git(cmd):
    return exec(f'git -C "{git_repo}" {cmd}', capture=True)


def init_git():
    # Setup main and a single branch
    # (main) 0.1.0 -> 0.2.0 -> 0.3.0
    #                    \
    #               (chore/branch1) -> branch-change-one -> branch-change-two
    if os.path.exists(git_repo):
        shutil.rmtree(git_repo)
    exec(f'git init -b main "{git_repo}"', capture=True)
    exec(f"git -C {git_repo} config user.name 'test'", capture=True)
    exec(f"git -C {git_repo} config user.email 'test@home.com'", capture=True)
    # add readme, commit and tag
    exec(f"touch {git_repo}/README.md", capture=True)
    exec(f"git -C {git_repo} add -A", capture=True)
    exec(f"git -C {git_repo} commit -m 'add readme'", capture=True)
    exec(f"git -C {git_repo} tag 0.1.0", capture=True)
    exec(f"git -C {git_repo} tag myservice-v0.1.0", capture=True)
    main_1 = git("rev-parse HEAD").stdout.strip()
    main_1_tags = ",".join(git(f"tag --points-at {main_1}").stdout.strip().splitlines())
    # add change1, commit and tag
    exec(f"touch {git_repo}/change-one.md", capture=True)
    exec(f"git -C {git_repo} add -A", capture=True)
    exec(f"git -C {git_repo} commit -m 'add change-one'", capture=True)
    exec(f"git -C {git_repo} tag 0.2.0", capture=True)
    exec(f"git -C {git_repo} tag myservice-v0.2.0", capture=True)
    main_2 = git("rev-parse HEAD").stdout.strip()
    main_2_tags = ",".join(git(f"tag --points-at {main_2}").stdout.strip().splitlines())
    # add branch and add a few commits
    exec(f"git -C {git_repo} checkout -b chore/branch1", capture=True)
    exec(f"touch {git_repo}/branch-change-one.md", capture=True)
    exec(f"git -C {git_repo} add -A", capture=True)
    exec(f"git -C {git_repo} commit -m 'add branch-change-one'", capture=True)
    branch_1 = git("rev-parse HEAD").stdout.strip()
    branch_1_tags = ",".join(git(f"tag --points-at {branch_1}").stdout.strip().splitlines())
    exec(f"touch {git_repo}/branch-change-two.md", capture=True)
    exec(f"git -C {git_repo} add -A", capture=True)
    exec(f"git -C {git_repo} commit -m 'add branch-change-two'", capture=True)
    branch_2 = git("rev-parse HEAD").stdout.strip()
    branch_2_tags = ",".join(git(f"tag --points-at {branch_1}").stdout.strip().splitlines())
    # switch back to main add change2, commit and tag
    exec(f"git -C {git_repo} switch main", capture=True)
    exec(f"touch {git_repo}/change-two.md", capture=True)
    exec(f"git -C {git_repo} add -A", capture=True)
    exec(f"git -C {git_repo} commit -m 'add change-two'", capture=True)
    exec(f"git -C {git_repo} tag 0.3.0", capture=True)
    exec(f"git -C {git_repo} tag myservice-v0.3.0", capture=True)
    main_3 = git("rev-parse HEAD").stdout.strip()
    main_3_tags = ",".join(git(f"tag --points-at {main_3}").stdout.strip().splitlines())
    git("checkout -b dev/some-name/jira-1234-this-is-a-really-cool-feature-i-think")
    #git("switch main")

    return {
        "main_1": main_1,
        "main_1_tags": main_1_tags,
        "main_2": main_2,
        "main_2_tags": main_2_tags,
        "main_3": main_3,
        "main_3_tags": main_3_tags,
        "branch_1": branch_1,
        "branch_1_tags": branch_1_tags,
        "branch_2": branch_2,
        "branch_2_tags": branch_2_tags,
    }
