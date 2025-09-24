"""Infraestrutura simples para armazenar segredos de forma volátil."""

from __future__ import annotations

from threading import RLock
from typing import Optional


class _RuntimeCredentialsStore:
    """Armazena segredos efêmeros na memória do processo."""

    _GESTAO_BASE_PASSWORD_KEY = "gestao_base_password"

    def __init__(self) -> None:
        self._lock = RLock()
        self._secrets: dict[str, str] = {}

    def set_secret(self, key: str, value: Optional[str]) -> None:
        """Define ou limpa o valor associado a ``key``."""

        with self._lock:
            if value is None or value == "":
                self._secrets.pop(key, None)
            else:
                self._secrets[key] = value

    def get_secret(self, key: str) -> Optional[str]:
        """Recupera o valor armazenado para ``key`` se houver."""

        with self._lock:
            return self._secrets.get(key)

    def clear_all(self) -> None:
        """Remove todos os segredos armazenados."""

        with self._lock:
            self._secrets.clear()

    # -- atalhos específicos para Gestão da Base ---------------------------------

    def set_gestao_base_password(self, password: Optional[str]) -> None:
        self.set_secret(self._GESTAO_BASE_PASSWORD_KEY, password)

    def get_gestao_base_password(self) -> Optional[str]:
        return self.get_secret(self._GESTAO_BASE_PASSWORD_KEY)

    def clear_gestao_base_password(self) -> None:
        self.set_secret(self._GESTAO_BASE_PASSWORD_KEY, None)


_STORE = _RuntimeCredentialsStore()


def set_gestao_base_password(password: Optional[str]) -> None:
    """Guarda a senha da Gestão da Base em memória."""

    _STORE.set_gestao_base_password(password)


def get_gestao_base_password() -> Optional[str]:
    """Retorna a senha atualmente armazenada para Gestão da Base."""

    return _STORE.get_gestao_base_password()


def clear_gestao_base_password() -> None:
    """Remove a senha armazenada da Gestão da Base."""

    _STORE.clear_gestao_base_password()


def clear_all_credentials() -> None:
    """Remove todos os segredos voláteis."""

    _STORE.clear_all()
