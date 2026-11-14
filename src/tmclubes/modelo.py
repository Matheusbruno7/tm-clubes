"""Modelo de probabilidade de vitória (regressão logística).

O perfil de rating de cada atleta na CBTM lista os jogos com os pontos
ganhos ou perdidos. Pela tabela oficial (Manual da CBTM, item 1.7.2.5.5), os
pontos divididos pelo peso do evento revelam:
  - se o atleta de maior rating (o favorito) venceu ou perdeu;
  - a faixa de diferença de rating (Δ) entre os dois.

Com esses jogos, ajustamos:
    P(favorito vence) = 1 / (1 + exp(-(b0 + b1 * Δ/100)))

O modelo é usado pelo simulador de confronto entre clubes.
"""

from __future__ import annotations

import math
import re

# (Δ mínimo, Δ máximo, pontos do vencedor, pontos do perdedor) – tabela básica
ESPERADAS = [
    (750, None, 1, 0), (500, 749, 2, 0), (400, 499, 3, 1), (300, 399, 4, 2), (200, 299, 5, 3),
    (150, 199, 6, 4), (100, 149, 7, 5), (50, 99, 8, 6), (25, 49, 9, 7), (0, 24, 10, 8),
]
INESPERADAS = [
    (500, None, 30, 22), (400, 499, 26, 20), (300, 399, 23, 18), (200, 299, 20, 16), (150, 199, 18, 14),
    (100, 149, 16, 12), (50, 99, 14, 11), (25, 49, 12, 10), (0, 24, 11, 9),
]
PESOS_EVENTO = [  # ordem importa: o primeiro que casar vale
    (r"BRASILEIR(A|Ã)O", 18),  # "Liga Nipo Brasileira" é regional
    (r"COPA BRASIL.*OURO|OURO.*COPA BRASIL", 9), (r"COPA BRASIL.*PRATA|PRATA.*COPA BRASIL", 6),
    (r"ESTADUAL|PAULIST|CATARINENSE|GAUCHO|MINEIRO|CARIOCA|PARANAENSE|DISTRITAL", 3),  # inclui "SÉRIE OURO/PRATA"
    (r"SELETIVA", 12),
    (r"REGIONAL|LIGA", 1),
]


DELTA_500_MAIS = 650.0  # a tabela não separa 500–749 de 750+ nas zebras: tudo ≥ 500 vira uma faixa só


def _meio(lo: int, hi: int | None) -> float:
    if lo >= 500:
        return DELTA_500_MAIS
    return (lo + hi) / 2


def peso_evento(nome_evento: str) -> int | None:
    n = nome_evento.upper()
    for padrao, peso in PESOS_EVENTO:
        if re.search(padrao, n):
            return peso
    return None


def decodificar(pontos_jogo: int, peso: int) -> tuple[float, int] | None:
    """Devolve (Δ estimado, favorito_venceu) ou None se não bater com a tabela."""
    if pontos_jogo % peso:
        return None
    b = pontos_jogo // peso
    if b > 0:  # o atleta venceu
        for lo, hi, v, _ in ESPERADAS:
            if b == v:
                return _meio(lo, hi), 1
        for lo, hi, v, _ in INESPERADAS:
            if b == v:
                return _meio(lo, hi), 0
        return None
    perda = -b
    if perda == 0:
        return DELTA_500_MAIS, 1  # derrota esperada com Δ ≥ 500 (as duas faixas valem 0)
    for lo, hi, _, p in ESPERADAS:
        if perda == p:
            return _meio(lo, hi), 1
    for lo, hi, _, p in INESPERADAS:
        if perda == p:
            return _meio(lo, hi), 0
    return None


def jogos_do_perfil(perfil: dict, desde: str = "2025-01-01") -> list[tuple[int, float, int]]:
    """Extrai (JogoId, Δ, favorito_venceu) dos jogos de um perfil de rating."""
    saida = []
    for g in perfil.get("games", []):
        if str(g.get("DataHorario", "")) < desde:
            continue
        peso = peso_evento(g.get("EventoNome", ""))
        if not peso or g.get("Pontos") is None:
            continue
        d = decodificar(int(g["Pontos"]), peso)
        if d:
            saida.append((g.get("JogoId"), d[0], d[1]))
    return saida


def sigmoide(z: float) -> float:
    return 1 / (1 + math.exp(-z))


def ajustar(jogos: list[tuple[float, int]], iteracoes: int = 50) -> dict:
    """Regressão logística (Newton–Raphson) de favorito_venceu sobre Δ/100."""
    xs = [d / 100 for d, _ in jogos]
    ys = [y for _, y in jogos]
    b0 = b1 = 0.0
    for _ in range(iteracoes):
        g0 = g1 = h00 = h01 = h11 = 0.0
        for x, y in zip(xs, ys):
            p = sigmoide(b0 + b1 * x)
            w = p * (1 - p)
            g0 += y - p
            g1 += (y - p) * x
            h00 += w
            h01 += w * x
            h11 += w * x * x
        det = h00 * h11 - h01 * h01
        if det == 0:
            break
        d0 = (h11 * g0 - h01 * g1) / det
        d1 = (-h01 * g0 + h00 * g1) / det
        b0, b1 = b0 + d0, b1 + d1
        if abs(d0) < 1e-9 and abs(d1) < 1e-9:
            break

    # calibração por faixa: taxa observada x prevista
    faixas: dict[float, list[int]] = {}
    for d, y in jogos:
        faixas.setdefault(d, []).append(y)
    calibracao = [
        {
            "delta": d,
            "jogos": len(v),
            "observado": round(sum(v) / len(v), 3),
            "previsto": round(sigmoide(b0 + b1 * d / 100), 3),
        }
        for d, v in sorted(faixas.items())
    ]
    return {"b0": round(b0, 5), "b1": round(b1, 5), "jogos": len(jogos), "calibracao": calibracao}


def prob_vitoria(rating_a: float, rating_b: float, modelo: dict) -> float:
    """Probabilidade de A vencer B."""
    delta = abs(rating_a - rating_b) / 100
    p_fav = sigmoide(modelo["b0"] + modelo["b1"] * delta)
    if rating_a == rating_b:
        return 0.5
    return p_fav if rating_a > rating_b else 1 - p_fav
