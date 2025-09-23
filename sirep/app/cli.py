from __future__ import annotations

import argparse
import sys
from typing import Sequence

import uvicorn

from sirep.app.api import app
from sirep.app.steps import default_step_sequence, parse_steps_text
from sirep.services.orchestrator import Orchestrator


def _default_steps() -> str:
    return ",".join(step.name for step in default_step_sequence())


def build_parser() -> argparse.ArgumentParser:
    """Cria o parser de argumentos da CLI."""

    parser = argparse.ArgumentParser("sirep")
    sub = parser.add_subparsers(dest="cmd")
    sub.required = True

    run = sub.add_parser("run", help="Executa etapas de tratamento")
    run.add_argument(
        "--steps",
        default=_default_steps(),
        help="Lista de etapas separadas por vírgula (ex.: ETAPA_1,ETAPA_2).",
    )

    serve = sub.add_parser("serve", help="Inicia API FastAPI via Uvicorn")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

    return parser
def handle_run(steps_text: str) -> int:
    """Executa o comando ``run`` retornando um código de saída."""

    try:
        steps = parse_steps_text(steps_text)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    orchestrator = Orchestrator()
    resultado = orchestrator.run_steps(steps)
    print(resultado)
    return 0


def handle_serve(host: str, port: int) -> int:
    """Executa o comando ``serve`` retornando um código de saída."""

    uvicorn.run(app, host=host, port=port)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "serve":
        return handle_serve(args.host, args.port)
    if args.cmd == "run":
        return handle_run(args.steps)

    parser.error("Comando inválido")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
