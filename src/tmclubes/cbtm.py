"""Cliente das fontes públicas da CBTM.

Fontes usadas (todas públicas, sem login):
- https://live.cbtm.org.br/api/local/classificacoes/...  ranking olímpico, paralímpico e rating
- https://cbtm.org.br/api/clubes?uf=XX                   clubes federados por estado

A API do CBTM Live não é documentada e pode mudar sem aviso. As chamadas são
feitas com pausa entre elas para não sobrecarregar o servidor da CBTM.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

LIVE = "https://live.cbtm.org.br/api/local/classificacoes/"
SITE = "https://cbtm.org.br/api/"
USER_AGENT = "tm-clubes/0.1 (coleta semanal de dados publicos)"
UFS = (
    "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO".split()
)
TIPOS = ("olimpico", "paralimpico", "rating")
TAMANHO_PAGINA = 1000  # maior valor aceito pela API


class Cliente:
    def __init__(self, pausa: float = 0.4, tentativas: int = 4):
        self.pausa = pausa
        self.tentativas = tentativas

    def _get(self, url: str):
        erro = None
        for i in range(self.tentativas):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=90) as r:
                    dados = json.load(r)
                time.sleep(self.pausa)
                return dados
            except urllib.error.HTTPError as e:
                if e.code == 400:  # filtro inválido: não adianta repetir
                    raise
                erro = e
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
                erro = e
            time.sleep(2 ** i)
        raise RuntimeError(f"falha ao baixar {url}: {erro}")

    # ---- CBTM Live -------------------------------------------------------
    def opcoes(self, tipo: str) -> dict:
        return self._get(f"{LIVE}{tipo}/opcoes")

    def classificacao(self, tipo: str, categoria: str, ano: int, regiao: str = "Brasil") -> list[dict]:
        """Todas as linhas de uma categoria (percorre as páginas)."""
        itens, pagina = [], 1
        while True:
            q = urllib.parse.urlencode(
                {"categoria": categoria, "ano": ano, "regiao": regiao, "pagina": pagina, "tamanho": TAMANHO_PAGINA}
            )
            r = self._get(f"{LIVE}{tipo}?{q}")
            itens.extend(r.get("items", []))
            if pagina >= (r.get("pages") or 1):
                return itens
            pagina += 1

    def perfil(self, caminho_perfil: str) -> dict:
        """caminho_perfil é o campo 'profile' de uma linha, ex.: /rating/atletas/<token>."""
        partes = caminho_perfil.strip("/").split("/")
        token = partes[-1]
        tipo = "rating" if partes[0] == "rating" else partes[1]
        return self._get(f"{LIVE}{tipo}/perfil/{token}")

    # ---- Site institucional ---------------------------------------------
    def clubes_federados(self) -> list[dict]:
        clubes = []
        for uf in UFS:
            for c in self._get(f"{SITE}clubes?uf={uf}"):
                # Guarda só o necessário. Contatos (e-mail, telefone) NÃO são coletados.
                clubes.append({"id": c.get("id"), "nome": c.get("nome"), "uf": c.get("uf") or uf})
        return clubes
