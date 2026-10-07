"""The argparse tree and command dispatch."""

from __future__ import annotations

import argparse
import os
import sys

from trident_cli import __version__, journal, output
from trident_cli.commands import aion as aion_cmd
from trident_cli.commands import config as config_cmd
from trident_cli.commands import day as day_cmd
from trident_cli.commands import doctor as doctor_cmd
from trident_cli.commands import done as done_cmd
from trident_cli.commands import export as export_cmd
from trident_cli.commands import history as history_cmd
from trident_cli.commands import log as log_cmd
from trident_cli.commands import refuse as refuse_cmd
from trident_cli.commands import season as season_cmd
from trident_cli.commands import stop as stop_cmd
from trident_cli.commands import task as task_cmd
from trident_cli.errors import CliError, EXIT_RUNTIME


def _json_parent() -> argparse.ArgumentParser:
    """A shared ``--json`` flag.

    ``default=SUPPRESS`` keeps a subparser from clobbering a value already set
    before the subcommand (argparse copies subparser defaults upward), so both
    ``trident --json doctor`` and ``trident doctor --json`` work.
    """
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="print results as JSON")
    return parent


def build_parser() -> argparse.ArgumentParser:
    json_parent = _json_parent()
    parser = argparse.ArgumentParser(
        prog="trident",
        parents=[json_parent],
        description="Trident in the terminal: write down what happened, keep it in view, "
        "and pick the next step.",
    )
    parser.add_argument(
        "--version", action="version", version=f"trident-cli {__version__}", help="show the version and exit"
    )

    sub = parser.add_subparsers(dest="command", metavar="<command>")

    doctor = sub.add_parser("doctor", parents=[json_parent], help="check this machine and the configuration")
    doctor.set_defaults(func=doctor_cmd.run)

    config = sub.add_parser("config", parents=[json_parent], help="read and write settings")
    config.set_defaults(func=config_cmd.cmd_help, parser=config)
    config_sub = config.add_subparsers(dest="config_command", metavar="<action>")

    config_list = config_sub.add_parser("list", parents=[json_parent], help="show all settings and their source")
    config_list.set_defaults(func=config_cmd.cmd_list)

    config_get = config_sub.add_parser("get", parents=[json_parent], help="print one setting")
    config_get.add_argument("key")
    config_get.set_defaults(func=config_cmd.cmd_get)

    config_set = config_sub.add_parser("set", parents=[json_parent], help="validate and store a setting")
    config_set.add_argument("key")
    config_set.add_argument("value")
    config_set.set_defaults(func=config_cmd.cmd_set)

    config_unset = config_sub.add_parser("unset", parents=[json_parent], help="return a setting to its default")
    config_unset.add_argument("key")
    config_unset.set_defaults(func=config_cmd.cmd_unset)

    log = sub.add_parser("log", parents=[json_parent], help="write down what happened")
    log.add_argument("-i", "--interactive", action="store_true", help="ask for the output and cost weights")
    log.add_argument("words", nargs="*", metavar="text", help="what happened, followed by optional pairs")
    log.set_defaults(func=log_cmd.run)

    day = sub.add_parser("day", parents=[json_parent], help="show a Trident day")
    day_group = day.add_mutually_exclusive_group()
    day_group.add_argument("--yesterday", action="store_true", help="show the previous Trident day")
    day_group.add_argument("--date", metavar="YYYY-MM-DD", help="show a specific Trident day")
    day.set_defaults(func=day_cmd.run)

    stop = sub.add_parser("stop", parents=[json_parent], help="mark a rest day")
    stop.add_argument("--reason", choices=journal.STOP_REASONS, help="why the day is a rest day")
    stop.set_defaults(func=stop_cmd.run)

    season = sub.add_parser("season", parents=[json_parent], help="show a season (chapter)")
    season_group = season.add_mutually_exclusive_group()
    season_group.add_argument("--number", type=int, metavar="N", help="show one season by number")
    season_group.add_argument("--list", action="store_true", help="show every season, newest first")
    season.set_defaults(func=season_cmd.run)

    history = sub.add_parser("history", parents=[json_parent], help="show past days")
    history.add_argument("--since", metavar="WHEN", help="7d, an ISO date, or all")
    history.add_argument("--until", metavar="YYYY-MM-DD", help="an upper bound (default: today)")
    history.set_defaults(func=history_cmd.run)

    export = sub.add_parser("export", parents=[json_parent], help="export the journal")
    export.add_argument("--format", choices=("json", "csv"), default="json", help="output format (default: json)")
    export.add_argument("--output", metavar="FILE", help="write to a file instead of stdout")
    export.add_argument("--force", action="store_true", help="overwrite an existing --output file")
    export.set_defaults(func=export_cmd.run)

    task = sub.add_parser("task", parents=[json_parent], help="manage the plan (Chronos)")
    task.set_defaults(func=task_cmd.run, plain=False)
    task_sub = task.add_subparsers(dest="task_command", metavar="<action>")

    task_list = task_sub.add_parser("list", parents=[json_parent], help="show the plan for a day")
    task_list.add_argument("--date", metavar="YYYY-MM-DD", help="show a chosen Trident day")
    task_list.add_argument("--plain", action="store_true", help="one open task per line")
    task_list.set_defaults(func=task_cmd.run)

    task_add = task_sub.add_parser("add", parents=[json_parent], help="add an open task")
    add_surface = task_add.add_mutually_exclusive_group()
    add_surface.add_argument("--date", metavar="YYYY-MM-DD", help="schedule it on a Trident day")
    add_surface.add_argument("--underline", action="store_true", help="place it under the line")
    task_add.add_argument("--note", metavar="TEXT", help="a description")
    task_add.add_argument("--remind", metavar="HH:MM", help="a stored reminder time")
    task_add.add_argument("--frog", action="store_true", help="mark it as the frog")
    add_strategy = task_add.add_mutually_exclusive_group()
    add_strategy.add_argument("--epic", metavar="ID", help="link it to an Epic")
    add_strategy.add_argument("--sprint", metavar="ID", help="link it to a Sprint")
    task_add.add_argument("words", nargs="*", metavar="text")
    task_add.set_defaults(func=task_cmd.run)

    task_move = task_sub.add_parser("move", parents=[json_parent], help="move a task to another day")
    task_move.add_argument("id")
    task_move.add_argument("--date", required=True, metavar="YYYY-MM-DD", help="the target Trident day")
    task_move.set_defaults(func=task_cmd.run)

    task_later = task_sub.add_parser("later", parents=[json_parent], help="move an open task to Aion")
    task_later.add_argument("id")
    task_later.set_defaults(func=task_cmd.run)

    task_subtask = task_sub.add_parser("subtask", parents=[json_parent], help="turn a task into a step of another")
    task_subtask.add_argument("id")
    task_subtask.add_argument("--parent", required=True, metavar="ID", help="the parent task id")
    task_subtask.set_defaults(func=task_cmd.run)

    task_edit = task_sub.add_parser("edit", parents=[json_parent], help="edit a task's fields")
    task_edit.add_argument("id")
    task_edit.add_argument("--text", metavar="TEXT", help="a new title")
    task_edit.add_argument("--note", metavar="TEXT", help="a description (empty clears it)")
    edit_remind = task_edit.add_mutually_exclusive_group()
    edit_remind.add_argument("--remind", metavar="HH:MM", help="a stored reminder time")
    edit_remind.add_argument("--no-remind", action="store_true", help="clear the reminder")
    edit_frog = task_edit.add_mutually_exclusive_group()
    edit_frog.add_argument("--frog", action="store_true", help="mark it as the frog")
    edit_frog.add_argument("--no-frog", action="store_true", help="clear the frog mark")
    edit_surface = task_edit.add_mutually_exclusive_group()
    edit_surface.add_argument("--underline", action="store_true", help="place it under the line")
    edit_surface.add_argument("--no-underline", action="store_true", help="bring it back to a day")
    task_edit.add_argument("--date", metavar="YYYY-MM-DD", help="move it to a Trident day")
    edit_strategy = task_edit.add_mutually_exclusive_group()
    edit_strategy.add_argument("--epic", metavar="ID", help="link it to an Epic")
    edit_strategy.add_argument("--sprint", metavar="ID", help="link it to a Sprint")
    edit_strategy.add_argument("--no-strategy", action="store_true", help="unlink the Strategy")
    task_edit.set_defaults(func=task_cmd.run)

    task_show = task_sub.add_parser("show", parents=[json_parent], help="show a task's fields and steps")
    task_show.add_argument("id")
    task_show.set_defaults(func=task_cmd.run)

    task_step = task_sub.add_parser("step", parents=[json_parent], help="work with a task's steps")
    task_step.set_defaults(func=task_cmd.run)
    step_sub = task_step.add_subparsers(dest="step_command", metavar="<action>")

    step_add = step_sub.add_parser("add", parents=[json_parent], help="append a step")
    step_add.add_argument("step_task")
    step_add.add_argument("words", nargs="*", metavar="text")
    step_add.set_defaults(func=task_cmd.run)

    for action, help_text in (
        ("remove", "remove an unprogressed step"),
        ("done", "mark a step complete"),
        ("skip", "skip a step"),
        ("resume", "resume a step"),
    ):
        step_action = step_sub.add_parser(action, parents=[json_parent], help=help_text)
        step_action.add_argument("step_task")
        step_action.add_argument("order")
        step_action.set_defaults(func=task_cmd.run)

    done = sub.add_parser("done", parents=[json_parent], help="complete a task")
    done.add_argument("id")
    done.add_argument("words", nargs="*", metavar="attributes")
    done.add_argument("-i", "--interactive", action="store_true", help="ask for the output and cost weights")
    done.add_argument("--silent", action="store_true", help="mark done without writing an entry")
    done.set_defaults(func=done_cmd.run)

    refuse = sub.add_parser("refuse", parents=[json_parent], help="let a task go")
    refuse.add_argument("id")
    refuse.set_defaults(func=refuse_cmd.run)

    aion = sub.add_parser("aion", parents=[json_parent], help="manage the Aion backlog")
    aion.set_defaults(func=aion_cmd.run, plain=False)
    aion_sub = aion.add_subparsers(dest="aion_command", metavar="<action>")

    aion_list = aion_sub.add_parser("list", parents=[json_parent], help="list open ideas, oldest first")
    aion_list.add_argument("--plain", action="store_true", help="one open idea per line")
    aion_list.set_defaults(func=aion_cmd.run)

    aion_add = aion_sub.add_parser("add", parents=[json_parent], help="add an idea")
    aion_add.add_argument("words", nargs="*", metavar="text")
    aion_add.add_argument("--why", metavar="TEXT", help="why this idea matters")
    aion_add.add_argument("--note", metavar="TEXT", help="a description")
    aion_add.set_defaults(func=aion_cmd.run)

    aion_pull = aion_sub.add_parser("pull", parents=[json_parent], help="turn an idea into an open task")
    aion_pull.add_argument("id")
    aion_pull.set_defaults(func=aion_cmd.run)

    aion_drop = aion_sub.add_parser("drop", parents=[json_parent], help="drop an idea")
    aion_drop.add_argument("id")
    aion_drop.set_defaults(func=aion_cmd.run)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return the process exit code."""
    output.reset()
    output.setup_streams()
    parser = build_parser()

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        return code if isinstance(code, int) else 1

    if getattr(args, "command", None) is None:
        parser.print_help()
        return 0

    output.set_json(bool(getattr(args, "json", False)))

    try:
        result = args.func(args)
        return int(result) if result is not None else 0
    except CliError as exc:
        output.error(f"trident: {exc.message}")
        return exc.code
    except KeyboardInterrupt:
        output.error("trident: interrupted")
        return 130
    except Exception as exc:  # noqa: BLE001 - the last line of defence
        if os.environ.get("TRIDENT_DEBUG") == "1":
            raise
        output.error(f"trident: unexpected error: {type(exc).__name__}: {exc}")
        return EXIT_RUNTIME


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
