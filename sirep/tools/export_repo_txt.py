"""
Exporta o conteúdo (código) de todos os arquivos texto do projeto para arquivos .txt,
preservando a estrutura de pastas dentro de uma pasta de saída.

Ignora:
  - Diretórios: __pycache__, .venv, sql (e tudo dentro), tests (e tudo dentro)
  - Arquivos: __init__.py, .env, .env.example, pyproject.toml, sirep.db

Uso:
  python export_project_to_txt.py --root "C:\\caminho\\do\\projeto" --out "C:\\caminho\\de\\saida"

Dicas Windows:
  - Coloque caminhos entre aspas se tiverem espaços.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Tuple

# Pastas a ignorar, em qualquer nível
IGNORE_DIRS = {".venv", "__pycache__", "sql", "tests", "txt_export"}

# Arquivos específicos a ignorar (por nome exato)
IGNORE_FILES = {"__init__.py", ".env", ".env.example", "pyproject.toml", "sirep.db", "export_repo_txt.py"}

# Extensões que normalmente são binárias e devem ser puladas
LIKELY_BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp",
    ".pdf", ".zip", ".rar", ".7z", ".tar", ".gz", ".xz",
    ".dll", ".exe", ".so", ".dylib", ".bin",
    ".mp3", ".wav", ".flac", ".ogg",
    ".mp4", ".mkv", ".avi", ".mov",
}


def is_probably_binary(sample: bytes) -> bool:
    """Heurística simples para detectar binário."""
    if b"\x00" in sample:
        return True
    # Muita quantidade de bytes não-texto tende a indicar binário
    # (permite acentos/UTF-8 multibyte)
    text_chars = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)))
    nontext = sample.translate(None, text_chars)
    # Se mais de 30% são não-texto, consideramos binário
    return len(nontext) / max(1, len(sample)) > 0.30


def read_text_with_fallback(p: Path) -> Tuple[str | None, str | None]:
    """
    Tenta ler como texto em UTF-8; se falhar, tenta latin-1.
    Retorna (conteudo, erro) — erro None indica sucesso.
    """
    try:
        data = p.read_bytes()
    except Exception as e:
        return None, f"erro ao ler bytes: {e}"

    if p.suffix.lower() in LIKELY_BINARY_EXTS:
        return None, "binário (extensão)"

    # Heurística de binário
    head = data[:8192]
    if is_probably_binary(head):
        return None, "binário (heurística)"

    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return data.decode(enc), None
        except Exception:
            continue
    return None, "falha ao decodificar em utf-8/latin-1"


def should_skip_dir(dir_name: str) -> bool:
    return dir_name in IGNORE_DIRS


def should_skip_file(name: str) -> bool:
    return name in IGNORE_FILES


def main():
    ap = argparse.ArgumentParser(description="Exporta código do projeto para .txt")
    ap.add_argument("--root", required=True, help="Pasta raiz do projeto")
    ap.add_argument("--out", required=True, help="Pasta de saída para os .txt")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    out_base = Path(args.out).resolve()
    out_base.mkdir(parents=True, exist_ok=True)

    manifest_lines = ["relpath,status,reason,bytes\n"]

    exported = 0
    skipped = 0
    errors = 0

    for dirpath, dirnames, filenames in os.walk(root):
        # Remover in-place os diretórios ignorados para não descer neles
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]

        for fname in filenames:
            # Checagens de ignorados por nome
            if should_skip_file(fname):
                skipped += 1
                rel = Path(dirpath, fname).resolve().relative_to(root)
                manifest_lines.append(f"{rel},skipped,ignored-name,\n")
                continue

            src_path = Path(dirpath, fname)
            rel_path = src_path.resolve().relative_to(root)

            content, err = read_text_with_fallback(src_path)
            if err is not None:
                skipped += 1
                size = src_path.stat().st_size if src_path.exists() else ""
                manifest_lines.append(f"{rel_path},skipped,{err},{size}\n")
                continue

            # Caminho espelhado na saída, mantendo subpastas, e adicionando .txt ao final
            out_path = out_base / rel_path
            out_path = out_path.with_suffix(out_path.suffix + ".txt")
            out_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                header = f"=== SOURCE: {rel_path.as_posix()} ===\n"
                out_path.write_text(header + content, encoding="utf-8")
                exported += 1
                manifest_lines.append(f"{rel_path},exported,ok,{len(content.encode('utf-8'))}\n")
            except Exception as e:
                errors += 1
                manifest_lines.append(f"{rel_path},error,{e},\n")

    # Grava manifest
    manifest_path = out_base / "manifest.csv"
    manifest_path.write_text("".join(manifest_lines), encoding="utf-8")

    print(f"[OK] Exportados: {exported} | Ignorados: {skipped} | Erros: {errors}")
    print(f"Manifesto: {manifest_path}")


if __name__ == "__main__":
    main()