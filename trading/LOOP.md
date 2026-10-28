# 🔁 Loop Engineering avec Claude (reel @raycfu)

L'idée du reel : une IA propose une hypothèse, la code, la backteste, lit les résultats, et recommence.
Le danger : à force d'itérer sur les mêmes données, l'IA (ou vous) finit par **sur-apprendre**.
Cette boucle impose donc un juge impartial : `python run.py optimize`, qui ne valide que ce qui tient
sur des données jamais vues (walk-forward 12 mois → 6 mois, plateau de paramètres, année 2026 gardée
de côté, frais doublés, puis simulation prop firm sur les seuls trades hors échantillon).

## Prompt à donner à Claude (Claude Code, dans ce dossier)

```
Tu es mon chercheur quant. Dans le dossier trading/ :
1. Lis tradebot/strategies.py et propose UNE hypothèse de stratégie simple (≤ 4 paramètres),
   avec une justification économique (pourquoi ce marché devrait se comporter ainsi).
2. Implémente-la comme nouvelle classe dans strategies.py (même interface reset/prepare/signal),
   ajoute-la à STRATEGIES et un preset (marché, frais, grille ≤ 500 combinaisons) dans tradebot/presets.py.
3. Lance : python run.py optimize <preset> --histdata "data/<marché>_*.zip"
4. Analyse le tableau walk-forward ET le holdout. Si le verdict est REJETÉ, explique pourquoi et propose
   une NOUVELLE hypothèse (ne pas juste élargir la grille). Si VALIDÉ, relance un backtest avec les
   règles de ma prop firm (python run.py backtest --params params/<preset>.json ...).
5. Répète au maximum 5 itérations, puis résume : ce qui a été testé, ce qui a échoué, ce qui reste.
Règles : jamais de paramètre ajusté après avoir vu les résultats du holdout (sinon il n'est plus
« jamais vu » : il faut alors attendre de nouvelles données), toujours inclure spread et commissions,
jamais d'argent réel.
```

## Ce qui compte comme « alpha » crédible
- Verdict **VALIDÉ pour la démo** avec ≥ 200 trades hors échantillon au total
- Profit factor > 1,2 **après** frais, drawdown max compatible avec votre prop firm
- Même comportement sur un 2ᵉ marché proche (ex. NQ et ES, ou XAUUSD chez 2 brokers)
- Puis ≥ 1 mois en démo avec `python run.py live ... --live`
