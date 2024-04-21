################################################
# https://github.com/chris-garrett/python-task #
################################################
#
# Apr 20 2024
# * chore: support single file task projects
#   * moved __task__.py to __tasklib__.py
#   * no longer filter __task__.py at root
#
# Mar 04 2024
# * chore: update to Python 3.9
# * chore: add tests for load_dotenv
# * feat: add environment variable expansion to load_dotenv
#
# Dec 16 2023
# * fix/feat: fix bug in load_dotenv where keys were not trimmed and white space not leading to a match, add
#             override to match python-dotenv behavior.
#
# Dec 05 2023
# * fix: add exception handling to exec() calls. normalize returned object.
#
# Dec 03 2023
# * added quiet option to exec(). This will capture stdout and stderr and will be available
#   in the CompletedProcess object.
#   example:
#    (args=['pwd'], returncode=0, stdout='/home/chris\n', stderr='') = ctx.exec("pwd", quiet=True)
# * log level can be specified via LOG_LEVEL env var. see ./task. Valid values are: TRACE, DEBUG, INFO, WARNING, ERROR, CRITICAL. # noqa
#
# Dec 02 2023
# * add support for task dependencies
#
# Nov 13 2023
# * initial cut of a task runner
#
# TODO
# * add the abililty to call depenencies with arguments.
# * add support for file depenencies. see go-task for inspiration: https://taskfile.dev/usage/#prevent-unnecessary-work

import os
import sys
import glob
import shlex
import typing
import logging
import platform
from logging import Logger
import argparse
import subprocess
from subprocess import CompletedProcess
from dataclasses import dataclass
from typing import NamedTuple, Callable, List, Protocol, runtime_checkable
import importlib.machinery
import inspect


def load_dotenv(filename=".env", override=False, expand_vars=True):
    """
    Load environment variables from a .env file into the os.environ dictionary.

    Args:
    - filename (str, optional): The name of the .env file to load. Defaults to ".env".
    - override (bool, optional): If True, existing environment variables will be overwritten
      by those in the .env file. Defaults to False.

    Returns:
    None
    """
    if not os.path.exists(filename):
        return
    with open(filename) as f:
        for line in f:
            line = line.strip()

            # skip comments and empty lines
            if line.startswith("#") or "=" not in line:
                continue

            k, v = line.split("=", 1)
            k = k.strip()

            # dont override existing env vars unless explicitly told to
            if k in os.environ and not override:
                continue

            # dont set null values
            if v is not None:
                os.environ[k] = v.strip()

    if expand_vars:
        # expand any env vars
        for k, v in os.environ.items():
            if v.startswith("$"):
                os.environ[k] = os.path.expandvars(v)


def trace(self, message, *args, **kws):
    if self.isEnabledFor(TRACE_LEVEL):
        self._log(TRACE_LEVEL, message, args, **kws)


TRACE_LEVEL = 5
logging.addLevelName(TRACE_LEVEL, "TRACE")
logging.Logger.trace = trace

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("task")


@runtime_checkable
class ExecProtocol(Protocol):
    def exec(self, cmd: str, quiet: bool = False) -> int:
        raise NotImplementedError


class SystemContext(NamedTuple):
    platform: str  # Linux, Darwin, Windows
    arch: str  # x86_64, arm64
    distro: str  # Debian, Arch, RHEL


def exec(
    cmd: str, cwd: str = None, logger: Logger = None, venv_dir: str = None, capture: bool = False, input: str = None
) -> CompletedProcess[str]:
    args = [arg.strip() for arg in shlex.split(cmd.strip())]
    if isinstance(logger, Logger) and not capture:
        if cwd:
            logger.debug("Executing: [%s] Cwd: [%s]", " ".join(args), cwd)
        else:
            logger.debug("Executing: [%s]", " ".join(args))

    try:
        return subprocess.run(
            args,
            check=False,
            text=True,
            cwd=cwd,
            env=_build_env(os.environ, venv_dir) if venv_dir else os.environ,
            capture_output=capture,
            input=input,
        )
    except Exception as ex:
        logger.error(f"{str(ex)}")
        return CompletedProcess(args=args, returncode=1, stdout="", stderr=str(ex))


@dataclass
class TaskContext(ExecProtocol):
    root_dir: str
    project_dir: str
    log: Logger
    system: SystemContext

    def exec(
        self, cmd: str, cwd: str = None, venv_dir: str = None, capture: bool = False, input: str = None
    ) -> CompletedProcess[str]:
        return exec(cmd, cwd, self.log, venv_dir, capture, input)


class TaskFileDefinition(NamedTuple):
    func: Callable[[TaskContext], None]  # configure func
    filename: str
    dir: str


class TaskDefinition(NamedTuple):
    func: Callable[[TaskContext], None]  # task func
    module: str
    name: str
    filename: str
    dir: str
    deps: List[str] = []


class TaskBuilder(object):
    def __init__(self):
        self.parsers = []
        self.python_exe = "python"

    def use_python(self, python_exe):
        self.python_exe = python_exe

    def add_task(self, module: str, name: str, func: callable, deps: List[str] = []) -> None:
        """
        Add a task to the list of parsers.

        Args:
        - module (str): The name of the module containing the task.
        - name (str): The name of the task.
        - func (callable): The function that implements the task.
        - deps (list[str]): A list of task names that this task depends on.
        """
        if not isinstance(deps, list):
            raise TypeError(f"deps must be a list, got {type(deps)}")
        self.parsers.append((module, name, func, deps))


def _build_env(env, venv_dir):
    """
    Replaces an old virtual env dir from path with a project
    level virtual env dir
    """
    old_env = env.copy()

    if "VIRTUAL_ENV" in old_env:
        old_venv = f"{old_env['VIRTUAL_ENV']}/bin:"
        # remove the old virtualenv path
        old_path = old_env["PATH"][len(old_venv) :]  # noqa
    else:
        old_path = old_env["PATH"]

    # remove pythopath if it exists
    if "PYTHONHOME" in old_env:
        del old_env["PYTHONHOME"]

    new_venv = f"{venv_dir}/bin"

    # replace it with project virt env dir
    old_env["PATH"] = f"{new_venv}:{old_path}"

    # replace virt env
    old_env["VIRTUAL_ENV"] = new_venv

    return old_env


def _ensure_venv(ctx: TaskContext):
    if not os.path.exists(ctx.venv_dir):
        ctx.log.info(f"Creating venv {ctx.venv_dir}")
        ctx.exec([ctx.python_exe, "-m", "venv", ctx.venv_dir])


def _load_tasks(task: TaskFileDefinition) -> typing.Dict[str, TaskDefinition]:
    """
    Builds a list of N tasks based on what was specified in configure().
    """
    tasks: typing.Dict[str, TaskDefinition] = {}
    builder = TaskBuilder()
    task.func(builder)
    for module, name, func, deps in builder.parsers:
        tasks[name] = TaskDefinition(
            module=module, name=name, func=func, dir=task.dir, filename=task.filename, deps=deps
        )
    return tasks


def _load_task_definitions(task_files) -> List[TaskFileDefinition]:
    """
    Loads tasks files if they match the required signature.
    """
    tasks: List[TaskFileDefinition] = []

    for idx, task_file in enumerate(task_files):
        loader = importlib.machinery.SourceFileLoader(f"task{idx}", task_file)
        module = loader.load_module()
        if not hasattr(module, "configure"):
            logger.trace(f"load task definition: {task_file}: no configure() found, skipping {task_file}")
            continue

        func = getattr(module, "configure")
        parameters = inspect.signature(func).parameters
        if "builder" not in parameters:
            logger.trace(f"load task definition: {task_file}: no configure(builder) found, skipping {task_file}")
            continue

        logger.trace(f"load task definition: {task_file}: loaded successfully")
        tasks.append(
            TaskFileDefinition(
                func=func,
                filename=task_file,
                dir=os.path.abspath(os.path.dirname(task_file)),
            )
        )

    return tasks


def _find_task_files() -> List[str]:
    """
    Finds files that match naming convention
    """
    return [f for f in glob.glob("**/__task__.py", recursive=True) if os.path.isfile(f)]


def _build_system_distro(content: str) -> str:
    """
    Returns distro for os-release contents
    """

    id = ""
    id_like = None
    for line in content.split():
        if line.startswith("ID_LIKE="):
            id_like = line.split("=")[1].strip()
        if line.startswith("ID="):
            id = line.split("=")[1].strip()
    return id_like if id_like else id


def _build_system_context() -> SystemContext:
    """
    Builds a context object for the system.
    """

    distro = ""
    if platform.system() == "Linux" and os.path.exists("/etc/os-release"):
        with open("/etc/os-release") as f:
            distro = _build_system_distro(f.read())

    return SystemContext(
        platform=platform.system().lower(),
        arch=platform.machine().lower(),
        distro=distro.lower(),
    )


def _build_task_context(task: TaskDefinition) -> TaskContext:
    """
    Builds a context object for a task.
    """
    return TaskContext(
        root_dir=os.path.abspath(os.path.dirname(__file__)),
        project_dir=task.dir,
        log=logging.getLogger(task.module),
        system=_build_system_context(),
    )


def _print_help(available_tasks: List[str]):
    # do a lazy sort to put tasks with no colons first
    formatted_tasks = "".join(
        [f"  {t}\n" for t in sorted(available_tasks, key=lambda x: (0 if x.count(":") == 0 else 1, x))]
    )
    print(
        f"""usage: task [-h] [task ...]

arguments:
{formatted_tasks}

options:
  -h, --help  show this help message and exit
  -v, --verbose  enabled debug logging
"""
    )


def _resolve_deps(tasks_to_resolve, tasks):
    # Convert list of tasks to a dictionary for easy access
    task_dict = {list(task.keys())[0]: list(task.values())[0] for task in tasks}

    resolved = []  # List to store the resolved order of tasks
    visited = set()  # Set to keep track of visited tasks to detect circular dependencies

    def dfs(task):
        if task in resolved:  # If already resolved, no need to proceed
            return
        if task in visited:  # Circular dependency detected
            raise ValueError("Circular dependency detected")
        visited.add(task)

        # Resolve dependencies first
        for dep in task_dict.get(task, {}).get("deps", []):
            if dep not in resolved:
                dfs(dep)

        visited.remove(task)  # Remove from visited as we are done with this task
        resolved.append(task)  # Add to resolved list

    for task in tasks_to_resolve:
        if task not in resolved:
            dfs(task)

    return resolved


def _process_tasks():
    logger.info("Processing tasks")

    # need to boostrap this arg so that we can enable debug logging at
    # configure time
    raw_args = sys.argv[1:]
    if "-v" in raw_args or "--verbose" in raw_args:
        logger.setLevel(logging.DEBUG)

    task_files = _find_task_files()
    task_defs = _load_task_definitions(task_files)
    tasks: typing.Dict[str, TaskDefinition] = {}  # { 'task_name': TaskDefinition }

    parser = argparse.ArgumentParser(description="task", add_help=False)
    parser.add_argument("tasks", nargs="*")
    parser.add_argument("-h", "--help", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")

    # configure tasks
    for task_def in task_defs:
        tasks.update(_load_tasks(task_def))

    args = parser.parse_args()

    if len(args.tasks) == 0 or args.help:
        _print_help(tasks.keys())
        return

    # validate tasks
    for task_name in args.tasks:
        if task_name not in tasks:
            logger.error("Unknown task: %s", task_name)
            _print_help(tasks.keys())
            return

    # build a list of tasks and dependencies to pass to the resolver
    # result should be:
    # [
    #   {
    #       "task_name": {
    #           "deps": ["dep1", "dep2"]
    #       }
    #   },
    # ]
    tasks_with_deps = [{k: {"deps": v.deps}} for k, v in tasks.items()]
    resolved_tasks = _resolve_deps(args.tasks, tasks_with_deps)

    # runtime
    for task_name in resolved_tasks:
        if task_name in tasks:
            task = tasks[task_name]
            try:
                task.func(_build_task_context(task))
            except KeyboardInterrupt:
                pass


if __name__ == "__main__":
    env_files = [
        {"file": ".env.defaults", "override": False},
        {"file": ".env.secrets", "override": False},
        {"file": ".env.user", "override": True},
        {"file": ".env.local", "override": True},
        {"file": ".env", "override": True},
    ]

    for env in env_files:
        load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), env["file"])), env["override"])

    _process_tasks()
