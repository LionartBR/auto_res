from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, Sequence

from sirep.app.steps import default_step_sequence, deduplicate_steps, parse_steps_text
from sirep.domain.enums import Step
from sirep.infra.db import init_db
from sirep.services.orchestrator import Orchestrator


DEFAULT_OUTPUTS: tuple[Path, ...] = (
    Path("Rescindidos_CNPJ.txt"),
    Path("Rescindidos_CEI.txt"),
)


def build_parser() -> argparse.ArgumentParser:
    """Return an argument parser for the helper script."""

    parser = argparse.ArgumentParser(
        description=(
            "Executa o pipeline SIREP usando a mesma sequência padrão da CLI, "
            "permitindo informar etapas personalizadas quando necessário."
        )
    )
    parser.add_argument(
        "--steps",
        help=(
            "Lista de etapas separadas por vírgula. Quando omitido utiliza a sequência "
            "padrão exposta pela CLI (veja --list-steps)."
        ),
    )
    parser.add_argument(
        "--list-steps",
        action="store_true",
        help="Apenas mostra a ordem padrão do pipeline e sai.",
    )
    return parser


def resolve_steps(raw: str | None) -> list[Step]:
    """Return the sequence of steps requested by the user."""

    if not raw:
        return default_step_sequence()
    steps = parse_steps_text(raw)
    return deduplicate_steps(steps)


def report_generated_files(paths: Iterable[Path]) -> None:
    """Print the generated files (if any) to stdout."""

    for path in paths:
        if path.exists():
            size = path.stat().st_size
            print(f"Gerado: {path} ({size} bytes)")


def run_pipeline(steps: Sequence[Step]) -> None:
    """Execute the orchestrator for the provided step sequence."""

    orchestrator = Orchestrator()
    resultado = orchestrator.run_steps(list(steps))
    print(resultado)
    report_generated_files(DEFAULT_OUTPUTS)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point used by ``python -m sirep.scripts.run_pipeline``."""

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_steps:
        for step in default_step_sequence():
            print(step.name)
        return 0

    try:
        steps = resolve_steps(args.steps)
    except ValueError as exc:
        parser.error(str(exc))
        return 2

    init_db()
    run_pipeline(steps)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())