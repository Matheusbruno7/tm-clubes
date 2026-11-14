"""Simulador de confronto entre clubes.

Formato padrão: o "Mini Davis" das competições por equipes da CBTM
(Manual, item 1.9.2.10): até 3 jogos, todos em melhor de 5 sets, e vence a
equipe que chegar primeiro a 2 vitórias. A ordem é:
    1º Duplas (AB x XY)   2º A x X   3º B x Y

A força de uma dupla é aproximada pela média do rating dos dois atletas.
O cálculo é exato: soma as probabilidades de todas as combinações de resultado.
"""

from __future__ import annotations

from itertools import product

from .modelo import prob_vitoria


def _prob_maioria(probs: list[float], vitorias_necessarias: int) -> float:
    total = 0.0
    for resultado in product((0, 1), repeat=len(probs)):
        if sum(resultado) >= vitorias_necessarias:
            p = 1.0
            for venceu, pj in zip(resultado, probs):
                p *= pj if venceu else 1 - pj
            total += p
    return total


def mini_davis(equipe_a: list[float], equipe_b: list[float], modelo: dict) -> dict:
    """equipe_a/equipe_b: ratings [A, B] e [X, Y], do melhor para o pior."""
    a1, a2 = equipe_a[:2]
    b1, b2 = equipe_b[:2]
    jogos = [
        ("Duplas", prob_vitoria((a1 + a2) / 2, (b1 + b2) / 2, modelo)),
        ("A x X", prob_vitoria(a1, b1, modelo)),
        ("B x Y", prob_vitoria(a2, b2, modelo)),
    ]
    p = _prob_maioria([pj for _, pj in jogos], 2)
    return {"formato": "Mini Davis (CBTM)", "prob_a": round(p, 4), "jogos": [{"jogo": n, "prob_a": round(pj, 4)} for n, pj in jogos]}


def cinco_simples(equipe_a: list[float], equipe_b: list[float], modelo: dict) -> dict:
    """Equipes de 3: A-X, B-Y, C-Z, A-Y, B-X; vence quem fizer 3 pontos."""
    a, b, c = equipe_a[:3]
    x, y, z = equipe_b[:3]
    jogos = [("A x X", a, x), ("B x Y", b, y), ("C x Z", c, z), ("A x Y", a, y), ("B x X", b, x)]
    probs = [prob_vitoria(r1, r2, modelo) for _, r1, r2 in jogos]
    p = _prob_maioria(probs, 3)
    return {"formato": "5 jogos simples", "prob_a": round(p, 4), "jogos": [{"jogo": n, "prob_a": round(pj, 4)} for (n, _, _), pj in zip(jogos, probs)]}
