"""Ferramentas para exportar o código fonte do repositório para arquivos ``.txt``.

Além da exportação "aberta" dos arquivos de texto (com cabeçalho indicando o caminho
original), o script também oferece um fluxo de exportação criptografada. O conteúdo é
ofuscado com uma cifra simétrica simples baseada em derivação PBKDF2 e um gerador de
keystream utilizando SHA-256. A descriptografia é realizada executando o script
neste mesmo módulo utilizando o modo ``decrypt``.

Ignora por padrão:

* Diretórios: ``__pycache__``, ``.venv``, ``sql``, ``tests``, ``txt_export`` e ``logs``.
* Arquivos: ``__init__.py``, ``.env``, ``.env.example``, ``pyproject.toml``, ``sirep.db``
  e o próprio ``export_repo_txt.py``.

Uso básico::

    python -m sirep.tools.export_repo_txt --root "/caminho/projeto" --out "/saida"

Para exportação criptografada::

    python -m sirep.tools.export_repo_txt --root "/caminho/projeto" \
        --out "/saida" --mode encrypt --passphrase "segredo"

Para descriptografar uma pasta previamente exportada (``*.enc.txt``)::

    python -m sirep.tools.export_repo_txt --root "/saida" \
        --out "/saida_decriptografada" --mode decrypt --passphrase "segredo"
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
import secrets
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable

# Pastas a ignorar, em qualquer nível
IGNORE_DIRS = {".venv", "__pycache__", "txt_export", "tools", "logs", ".git"}

# Arquivos específicos a ignorar (por nome exato)
IGNORE_FILES = {"__init__.py", ".env", ".env.example", "pyproject.toml", "sirep.db", ".gitignore", "AGENTS.md"}

# Extensões que normalmente são binárias e devem ser puladas
LIKELY_BINARY_EXTS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".ico",
    ".webp",
    ".pdf",
    ".zip",
    ".rar",
    ".7z",
    ".tar",
    ".gz",
    ".xz",
    ".dll",
    ".exe",
    ".so",
    ".dylib",
    ".bin",
    ".mp3",
    ".wav",
    ".flac",
    ".ogg",
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
}

HEADER_PREFIX = "=== SOURCE: "
HEADER_SUFFIX = " ===\n"
ENC_PREFIX = "ENCv1"
SALT_BYTES = 16
NONCE_BYTES = 16
PBKDF2_ITERATIONS = 200_000
MANIFEST_NAME = "manifest.csv"


class ExportMode(str, Enum):
    """Representa os modos de operação do script."""

    PLAIN = "plain"
    ENCRYPT = "encrypt"
    DECRYPT = "decrypt"


@dataclass
class ExportStats:
    """Acumula estatísticas do processamento."""

    exported: int = 0
    skipped: int = 0
    errors: int = 0


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


def read_text_with_fallback(p: Path) -> tuple[str | None, str | None]:
    """Tenta ler como texto em UTF-8; se falhar, tenta latin-1."""

    try:
        data = p.read_bytes()
    except Exception as exc:  # pragma: no cover - acesso ao FS pode falhar
        return None, f"erro ao ler bytes: {exc}"

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


def build_header(rel_path: Path) -> str:
    """Retorna o cabeçalho utilizado em cada arquivo exportado."""

    return f"{HEADER_PREFIX}{rel_path.as_posix()}{HEADER_SUFFIX}"


def parse_header(header_line: str) -> Path | None:
    """Extrai o caminho relativo armazenado no cabeçalho."""

    if not header_line.startswith(HEADER_PREFIX):
        return None
    if not header_line.endswith(HEADER_SUFFIX):
        return None
    rel_str = header_line[len(HEADER_PREFIX) : -len(HEADER_SUFFIX)]
    rel_path = Path(rel_str)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        return None
    return rel_path


def split_header_and_body(text: str) -> tuple[str, str]:
    """Separa o cabeçalho da carga útil."""

    lines = text.splitlines(keepends=True)
    if not lines:
        return "", ""
    header = lines[0]
    body = "".join(lines[1:])
    return header, body


def derive_key(passphrase: str, salt: bytes) -> bytes:
    """Deriva uma chave simétrica a partir da senha e do salt."""

    return hashlib.pbkdf2_hmac(
        "sha256",
        passphrase.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
        dklen=32,
    )


def keystream_bytes(key: bytes, nonce: bytes, length: int) -> bytes:
    """Gera um fluxo pseudoaleatório de bytes utilizando SHA-256."""

    stream = bytearray()
    counter = 0
    while len(stream) < length:
        counter_bytes = counter.to_bytes(8, "big", signed=False)
        stream.extend(hashlib.sha256(key + nonce + counter_bytes).digest())
        counter += 1
    return bytes(stream[:length])


def xor_bytes(data: bytes, keystream: bytes) -> bytes:
    """Aplica XOR byte a byte entre ``data`` e ``keystream``."""

    return bytes(b ^ k for b, k in zip(data, keystream))


def encode_chunk(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii")


def decode_chunk(data: str) -> bytes:
    return base64.urlsafe_b64decode(data.encode("ascii"))


def encrypt_payload(content: str, passphrase: str) -> str:
    """Retorna o payload criptografado a ser gravado após o cabeçalho."""

    salt = secrets.token_bytes(SALT_BYTES)
    nonce = secrets.token_bytes(NONCE_BYTES)
    key = derive_key(passphrase, salt)
    plain_bytes = content.encode("utf-8")
    stream = keystream_bytes(key, nonce, len(plain_bytes))
    cipher = xor_bytes(plain_bytes, stream)
    return ":".join(
        [ENC_PREFIX, encode_chunk(salt), encode_chunk(nonce), encode_chunk(cipher)]
    ) + "\n"


def decrypt_payload(payload: str, passphrase: str) -> str:
    """Descriptografa um payload gerado por :func:`encrypt_payload`."""

    raw = payload.strip()
    parts = raw.split(":")
    if len(parts) != 4 or parts[0] != ENC_PREFIX:
        raise ValueError("payload inválido ou não criptografado")
    salt = decode_chunk(parts[1])
    nonce = decode_chunk(parts[2])
    cipher = decode_chunk(parts[3])
    key = derive_key(passphrase, salt)
    stream = keystream_bytes(key, nonce, len(cipher))
    plain_bytes = xor_bytes(cipher, stream)
    return plain_bytes.decode("utf-8")


def ensure_passphrase(passphrase: str | None, parser: argparse.ArgumentParser) -> str:
    """Valida se a frase-secreta foi informada."""

    if not passphrase:
        parser.error("--passphrase é obrigatório para os modos encrypt e decrypt")
    if passphrase.strip() == "":
        parser.error("--passphrase não pode ser vazia")
    return passphrase


def make_out_path(base: Path, rel_path: Path, mode: ExportMode) -> Path:
    """Calcula o caminho de saída respeitando o modo de operação."""

    suffix = ".txt"
    if mode is ExportMode.ENCRYPT:
        suffix = ".enc.txt"
    out_path = base / rel_path
    return out_path.with_suffix(out_path.suffix + suffix)


def run_plain_or_encrypted_export(
    root: Path,
    out_base: Path,
    mode: ExportMode,
    manifest_lines: list[str],
    stats: ExportStats,
    passphrase: str | None = None,
) -> None:
    """Percorre o repositório exportando arquivos em modo simples ou criptografado."""

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]

        for fname in filenames:
            if should_skip_file(fname):
                stats.skipped += 1
                rel = Path(dirpath, fname).resolve().relative_to(root)
                manifest_lines.append(f"{rel},skipped,ignored-name,\n")
                continue

            src_path = Path(dirpath, fname)
            rel_path = src_path.resolve().relative_to(root)

            content, err = read_text_with_fallback(src_path)
            if err is not None:
                stats.skipped += 1
                size = src_path.stat().st_size if src_path.exists() else ""
                manifest_lines.append(f"{rel_path},skipped,{err},{size}\n")
                continue

            out_path = make_out_path(out_base, rel_path, mode)
            out_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                header = build_header(rel_path)
                body = content
                reason = "ok"
                if mode is ExportMode.ENCRYPT:
                    assert passphrase is not None
                    body = encrypt_payload(content, passphrase)
                    reason = "encrypted"
                out_path.write_text(header + body, encoding="utf-8")
                stats.exported += 1
                manifest_lines.append(
                    f"{rel_path},exported,{reason},{len(content.encode('utf-8'))}\n"
                )
            except Exception as exc:  # pragma: no cover - exceção rara/ambiente
                stats.errors += 1
                manifest_lines.append(f"{rel_path},error,{exc},\n")


def run_decryption(
    root: Path,
    out_base: Path,
    manifest_lines: list[str],
    stats: ExportStats,
    passphrase: str,
) -> None:
    """Descriptografa arquivos ``.enc.txt`` gerados previamente."""

    for enc_path in root.rglob("*.enc.txt"):
        if any(part in IGNORE_DIRS for part in enc_path.parts):
            continue

        rel_input = enc_path.resolve().relative_to(root)
        try:
            raw_text = enc_path.read_text(encoding="utf-8")
        except Exception as exc:
            stats.errors += 1
            manifest_lines.append(f"{rel_input},error,read-failed:{exc},\n")
            continue

        header, payload = split_header_and_body(raw_text)
        rel_from_header = parse_header(header)
        if rel_from_header is None:
            stats.skipped += 1
            manifest_lines.append(f"{rel_input},skipped,missing-header,\n")
            continue

        try:
            plaintext = decrypt_payload(payload, passphrase)
        except Exception as exc:
            stats.errors += 1
            manifest_lines.append(f"{rel_from_header},error,decrypt-failed:{exc},\n")
            continue

        out_path = make_out_path(out_base, rel_from_header, ExportMode.PLAIN)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            out_path.write_text(build_header(rel_from_header) + plaintext, encoding="utf-8")
        except Exception as exc:  # pragma: no cover - exceção rara/ambiente
            stats.errors += 1
            manifest_lines.append(f"{rel_from_header},error,write-failed:{exc},\n")
            continue

        stats.exported += 1
        manifest_lines.append(
            f"{rel_from_header},decrypted,ok,{len(plaintext.encode('utf-8'))}\n"
        )


def write_manifest(out_base: Path, manifest_lines: Iterable[str]) -> Path:
    """Persiste o manifesto dos arquivos processados."""

    manifest_path = out_base / MANIFEST_NAME
    manifest_path.write_text("".join(manifest_lines), encoding="utf-8")
    return manifest_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Exporta código do projeto para .txt")
    parser.add_argument("--root", required=True, help="Pasta raiz do projeto")
    parser.add_argument("--out", required=True, help="Pasta de saída para os arquivos")
    parser.add_argument(
        "--mode",
        choices=[mode.value for mode in ExportMode],
        default=ExportMode.PLAIN.value,
        help=(
            "Modo de operação: plain (padrão) exporta texto aberto; "
            "encrypt exporta conteúdo criptografado; decrypt reverte arquivos .enc.txt"
        ),
    )
    parser.add_argument(
        "--passphrase",
        help="Frase-secreta utilizada para criptografar/descriptografar",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    mode = ExportMode(args.mode)

    root = Path(args.root).resolve()
    if not root.exists():
        parser.error(f"pasta raiz '{root}' inexistente")
    if not root.is_dir():
        parser.error(f"pasta raiz '{root}' não é um diretório")

    out_base = Path(args.out).resolve()
    out_base.mkdir(parents=True, exist_ok=True)

    passphrase: str | None = args.passphrase
    if mode in {ExportMode.ENCRYPT, ExportMode.DECRYPT}:
        passphrase = ensure_passphrase(passphrase, parser)

    manifest_lines = ["relpath,status,reason,bytes\n"]
    stats = ExportStats()

    if mode is ExportMode.DECRYPT:
        assert passphrase is not None
        run_decryption(root, out_base, manifest_lines, stats, passphrase)
    else:
        run_plain_or_encrypted_export(root, out_base, mode, manifest_lines, stats, passphrase)

    manifest_path = write_manifest(out_base, manifest_lines)

    print(f"[OK] Exportados: {stats.exported} | Ignorados: {stats.skipped} | Erros: {stats.errors}")
    print(f"Manifesto: {manifest_path}")


if __name__ == "__main__":
    main()
