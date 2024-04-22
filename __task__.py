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
            python version.py minor --show major,minor,patch
        """
    )


def configure(builder: TaskBuilder):
    module_name = "root"
    builder.add_task(module_name, "test", _test)
    builder.add_task(module_name, "test:watch", _test_watch)
    builder.add_task(module_name, "version:watch", _version_watch)
