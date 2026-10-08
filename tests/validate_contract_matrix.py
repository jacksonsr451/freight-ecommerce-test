"""Conferência documental offline: métodos, rotas, abilities e referências.

Uso: python tests/validate_contract_matrix.py
Não realiza HTTP nem valida operação da Packsenvios.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTE = re.compile(r"\|\s*(GET|POST)\s*\|\s*`(/api/v1/freight/[^`]+)`\s*\|")
ABILITY = re.compile(r"`(freight:[a-z:]+)`")


def routes(text: str) -> dict[tuple[str, str], tuple[set[str], int, str]]:
    result = {}
    for number, line in enumerate(text.splitlines(), 1):
        match = ROUTE.search(line)
        if not match:
            continue
        key = match.groups()
        if key in result:
            raise ValueError(f"Rota duplicada: {key}")
        ability_cell = line[match.end() :].split("|", 1)[0]
        result[key] = (set(ABILITY.findall(ability_cell)), number, line)
    return result


def validate(reference: str, matrix: str) -> int:
    expected = routes(reference)
    actual = routes(matrix)
    if not expected:
        raise ValueError("Tabela contratual sem rotas; verificação inconclusiva")
    if expected.keys() != actual.keys():
        raise ValueError(
            f"Ausentes: {expected.keys() - actual.keys()}; "
            f"extras: {actual.keys() - expected.keys()}"
        )
    for key, (abilities, source_line, _) in expected.items():
        received, _, matrix_line = actual[key]
        if not abilities or received != abilities:
            raise ValueError(f"Abilities divergentes: {key}: {received} != {abilities}")
        if not re.search(rf"\bL{source_line}\b", matrix_line):
            raise ValueError(f"Referência L{source_line} ausente: {key}")
        if "HTTP: **não**" not in matrix_line:
            raise ValueError(f"Estado de verificação HTTP ausente: {key}")
    return len(expected)


def main() -> None:
    reference = (ROOT / "docs/reference/gestao-frete-integracao-ecommerce-teste.md").read_text(
        encoding="utf-8"
    )
    matrix = (ROOT / "docs/architecture/contract-matrix.md").read_text(encoding="utf-8")
    count = validate(reference, matrix)
    # Confere também a sintaxe dos exemplos JSON efetivamente presentes na fonte.
    examples = re.findall(r"```json\s*\n(.*?)\n```", reference, re.DOTALL)
    for example in examples:
        json.loads(example)
    print(f"PASS: {count} rotas; métodos, abilities e linhas da fonte coincidem.")
    print(f"PASS: todas as rotas marcadas sem HTTP; {len(examples)} exemplos JSON válidos.")
    print("SKIP: HTTP real, filas, despacho e webhook externos não executados.")


if __name__ == "__main__":
    main()
