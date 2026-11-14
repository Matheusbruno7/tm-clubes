"""Coleta os dados da CBTM e gera os arquivos públicos do Ranking de Clubes.

Uso:
    python scripts/atualizar.py                 # coleta tudo e recalcula
    python scripts/atualizar.py --sem-coleta    # recalcula a partir de dados/bruto/
    python scripts/atualizar.py --perfis 300    # nº de perfis amostrados para o modelo

Saídas (versionadas no repositório e lidas pelo tm-hub):
    dados/publico/ranking_clubes.json      ranking, Força do Clube e indicadores
    dados/publico/atletas_por_clube.json   atletas ativos de cada clube
    dados/publico/modelo_vitoria.json      coeficientes da regressão logística
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from tmclubes.cbtm import Cliente  # noqa: E402
from tmclubes.forca import ranking_de_clubes  # noqa: E402
from tmclubes.limpeza import ResolvedorUF, chave, uf_dos_clubes_pelos_atletas  # noqa: E402
from tmclubes.modelo import ajustar, jogos_do_perfil  # noqa: E402

BRUTO = RAIZ / "dados" / "bruto"
PUBLICO = RAIZ / "dados" / "publico"
CORRECOES = RAIZ / "dados" / "correcoes_uf.json"


def salvar(caminho: Path, dados, compacto: bool = False) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8") as f:
        if compacto:
            json.dump(dados, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(dados, f, ensure_ascii=False, indent=1)


def ler(caminho: Path):
    return json.loads(caminho.read_text(encoding="utf-8"))


def coletar(cli: Cliente, ano: int) -> None:
    print("clubes federados...", flush=True)
    salvar(BRUTO / "clubes_federados.json", cli.clubes_federados())
    for tipo in ("olimpico", "paralimpico", "rating"):
        cats = cli.opcoes(tipo)["categories"]
        linhas = []
        for i, c in enumerate(cats, 1):
            for it in cli.classificacao(tipo, c["id"], ano):
                it["cat"] = c["name"]
                it["tipo"] = tipo
                linhas.append(it)
            print(f"  {tipo}: {i}/{len(cats)} categorias, {len(linhas)} linhas", flush=True)
        salvar(BRUTO / f"{tipo}.json", linhas, compacto=True)
    coletar_rating_por_uf(cli, ano)


def coletar_rating_por_uf(cli: Cliente, ano: int) -> None:
    """Rating filtrado por estado: dá o estado de cada atleta e, pela maioria, de cada clube."""
    from tmclubes.cbtm import UFS

    cats = cli.opcoes("rating")["categories"]
    linhas = []
    for i, uf in enumerate(UFS, 1):
        for c in cats:
            for it in cli.classificacao("rating", c["id"], ano, regiao=uf):
                linhas.append({"name": it["name"], "club": it["club"], "uf": uf})
        print(f"  rating por estado: {i}/{len(UFS)} ({uf}), {len(linhas)} linhas", flush=True)
    salvar(BRUTO / "rating_por_uf.json", linhas, compacto=True)


def amostrar_perfis(cli: Cliente, rating: list[dict], ativos: set, n: int, semente: int = 7) -> list:
    """Amostra estratificada por classe de rating, só entre atletas ativos."""
    rnd = random.Random(semente)
    por_cat: dict[str, list[dict]] = {}
    for r in rating:
        if (r["name"], r["club"]) in ativos:
            por_cat.setdefault(r["cat"], []).append(r)
    escolhidos = []
    por_classe = max(1, n // max(1, len(por_cat)))
    for cat, linhas in sorted(por_cat.items()):
        escolhidos += rnd.sample(linhas, min(por_classe, len(linhas)))
    jogos = {}
    for i, r in enumerate(escolhidos, 1):
        try:
            perfil = cli.perfil(r["profile"])
        except Exception as e:  # um perfil com erro não derruba a coleta
            print(f"  perfil ignorado ({e})", flush=True)
            continue
        for g in perfil.get("games", []):
            # guarda só o necessário para o modelo, sem nomes de atletas
            jogos[g.get("JogoId")] = {k: g.get(k) for k in ("JogoId", "DataHorario", "EventoNome", "Pontos")}
        if i % 25 == 0:
            print(f"  perfis: {i}/{len(escolhidos)}, jogos: {len(jogos)}", flush=True)
    return list(jogos.values())


def jogos_para_modelo(jogos_brutos: list[dict]) -> list[tuple[float, int]]:
    # Cada jogo pode ter vindo do perfil de cada um dos dois atletas: o
    # dicionário por JogoId já deduplicou; aqui só decodificamos.
    return [(d, f) for _, d, f in jogos_do_perfil({"games": jogos_brutos})]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sem-coleta", action="store_true")
    ap.add_argument("--perfis", type=int, default=300)
    ap.add_argument("--reusar-jogos", action="store_true", help="reajusta o modelo com dados/bruto/jogos_perfis.json")
    ap.add_argument("--ano", type=int, default=dt.date.today().year)
    args = ap.parse_args()

    cli = Cliente()
    if not args.sem_coleta:
        coletar(cli, args.ano)

    federados = ler(BRUTO / "clubes_federados.json")
    olimpico = ler(BRUTO / "olimpico.json")
    paralimpico = ler(BRUTO / "paralimpico.json")
    rating = ler(BRUTO / "rating.json")
    correcoes = ler(CORRECOES) if CORRECOES.exists() else {}
    correcoes = {k: v for k, v in correcoes.items() if not k.startswith("_")}
    por_uf = ler(BRUTO / "rating_por_uf.json") if (BRUTO / "rating_por_uf.json").exists() else []
    uf_atleta = {(chave(r["name"]), chave(r["club"])): r["uf"] for r in por_uf}
    resolvedor = ResolvedorUF(federados, correcoes, uf_dos_clubes_pelos_atletas(por_uf))

    res = ranking_de_clubes(rating, olimpico + paralimpico, resolvedor, uf_atleta)
    agora = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    atletas_por_clube = {c["id"]: c.pop("atletas") for c in res["clubes"]}
    for f in res["federacoes"]["itens"]:
        atletas_por_clube[f["id"]] = f.pop("atletas")

    meta = {
        "gerado_em": agora,
        "ano_ranking": args.ano,
        "fonte": "CBTM – rankings e rating públicos (live.cbtm.org.br) e clubes federados (cbtm.org.br)",
        "aviso": "Os dados usam os números dos atletas do último ano (últimas 52 semanas).",
    }
    salvar(PUBLICO / "ranking_clubes.json", {"meta": meta, **res})
    salvar(PUBLICO / "atletas_por_clube.json", {"meta": meta, "clubes": atletas_por_clube}, compacto=True)

    jogos_brutos = None
    if args.reusar_jogos and (BRUTO / "jogos_perfis.json").exists():
        jogos_brutos = ler(BRUTO / "jogos_perfis.json")
    elif args.perfis > 0:
        ativos_ch = {(chave(r["name"]), chave(r["club"])) for r in olimpico + paralimpico}
        ativos = {(r["name"], r["club"]) for r in rating if (chave(r["name"]), chave(r["club"])) in ativos_ch}
        print("perfis para o modelo...", flush=True)
        jogos_brutos = amostrar_perfis(cli, rating, ativos, args.perfis)
        salvar(BRUTO / "jogos_perfis.json", jogos_brutos, compacto=True)
    if jogos_brutos:
        modelo = ajustar(jogos_para_modelo(jogos_brutos))
        salvar(PUBLICO / "modelo_vitoria.json", {"meta": {**meta, "perfis_amostrados": args.perfis}, **modelo})
        print(f"modelo: b0={modelo['b0']} b1={modelo['b1']} ({modelo['jogos']} jogos)")

    r = res["resumo"]
    print(
        f"ok: {r['clubes_no_ranking']} clubes, {r['atletas_ativos']} atletas ativos "
        f"({r['atletas_ativos_em_federacoes']} em federações), {r['clubes_sem_estado']} clubes sem estado"
    )


if __name__ == "__main__":
    main()
