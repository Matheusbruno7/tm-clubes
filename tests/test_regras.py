import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tmclubes.forca import forca, ranking_de_clubes  # noqa: E402
from tmclubes.limpeza import SEM_ESTADO, ResolvedorUF, eh_federacao, nome_exibicao, uf_no_nome  # noqa: E402
from tmclubes.modelo import ajustar, decodificar, peso_evento, prob_vitoria  # noqa: E402
from tmclubes.simulador import cinco_simples, mini_davis  # noqa: E402


class Limpeza(unittest.TestCase):
    def test_federacao(self):
        self.assertTrue(eh_federacao("FEDERAÇÃO DE TÊNIS DE MESA DO ESTADO DE SÃO PAULO - SP"))
        self.assertTrue(eh_federacao("FEDERACAO GAUCHA DE TENIS DE MESA"))
        self.assertFalse(eh_federacao("ASSOCIAÇÃO JOINVILENSE DE TÊNIS DE MESA - SC"))

    def test_uf_no_nome(self):
        self.assertEqual(uf_no_nome("ADC- FME CRICIÚMA-SC"), "SC")
        self.assertEqual(uf_no_nome("NETO TT BAL. CAMBORIU SC"), "SC")
        self.assertIsNone(uf_no_nome("INTERCOLONIAL"))

    def test_resolvedor_ordem(self):
        r = ResolvedorUF([{"nome": "CLUBE X", "uf": "PR"}], {"INTERCOLONIAL": "SP"})
        self.assertEqual(r.resolver("Clube X"), ("PR", "federados"))
        self.assertEqual(r.resolver("INTERCOLONIAL"), ("SP", "correcao"))
        self.assertEqual(r.resolver("TIME Y - RS"), ("RS", "nome"))
        self.assertEqual(r.resolver("SEM PISTA"), (SEM_ESTADO, "sem_estado"))

    def test_nome_exibicao(self):
        self.assertEqual(nome_exibicao("CLUBE CONCORDIA - SC"), "CLUBE CONCORDIA")


class Modelo(unittest.TestCase):
    def test_pesos(self):
        self.assertEqual(peso_evento("Brasileirão de Inverno Interclubes"), 18)
        self.assertEqual(peso_evento("Seletiva Nacional Olímpica 2026"), 12)
        self.assertEqual(peso_evento("TMB - Copa Brasil Ouro - Caruaru"), 9)
        self.assertEqual(peso_evento("TMB ESTADUAL - 4ª ETAPA"), 3)

    def test_decodificar(self):
        self.assertEqual(decodificar(312, 12), (449.5, 0))  # 26 -> vitória inesperada, Δ 400–499
        self.assertEqual(decodificar(3, 3), (650.0, 1))  # esperada, Δ ≥ 750 -> faixa única ≥ 500
        self.assertEqual(decodificar(0, 18), (650.0, 1))  # derrota esperada, Δ ≥ 500
        self.assertEqual(decodificar(270, 9), (650.0, 0))  # zebra (30 × peso 9) com Δ ≥ 500
        self.assertEqual(decodificar(-24, 3), (12.0, 1))  # perdedor esperado 8 -> Δ 0–24
        self.assertEqual(decodificar(-27, 3), (12.0, 0))  # perdedor inesperado 9 -> Δ 0–24
        self.assertIsNone(decodificar(5, 3))

    def test_ajuste_recupera_tendencia(self):
        jogos = [(d, 1) for d in (12, 250, 450, 650) for _ in range(9)] + [(d, 0) for d in (12,) * 8 + (250,) * 3 + (450,)]
        m = ajustar(jogos)
        self.assertGreater(m["b1"], 0)
        self.assertGreater(prob_vitoria(2000, 1500, m), prob_vitoria(2000, 1900, m))
        self.assertAlmostEqual(prob_vitoria(1800, 1500, m) + prob_vitoria(1500, 1800, m), 1.0)


class Simulador(unittest.TestCase):
    M = {"b0": 0.2, "b1": 0.6}

    def test_mini_davis_simetrico(self):
        a = mini_davis([2000, 1800], [1500, 1400], self.M)["prob_a"]
        b = mini_davis([1500, 1400], [2000, 1800], self.M)["prob_a"]
        self.assertAlmostEqual(a + b, 1.0, places=3)
        self.assertGreater(a, 0.5)

    def test_cinco_simples(self):
        r = cinco_simples([1800, 1700, 1600], [1800, 1700, 1600], self.M)
        self.assertAlmostEqual(r["prob_a"], 0.5, places=3)


class Forca(unittest.TestCase):
    def test_escala(self):
        self.assertEqual(forca([100] * 15 + [100] * 35)["forca"], 1000.0)
        self.assertEqual(forca([])["forca"], 0.0)

    def test_ranking_regras(self):
        rating = [
            {"name": "ANA", "club": "CLUBE A - SC", "points": "2000 Pts", "cat": "Rating B Feminino"},
            {"name": "BIA", "club": "CLUBE A - SC", "points": "800 Pts", "cat": "Rating E Feminino"},
            {"name": "CAIO", "club": "FEDERAÇÃO X - PR", "points": "3000 Pts", "cat": "Rating B Masculino"},
            {"name": "DANI", "club": "INTERCOLONIAL", "points": "1000 Pts", "cat": "Rating G Masculino"},
            {"name": "EDU", "club": "CLUBE A - SC", "points": "3500 Pts", "cat": "Rating A Masculino"},
        ]
        rk = lambda n, c: {"name": n, "club": c, "position": "Rk 3", "points": "100 Pts", "cat": "ABSOLUTO A MAS", "tipo": "olimpico"}
        rankings = [rk("ANA", "CLUBE A - SC"), rk("CAIO", "FEDERAÇÃO X - PR"), rk("DANI", "INTERCOLONIAL")]
        res = ranking_de_clubes(rating, rankings, ResolvedorUF([]))
        nomes = {c["nome_cbtm"]: c for c in res["clubes"]}
        self.assertIn("CLUBE A - SC", nomes)
        self.assertEqual(nomes["CLUBE A - SC"]["atletas_ativos"], 1)  # BIA e EDU inativos
        self.assertEqual(nomes["INTERCOLONIAL"]["uf"], SEM_ESTADO)
        self.assertNotIn("FEDERAÇÃO X - PR", nomes)
        self.assertEqual(res["federacoes"]["itens"][0]["atletas_ativos"], 1)

    def test_federacao_ativo_por_nome_no_mesmo_estado(self):
        rating = [
            {"name": "FABI", "club": "FEDERAÇÃO Y - PR", "points": "900 Pts", "cat": "Rating F Feminino"},
            {"name": "GABI", "club": "FEDERAÇÃO Y - PR", "points": "900 Pts", "cat": "Rating F Feminino"},
        ]
        rk = lambda n, c: {"name": n, "club": c, "position": "Rk 9", "points": "50 Pts", "cat": "SUB-15 FEM", "tipo": "olimpico"}
        # FABI jogou por um clube do PR (conta); GABI jogou por um clube de SP (homônimo de outro estado, não conta)
        res = ranking_de_clubes(rating, [rk("FABI", "CLUBE Z - PR"), rk("GABI", "CLUBE W - SP")], ResolvedorUF([]))
        fed = res["federacoes"]["itens"][0]
        self.assertEqual(fed["atletas_ativos"], 1)
        self.assertEqual(res["clubes"], [])

    def test_federacao_ativo_com_clube_em_branco_no_ranking(self):
        rating = [{"name": "HELO", "club": "FEDERAÇÃO Y - PR", "points": "900 Pts", "cat": "Rating F Feminino"}]
        rk = {"name": "HELO", "club": "", "position": "Rk 9", "points": "50 Pts", "cat": "SUB-15 FEM", "tipo": "olimpico"}
        res = ranking_de_clubes(rating, [rk], ResolvedorUF([]))
        self.assertEqual(res["federacoes"]["itens"][0]["atletas_ativos"], 1)


if __name__ == "__main__":
    unittest.main()
