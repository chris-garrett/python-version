import os
from glob import glob

from __tasklib__ import TaskBuilder, TaskContext


def _get_pytest_cmd():
    files = " ".join(glob("./tests/test_*.py"))
    return f"pytest --lf -v --capture=tee-sys {files}"


def _hello(ctx: TaskContext):
    ctx.log.info("Hello")


def _test(ctx: TaskContext):
    ctx.exec(_get_pytest_cmd())


def _test_watch(ctx: TaskContext):
    ctx.exec(
        f"""
        watchexec
            -r --project-origin .
            -w .
            -e py
             {_get_pytest_cmd()}
        """
    )


def _version_watch(ctx: TaskContext):
    ctx.exec(
        f"""
        watchexec
            -r --project-origin .
            -w .
            -e py
            python version.py minor --show all --format env
        """
    )


def _ci_version(ctx: TaskContext, increment):
    if not os.path.exists(".local"):
        os.makedirs(".local")

    ret = ctx.exec(f"python version.py {increment} --format env", capture=True)
    out = ret.stdout.strip()
    ctx.log.info(out)

    build_env = os.path.abspath(
        os.path.join(os.path.dirname(__file__), ".local", "build-env")
    )
    with open(build_env, "w") as f:
        f.write(out)


def configure(builder: TaskBuilder):
    module_name = "root"
    builder.add_task(module_name, "test", _test)
    builder.add_task(module_name, "test:watch", _test_watch)
    builder.add_task(module_name, "version:watch", _version_watch)
    builder.add_task(
        module_name, "ci:version:major", lambda ctx: _ci_version(ctx, "major")
    )
    builder.add_task(
        module_name, "ci:version:minor", lambda ctx: _ci_version(ctx, "minor")
    )
    builder.add_task(
        module_name, "ci:version:patch", lambda ctx: _ci_version(ctx, "patch")
    )
