from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from sirep.domain.enums import Step
from sirep.domain.logs import (
    GESTAO_STAGE_DEFINITIONS,
    TRATAMENTO_STAGE_DEFINITIONS,
)


@dataclass(frozen=True)
class StepMetadata:
    """Metadata describing a pipeline step exposed by the API/CLI."""

    step: Step
    code: str
    label: str
    category: str
    order: int
    stage: int | None = None

    def as_dict(self) -> dict[str, object]:
        """Return a serialisable representation of the metadata."""

        data: dict[str, object] = {
            "code": self.code,
            "label": self.label,
            "category": self.category,
            "order": self.order,
        }
        if self.stage is not None:
            data["stage"] = self.stage
        return data


def _step_number(step: Step) -> int:
    value = step.name
    for prefix in ("ETAPA_",):
        if value.startswith(prefix):
            value = value[len(prefix) :]
            break
    try:
        return int(value.split("_", 1)[0])
    except ValueError:
        return 0


def _register_defaults() -> dict[Step, StepMetadata]:
    mapping: dict[Step, StepMetadata] = {}

    for numero, descricao in GESTAO_STAGE_DEFINITIONS.items():
        member = f"ETAPA_{numero}"
        if member in Step.__members__:
            step = Step[member]
            mapping[step] = StepMetadata(
                step=step,
                code=step.name,
                label=f"Gestão da Base – {descricao}",
                category="gestao",
                order=_step_number(step),
                stage=numero,
            )

    tratamento_stage_to_step = [
        (1, Step.ETAPA_5),
        (2, Step.ETAPA_7),
        (3, Step.ETAPA_8),
        (4, Step.ETAPA_9),
        (5, Step.ETAPA_10),
        (6, Step.ETAPA_11),
        (7, Step.ETAPA_12),
    ]

    for stage_num, step in tratamento_stage_to_step:
        descricao = TRATAMENTO_STAGE_DEFINITIONS.get(stage_num)
        if descricao is None:
            continue
        mapping[step] = StepMetadata(
            step=step,
            code=step.name,
            label=f"Tratamento – {descricao}",
            category="tratamento",
            order=_step_number(step),
            stage=stage_num,
        )

    mapping[Step.ETAPA_13] = StepMetadata(
        step=Step.ETAPA_13,
        code=Step.ETAPA_13.name,
        label="Tratamento – Etapa 8 – Dossiê do Processo",
        category="tratamento",
        order=_step_number(Step.ETAPA_13),
        stage=8,
    )

    return mapping


_STEP_METADATA = _register_defaults()


def list_step_metadata() -> list[StepMetadata]:
    """Return metadata for all known steps ordered by pipeline progression."""

    return sorted(_STEP_METADATA.values(), key=lambda meta: meta.order)


def metadata_for_step(step: Step) -> StepMetadata:
    """Return metadata associated with a specific ``Step`` value."""

    return _STEP_METADATA[step]


def default_step_sequence() -> list[Step]:
    """Return the default execution order for the pipeline."""

    return [meta.step for meta in list_step_metadata()]


def _normalize_step_code(raw: str) -> str:
    candidato = (raw or "").strip()
    if not candidato:
        return ""
    candidato = candidato.replace("-", "_").replace(" ", "_")
    candidato_upper = candidato.upper()
    if candidato_upper in Step.__members__:
        return candidato_upper
    for member, step in Step.__members__.items():
        if candidato_upper == step.value.upper():
            return member
    if not candidato_upper.startswith("ETAPA_"):
        candidato_upper = f"ETAPA_{candidato_upper}"
        if candidato_upper in Step.__members__:
            return candidato_upper
    return ""


def parse_step_codes(entries: Sequence[str | Step]) -> list[Step]:
    """Parse user provided entries into ``Step`` instances preserving order."""

    resolved: list[Step] = []
    for entry in entries:
        if isinstance(entry, Step):
            resolved.append(entry)
            continue
        normalized = _normalize_step_code(entry)
        if not normalized or normalized not in Step.__members__:
            raise ValueError(f"Etapa inválida '{entry}'.")
        resolved.append(Step[normalized])
    return resolved


def parse_steps_text(raw: str) -> list[Step]:
    """Parse a comma separated list of step names as accepted by the CLI/API."""

    items = [item.strip() for item in (raw or "").split(",") if item.strip()]
    if not items:
        raise ValueError("Nenhuma etapa informada.")
    return parse_step_codes(items)


def deduplicate_steps(steps: Sequence[Step]) -> list[Step]:
    """Remove duplicated steps keeping the first occurrence of each one."""

    seen: set[Step] = set()
    ordered: list[Step] = []
    for step in steps:
        if step in seen:
            continue
        seen.add(step)
        ordered.append(step)
    return ordered
