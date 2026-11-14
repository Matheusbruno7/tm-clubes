# tm-clubes

**Ranking de Clubes** do tênis de mesa brasileiro: Força do Clube, comparação e
simulador de confrontos, a partir dos dados públicos da CBTM.

> Os dados usam os números dos atletas do último ano (últimas 52 semanas).

## O que este repositório faz
1. **Coleta** (semanal, via GitHub Actions) os dados públicos da CBTM:
   - rating de todos os atletas, inclusive filtrado por estado;
   - ranking olímpico e paralímpico do ano (últimas 52 semanas);
   - lista oficial de clubes federados (só nome e estado, **sem contatos**);
   - uma amostra de perfis de rating, para o modelo de vitória.
2. **Limpa** os dados:
   - **Atletas vinculados a federações** ficam em grupo separado e não entram no ranking.
   - **Estado do clube:** correção manual → lista de clubes federados → estado da
     maioria dos atletas do clube → sigla no nome → **"Clubes sem estado"**.
   - **Atleta ativo:** aparece em algum ranking olímpico ou paralímpico do ano
     (jogou evento oficial nos últimos 12 meses).
3. **Calcula** a Força do Clube (0–1000) e ajusta o modelo de regressão logística.
4. **Publica** os arquivos em `dados/publico/`, que o `tm-hub` exibe.

## Força do Clube
- **Índice do atleta (0–100):** 100 × rating ÷ média dos 10 melhores ratings ativos do mesmo sexo (teto 100).
- **Elite (50%):** média do índice dos 5 melhores atletas do clube.
- **Profundidade (30%):** média do índice do 6º ao 15º atleta.
- **Volume (20%):** nº de atletas ativos em escala logarítmica (teto 50).
- Força = 10 × (0,5·Elite + 0,3·Profundidade + 0,2·Volume).

## Modelo de vitória e simulador
Os pontos de cada jogo no perfil de rating, divididos pelo peso do evento,
revelam pela tabela oficial (Manual CBTM 2026, item 1.7.2.5.5) a faixa de
diferença de rating e se o favorito venceu. Com isso ajustamos
`P(favorito vence) = 1 / (1 + e^-(b0 + b1·Δ/100))`.

O simulador usa o **Mini Davis** da CBTM (Manual, item 1.9.2.10): Duplas, A×X
e B×Y, em melhor de 5 sets, e vence quem fizer 2. Há também a opção de 5 jogos simples.

## Corrigir o estado de um clube
Edite `dados/correcoes_uf.json`:
```json
{ "INTERCOLONIAL": "SP" }
```
Na próxima atualização, o clube sai de "Clubes sem estado".

## Rodar localmente
```bash
python -m unittest discover -s tests      # testes
python scripts/atualizar.py               # coleta tudo (≈20–30 min) e recalcula
python scripts/atualizar.py --sem-coleta --perfis 0   # só recalcula a partir de dados/bruto/
```
Só usa a biblioteca padrão do Python (3.10+).

## Arquivos publicados
| Arquivo | Conteúdo |
|---|---|
| `dados/publico/ranking_clubes.json` | ranking, Força do Clube, indicadores, federações, metodologia |
| `dados/publico/atletas_por_clube.json` | atletas ativos de cada clube (nome, sexo, classe, rating, índice) |
| `dados/publico/modelo_vitoria.json` | coeficientes e calibração da regressão logística |

## Observações
- A API do CBTM Live não é documentada e pode mudar. A coleta é feita uma vez
  por semana, com pausa entre as chamadas.
- Projeto independente, sem vínculo oficial com a CBTM. Em caso de diferença, vale o dado oficial.
