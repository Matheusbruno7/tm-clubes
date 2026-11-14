"""Ranking de Clubes e Força do Clube.

Só contam os atletas ATIVOS: quem aparece em algum ranking olímpico ou
paralímpico do ano corrente da CBTM, que soma as últimas 52 semanas, ou seja,
quem disputou evento oficial nos últimos 12 meses.

Índice do atleta (0–100): percentil do rating do atleta entre os atletas
ativos do mesmo sexo. Usar percentil por sexo deixa masculino e feminino na
mesma escala, porque as faixas de rating são diferentes para cada sexo.

Força do Clube (0–1000):
    Elite        50%  média do índice dos 5 melhores atletas (vaga vazia = 0)
    Profundidade 30%  média do índice do 6º ao 15º atleta (vaga vazia = 0)
    Volume       20%  nº de atletas ativos em escala logarítmica, teto em 50
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from statistics import mean, median

from .limpeza import (
    GRUPO_FEDERACOES,
    ResolvedorUF,
    chave,
    classe_rating,
    eh_federacao,
    nome_exibicao,
    pontos,
    posicao,
    sexo_da_categoria,
)

PESOS = {"elite": 0.5, "profundidade": 0.3, "volume": 0.2}
N_ELITE = 5
N_PROFUNDIDADE = 10  # do 6º ao 15º
TETO_VOLUME = 50
TOP_RATING = 100  # "atletas no top 100 do rating nacional" (por sexo)
N_REFERENCIA = 10  # referência do índice: média dos 10 melhores ratings ativos do sexo


def faixa_etaria(categoria: str) -> str | None:
    c = categoria.upper()
    if c.startswith("SUB-"):
        return "Base (Sub)"
    if c.startswith("MASTER"):
        return "Master"
    if c.startswith("ADULTO"):
        return "Adulto"
    if c.startswith("ABSOLUTO"):
        return "Absoluto"
    return None


def slug(texto: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", chave(texto).lower()).strip("-")


def montar_atletas(
    rating: list[dict],
    rankings: list[dict],
    resolvedor: ResolvedorUF | None = None,
    uf_atleta: dict[tuple, str] | None = None,
) -> list[dict]:
    """rating: linhas do rating (com 'cat'); rankings: linhas dos rankings (com 'tipo' e 'cat').

    Ligação rating -> ranking: pelo nome + clube. Para atletas cujo vínculo
    atual no rating é uma federação, o ranking mostra o clube pelo qual
    disputaram os eventos. Nesse caso a ligação é feita pelo nome, desde que
    o nome seja único no rating e o clube do ranking seja do mesmo estado.
    """
    por_chave: dict[tuple, list[dict]] = defaultdict(list)
    por_nome: dict[str, list[dict]] = defaultdict(list)
    for r in rankings:
        por_chave[(chave(r["name"]), chave(r["club"]))].append(r)
        por_nome[chave(r["name"])].append(r)
    nomes_rating = Counter(chave(r["name"]) for r in rating)
    nomes_federacao = Counter(chave(r["name"]) for r in rating if eh_federacao(r["club"]))
    uf_atleta = uf_atleta or {}

    atletas = []
    for r in rating:
        k = (chave(r["name"]), chave(r["club"]))
        rk = por_chave.get(k, [])
        if not rk and eh_federacao(r["club"]):
            # No ranking, o atleta ligado a federação aparece com o clube em branco.
            if nomes_federacao[k[0]] == 1:
                rk = [x for x in por_nome.get(k[0], []) if not (x.get("club") or "").strip()]
            # Ou com o clube pelo qual jogou: só aceita se o nome for único e o estado bater.
            if not rk and resolvedor and nomes_rating[k[0]] == 1:
                uf = uf_atleta.get(k) or resolvedor.resolver(r["club"])[0]
                rk = [x for x in por_nome.get(k[0], []) if (x.get("club") or "").strip() and resolvedor.resolver(x["club"])[0] == uf]
        atletas.append(
            {
                "nome": r["name"],
                "clube": r["club"],
                "sexo": sexo_da_categoria(r["cat"]),
                "classe": classe_rating(r["cat"]),
                "rating": pontos(r["points"]),
                "ativo": bool(rk),
                "paralimpico": any(x["tipo"] == "paralimpico" for x in rk),
                "rankings": [
                    {"tipo": x["tipo"], "categoria": x["cat"], "posicao": posicao(x["position"]), "pontos": pontos(x["points"])}
                    for x in rk
                ],
            }
        )
    return atletas


def indices_por_sexo(atletas: list[dict]) -> dict:
    """Preenche 'indice' (0–100) nos atletas ativos.

    índice = 100 × rating / referência do sexo, com teto em 100. A referência
    é a média do rating dos 10 melhores atletas ativos do sexo. A escala é
    linear no rating, então diferenças no topo continuam visíveis.
    """
    refs = {}
    for sexo in ("M", "F"):
        grupo = sorted((a["rating"] for a in atletas if a["ativo"] and a["sexo"] == sexo), reverse=True)
        ref = mean(grupo[:N_REFERENCIA]) if grupo else 1
        refs[sexo] = round(ref)
        for a in atletas:
            if a["ativo"] and a["sexo"] == sexo:
                a["indice"] = round(min(100.0, 100.0 * a["rating"] / ref), 2)
    return refs


def forca(indices: list[float]) -> dict:
    ordem = sorted(indices, reverse=True)
    elite = sum(ordem[:N_ELITE]) / N_ELITE
    prof = sum(ordem[N_ELITE : N_ELITE + N_PROFUNDIDADE]) / N_PROFUNDIDADE
    vol = min(1.0, math.log1p(len(ordem)) / math.log1p(TETO_VOLUME)) * 100
    total = 10 * (PESOS["elite"] * elite + PESOS["profundidade"] * prof + PESOS["volume"] * vol)
    return {
        "forca": round(total, 1),
        "elite": round(elite, 1),
        "profundidade": round(prof, 1),
        "volume": round(vol, 1),
    }


def absoluto(atleta: dict) -> dict | None:
    """Categoria do Absoluto mais alta em que o atleta aparece (A é a mais forte) e a posição nela."""
    abs_ = [x for x in atleta["rankings"] if x["tipo"] == "olimpico" and x["categoria"].upper().startswith("ABSOLUTO")]
    if not abs_:
        return None
    melhor = min(abs_, key=lambda x: (x["categoria"].split()[1] if len(x["categoria"].split()) > 1 else "Z", x["posicao"] or 9999))
    letra = melhor["categoria"].split()[1] if len(melhor["categoria"].split()) > 1 else "?"
    return {"categoria": letra, "posicao": melhor["posicao"]}


def posicoes_no_rating(atletas: list[dict]) -> None:
    """Posição de cada atleta no rating nacional do seu sexo (todos os atletas do rating)."""
    for sexo in ("M", "F"):
        grupo = sorted((a for a in atletas if a["sexo"] == sexo), key=lambda a: -a["rating"])
        anterior, pos = None, 0
        for i, a in enumerate(grupo, 1):
            if a["rating"] != anterior:
                pos, anterior = i, a["rating"]
            a["posicao_rating"] = pos


def resumo_grupo(nome: str, uf: str, origem_uf: str, membros: list[dict], ordem_classes: dict) -> dict:
    ativos = [a for a in membros if a["ativo"]]
    masc = [a for a in ativos if a["sexo"] == "M"]
    fem = [a for a in ativos if a["sexo"] == "F"]

    faixas = Counter()
    for a in ativos:
        for f in {faixa_etaria(x["categoria"]) for x in a["rankings"] if x["tipo"] == "olimpico"} - {None}:
            faixas[f] += 1

    # Mesma régua para todos: posição no rating nacional (por sexo), e não a
    # melhor posição em qualquer categoria (2º no Absoluto B ≠ 2º no Absoluto A).
    top100_rating = sum(1 for a in ativos if a.get("posicao_rating") and a["posicao_rating"] <= TOP_RATING)
    melhores = sorted(ativos, key=lambda a: a.get("indice", 0), reverse=True)

    def dist(lista, sexo):
        c = Counter(a["classe"] for a in lista)
        return {k: c.get(k, 0) for k in ordem_classes[sexo]}

    return {
        "nome": nome_exibicao(nome) or nome,
        "nome_cbtm": nome,
        "uf": uf,
        "origem_uf": origem_uf,
        "atletas_ativos": len(ativos),
        "atletas_masculino": len(masc),
        "atletas_feminino": len(fem),
        "atletas_paralimpicos": sum(1 for a in ativos if a["paralimpico"]),
        "atletas_cadastrados": len(membros),
        "top100_rating": top100_rating,
        **forca([a.get("indice", 0) for a in ativos]),
        "forca_masculino": forca([a.get("indice", 0) for a in masc])["forca"] if masc else 0,
        "forca_feminino": forca([a.get("indice", 0) for a in fem])["forca"] if fem else 0,
        "rating_medio_masculino": round(mean(a["rating"] for a in masc)) if masc else None,
        "rating_mediano_masculino": round(median(a["rating"] for a in masc)) if masc else None,
        "rating_medio_feminino": round(mean(a["rating"] for a in fem)) if fem else None,
        "rating_mediano_feminino": round(median(a["rating"] for a in fem)) if fem else None,
        "classes_masculino": dist(masc, "M"),
        "classes_feminino": dist(fem, "F"),
        "faixas_etarias": dict(faixas),
        "atletas": [
            {
                "nome": a["nome"],
                "sexo": a["sexo"],
                "rating": a["rating"],
                "classe": a["classe"],
                "indice": a.get("indice", 0),
                "paralimpico": a["paralimpico"],
                "posicao_rating": a.get("posicao_rating"),
                "absoluto": absoluto(a),
            }
            for a in melhores
        ],
    }


def ranking_de_clubes(
    rating: list[dict],
    rankings: list[dict],
    resolvedor: ResolvedorUF,
    uf_atleta: dict[tuple, str] | None = None,
    min_ativos: int = 1,
) -> dict:
    atletas = montar_atletas(rating, rankings, resolvedor, uf_atleta)
    referencias = indices_por_sexo(atletas)
    posicoes_no_rating(atletas)

    ordem_classes = {
        "M": list("ABCDEFGHIJLMNO"),
        "F": list("ABCDEFGHIJ"),
    }

    por_clube: dict[str, list[dict]] = defaultdict(list)
    for a in atletas:
        por_clube[a["clube"]].append(a)

    clubes, federacoes = [], []
    for nome, membros in por_clube.items():
        if not any(a["ativo"] for a in membros):
            continue
        if eh_federacao(nome):
            uf, origem = resolvedor.resolver(nome)
            federacoes.append(resumo_grupo(nome, uf, origem, membros, ordem_classes))
            continue
        uf, origem = resolvedor.resolver(nome)
        g = resumo_grupo(nome, uf, origem, membros, ordem_classes)
        if g["atletas_ativos"] >= min_ativos:
            clubes.append(g)

    clubes.sort(key=lambda c: (-c["forca"], -c["atletas_ativos"], c["nome"]))
    por_uf: dict[str, int] = defaultdict(int)
    for i, c in enumerate(clubes, 1):
        c["posicao_brasil"] = i
        por_uf[c["uf"]] += 1
        c["posicao_estado"] = por_uf[c["uf"]]
        c["id"] = slug(c["nome_cbtm"])
    federacoes.sort(key=lambda c: -c["atletas_ativos"])
    for f in federacoes:
        f["id"] = slug(f["nome_cbtm"])

    ativos = [a for a in atletas if a["ativo"]]
    return {
        "clubes": clubes,
        "federacoes": {"titulo": GRUPO_FEDERACOES, "itens": federacoes},
        "resumo": {
            "atletas_no_rating": len(atletas),
            "atletas_ativos": len(ativos),
            "atletas_ativos_em_clubes": sum(c["atletas_ativos"] for c in clubes),
            "atletas_ativos_em_federacoes": sum(f["atletas_ativos"] for f in federacoes),
            "clubes_no_ranking": len(clubes),
            "clubes_sem_estado": sum(1 for c in clubes if c["origem_uf"] == "sem_estado"),
            "origem_uf": dict(Counter(c["origem_uf"] for c in clubes)),
        },
        "metodologia": {
            "ativo": "Atleta que aparece em algum ranking olímpico ou paralímpico do ano corrente da CBTM (últimas 52 semanas).",
            "indice": "100 × rating do atleta ÷ média do rating dos 10 melhores atletas ativos do mesmo sexo, com teto em 100.",
            "referencias": {"masculino": referencias.get("M"), "feminino": referencias.get("F")},
            "pesos": PESOS,
            "n_elite": N_ELITE,
            "n_profundidade": N_PROFUNDIDADE,
            "teto_volume": TETO_VOLUME,
        },
    }
