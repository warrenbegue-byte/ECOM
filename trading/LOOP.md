# 🔁 Loop Engineering avec Claude (reel @raycfu)

L'idée du reel : une IA propose une hypothèse, la code, la backteste, lit les résultats, et recommence.
Le danger : à force d'itérer sur les mêmes données, l'IA (ou vous) finit par **sur-apprendre**.
Cette boucle impose donc un juge impartial : `python run.py optimize`, qui ne valide que ce qui tient
sur des données jamais vues.

## Prompt à donner à Claude (Claude Code, dans ce dossier)

```
Tu es mon chercheur quant. Dans le dossier trading/ :
1. Lis tradebot/strategies.py et propose UNE hypothèse de stratégie simple (≤ 4 paramètres),
   avec une justification économique (pourquoi ce marché devrait se comporter ainsi).
2. Implémente-la comme nouvelle classe dans strategies.py (même interface reset/prepare/signal),
   ajoute-la à STRATEGIES et une grille dans GRIDS de run.py (≤ 30 combinaisons).
3. Lance : python run.py optimize <nom> --csv <mes_données> --spread <spread réel>
4. Analyse le tableau walk-forward. Si le verdict est REJETÉ, explique pourquoi et propose
   une NOUVELLE hypothèse (ne pas juste élargir la grille). Si ROBUSTE, lance un backtest complet
   avec les règles de ma prop firm et le calcul prop (python run.py prop ...).
5. Répète au maximum 5 itérations, puis résume : ce qui a été testé, ce qui a échoué, ce qui reste.
Règles : jamais de paramètre ajusté après avoir vu les résultats hors échantillon,
toujours inclure spread et commissions, jamais d'argent réel.
```

## Ce qui compte comme « alpha » crédible
- Verdict walk-forward **ROBUSTE** avec ≥ 200 trades hors échantillon au total
- Profit factor > 1,2 **après** frais, drawdown max compatible avec votre prop firm
- Même comportement sur un 2ᵉ marché proche (ex. NQ et ES, ou XAUUSD chez 2 brokers)
- Puis ≥ 1 mois en démo avec `python run.py live ... --live`
