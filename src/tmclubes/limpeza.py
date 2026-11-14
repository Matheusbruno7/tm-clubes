"""Regras de limpeza dos clubes.

1. Atletas vinculados a federações: quando o "clube" do atleta é uma federação
   estadual, ele vai para o grupo "Atletas vinculados a federações", e não
   entra no Ranking de Clubes.
2. Estado do clube: primeiro cruza com a lista oficial de clubes federados da
   CBTM; se não achar, usa a sigla do estado no fim do nome do clube
   (ex.: "...-SC"); se ainda assim não achar, o clube vai para
   "Clubes sem estado" até ser corrigido manualmente em dados/correcoes_uf.json.
"""

from __future__ import annotations

import re
import unicodedata

UFS = set("AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO".split())
SEM_ESTADO = "Clubes sem estado"
GRUPO_FEDERACOES = "Atletas vinculados a federações"

_RE_FEDERACAO = re.compile(r"^\s*(FEDERA[CÇ][AÃ]O|FED\.|FEDERACAO)\b", re.I)
_RE_UF_FINAL = re.compile(r"(?:[-–/,(]|\s)\s*([A-Z]{2})\s*\)?\s*$")


def sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def chave(nome: str) -> str:
    """Forma normalizada para comparar nomes de clube."""
    s = sem_acento(nome or "").upper()
    s = re.sub(r"[^A-Z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def eh_federacao(nome_clube: str) -> bool:
    return bool(_RE_FEDERACAO.match(sem_acento(nome_clube or "")))


def uf_no_nome(nome_clube: str) -> str | None:
    m = _RE_UF_FINAL.search(sem_acento(nome_clube or "").upper())
    if m and m.group(1) in UFS:
        return m.group(1)
    return None


class ResolvedorUF:
    """Ordem: correção manual > lista de clubes federados > estado dos atletas
    do clube no rating por estado da CBTM > sigla no nome > sem estado."""

    def __init__(
        self,
        clubes_federados: list[dict],
        correcoes: dict[str, str] | None = None,
        uf_dos_atletas: dict[str, str] | None = None,
    ):
        self.oficial = {chave(c["nome"]): c["uf"] for c in clubes_federados if c.get("nome") and c.get("uf")}
        self.correcoes = {chave(k): v for k, v in (correcoes or {}).items()}
        self.atletas = {chave(k): v for k, v in (uf_dos_atletas or {}).items()}

    def resolver(self, nome_clube: str) -> tuple[str, str]:
        """Devolve (uf, origem). origem: correcao | federados | atletas | nome | sem_estado."""
        k = chave(nome_clube)
        if k in self.correcoes:
            return self.correcoes[k], "correcao"
        if k in self.oficial:
            return self.oficial[k], "federados"
        if k in self.atletas:
            return self.atletas[k], "atletas"
        uf = uf_no_nome(nome_clube)
        if uf:
            return uf, "nome"
        return SEM_ESTADO, "sem_estado"


def uf_dos_clubes_pelos_atletas(linhas_uf: list[dict], minimo: float = 0.6) -> dict[str, str]:
    """linhas_uf: linhas do rating filtrado por estado (campo 'uf').
    O estado do clube é o estado da maioria dos seus atletas (pelo menos 60%)."""
    from collections import Counter, defaultdict

    cont: dict[str, Counter] = defaultdict(Counter)
    for r in linhas_uf:
        cont[r["club"]][r["uf"]] += 1
    saida = {}
    for clube, c in cont.items():
        uf, n = c.most_common(1)[0]
        if n / sum(c.values()) >= minimo:
            saida[clube] = uf
    return saida


def nome_exibicao(nome_clube: str) -> str:
    """Nome do clube sem a sigla do estado no fim, para exibir."""
    s = re.sub(r"\s*[-–/]\s*[A-Z]{2}\s*$", "", (nome_clube or "").strip())
    return re.sub(r"\s+", " ", s).strip(" -")


def pontos(texto: str) -> int:
    """'4888 Pts' -> 4888"""
    return int(re.sub(r"\D", "", texto or "0") or 0)


def posicao(texto: str) -> int:
    """'Rk 12' -> 12"""
    return int(re.sub(r"\D", "", texto or "0") or 0)


def sexo_da_categoria(nome_categoria: str) -> str:
    n = sem_acento(nome_categoria).upper()
    if "FEM" in n:
        return "F"
    if "MAS" in n:
        return "M"
    return "X"


def classe_rating(nome_categoria: str) -> str:
    """'Rating B Masculino' -> 'B'"""
    m = re.search(r"Rating\s+([A-Z])\b", nome_categoria)
    return m.group(1) if m else "?"
