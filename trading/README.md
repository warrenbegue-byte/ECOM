# 🤖 Bots de trading — analyse des 6 reels + boîte à outils

> ⚠️ **Avertissement** : le trading à effet de levier (CFD, futures, or) fait perdre de l'argent à la
> majorité des particuliers. Ce code est un outil de recherche et de test. **Toujours en compte démo
> d'abord**, plusieurs semaines, avant d'envisager de l'argent réel. Rien ici n'est un conseil financier.

---

## 🧠 Ce que montrent les reels (et faut-il installer leurs applis ?)

| # | Reel | Ce que c'est | Faut-il l'installer ? | Ce qui est reproduit ici |
|---|------|--------------|-----------------------|---------------------------|
| 1 | `@itsmikepoarch` — **Phantom Trader A.I.** | Bot payant (essai gratuit 2 semaines via lien en bio) qui exécute « ses » stratégies sur votre PC, avec objectif de profit et limites de risque | **Non.** Résultats non vérifiés, produit fermé, modèle « essai gratuit → abonnement ». Vous ne pouvez pas auditer ce qu'il fait de votre compte. | `tradebot/risk.py` (objectif + limites de risque) + `live_mt5.py` (exécution locale sur votre PC) |
| 2 | `@algo.jitnems` — **« 94% » + « commente Access »** | Liste d'attente pour un produit non nommé. « 94 % » = taux de réussite affiché sans preuve | **Non.** C'est de la capture de leads. Un taux de réussite seul ne veut rien dire : 94 % de gains de 1 $ et 6 % de pertes de 20 $ = compte qui fond. | `propfirm.py` montre pourquoi le taux de réussite ne suffit pas (seule l'espérance compte) |
| 3 | `@protos_quant` — **ORB NY** | Stratégie *Opening Range Breakout* sur l'ouverture de New York (9h30) | Rien à installer : c'est une stratégie publique et connue | `strategies.py → ORBStrategy` ✅ |
| 4 | `@raycfu` — **Loop Engineering** | Boucle « hypothèse → backtest → mesure → ajustement » (souvent avec une IA) pour chercher de l'*alpha* | Rien à installer | `optimize.py` : walk-forward qui **rejette** les paramètres surappris ✅ + `LOOP.md` (prompt pour itérer avec Claude) |
| 5 | `@davidtrades_model` — **Maths des challenges prop firm (SSRN)** | Probabilité de réussite sans avantage = `L / (L + T)` | Pas besoin de commenter « PROFIT » : la formule est ci-dessous | `propfirm.py` : formule + Monte Carlo avec votre stratégie ✅ |
| 6 | `@shahmeer___ahmed` — **« Premier HFT XAUUSD en local »** | Bot sur l'or qui tourne sur votre ordinateur | **Non.** Un vrai HFT exige des serveurs colocalisés et des latences en microsecondes : impossible depuis un PC perso chez un broker CFD. C'est un bot intraday rebaptisé « HFT » pour le marketing. | `strategies.py → GoldBreakoutStrategy` + `live_mt5.py` ✅ |

**Conclusion : vous n'avez besoin d'installer AUCUNE des applis des reels.** Ce dossier contient
l'équivalent ouvert, auditable et testé. Ce qu'il faut installer est listé juste en dessous.

---

## 🛠️ Ce qu'il faut installer (gratuit)

| Pour… | Installer | Remarque |
|-------|-----------|----------|
| Backtests, optimisation, calcul prop firm | **Python 3.11+** puis `pip install -r requirements.txt` | Marche sur Windows, Mac, Linux |
| Bot live sur l'or (XAUUSD) ou indices CFD | **MetaTrader 5** (téléchargé depuis le site de votre broker) + `pip install MetaTrader5` | **Windows uniquement** (sur Mac : VPS Windows ou machine virtuelle). Ouvrir un **compte démo** chez le broker. |
| Données historiques longues | Export depuis MT5 (*Affichage → Symboles → Barres → Exporter*) | Yahoo Finance est limité à 60 jours en 5 min |

Dans MT5 : activer le bouton **Algo Trading** (barre d'outils) et cocher
*Outils → Options → Expert Advisors → Autoriser le trading algorithmique*.

---

## 🚀 Utilisation

```bash
cd trading
pip install -r requirements.txt

# 0) Télécharger l'historique 1 minute gratuit (HistData.com, ~5 Mo par an et par marché)
python run.py download xauusd 2023      # or
python run.py download nsxusd 2023      # Nasdaq 100

# 1) Optimiser PUIS tester un bot (walk-forward + test 2026 jamais vu + frais x2 + prop firm)
python run.py optimize orb_nasdaq        --histdata "data/nsxusd_*.zip"
python run.py optimize orb_gold          --histdata "data/xauusd_*.zip"
python run.py optimize gold_breakout     --histdata "data/xauusd_*.zip"
python run.py optimize gold_breakout_m15 --histdata "data/xauusd_*.zip"
#    -> écrit params/<bot>.json (paramètres optimisés + tous les résultats)

# 2) Re-tester les paramètres optimisés, avec les règles de votre prop firm
python run.py backtest --params params/orb_nasdaq.json --histdata "data/nsxusd_*.zip" --from 2026-01-01 --risk 0.5

# 3) Vos chances de réussir un challenge avec un taux de réussite / RR donné
python run.py prop --win-rate 0.45 --rr 2 --risk 0.5 --target 10 --max-loss 10 --daily-loss 5 --fee 500

# 4) Bot live MT5 avec les paramètres optimisés — SIMULATION (aucun ordre envoyé)
python run.py live --params params/orb_nasdaq.json --symbol US100 --risk 0.5

# 5) Bot live MT5 — ordres réels sur le compte DÉMO
python run.py live --params params/orb_nasdaq.json --symbol US100 --risk 0.5 --live
```

Le nom du symbole dépend du broker (`US100`, `NAS100`, `USTEC`… / `XAUUSD`, `GOLD`).
Vérifiez aussi le décalage horaire de son serveur (`--server-utc-offset`, souvent 2 l'hiver et 3 l'été).

Règles prop firm réglables partout : `--account 100000 --target 10 --daily-loss 5 --max-loss 10 [--trailing]`
(`--target 0` = pas d'objectif, pour un compte perso).

**Valeur du point** (`--point-value`) = gain pour 1,0 de mouvement de prix et 1 unité :
actions/ETF = 1 · XAUUSD 1 lot = 100 · NQ = 20 · MNQ = 2 · ES = 50 · MES = 5.
En live, elle est lue automatiquement chez le broker.

---

## 📐 Les maths prop firm en 30 secondes (reel 5)

Sans avantage statistique : **P(réussite) = Perte max / (Perte max + Objectif)**

| Objectif | Perte max | Chance sans avantage |
|---------:|----------:|---------------------:|
| 10 % | 10 % | 50 % |
| 8 % | 10 % | 56 % |
| 10 % | 5 % | 33 % |
| 8 % | 5 % | 38 % |

La perte journalière max, le spread et les frais font **baisser** ces chiffres. Seule une espérance
positive (`taux de réussite × RR − taux d'échec > 0`) les fait monter. Le calculateur le chiffre,
y compris le **coût moyen pour obtenir un compte financé** (frais ÷ probabilité).

Les 5 règles qui tuent les comptes : risquer trop par trade (> 1 %), ignorer la perte journalière,
doubler après une perte, trader les annonces sans stop, et confondre taux de réussite et rentabilité.

---

## 📈 Résultats après optimisation (3,75 ans de données, détail dans [`RESULTATS.md`](RESULTATS.md))

| Bot | Hors échantillon | 2026 jamais vu | Verdict |
|-----|-----------------:|---------------:|---------|
| ORB NY sur Nasdaq | −0,04 R/trade | −0,08 R | ❌ Rejeté |
| ORB sur l'or (8h20 NY) | +0,09 R (1 pli positif sur 4) | +0,04 R | ⚠️ Fragile |
| Bot or M5 (achat seul) | +0,05 R | +0,08 R | ✅ Validé pour la démo* |
| **Bot or M15 (achat seul)** | **+0,12 R** | **+0,09 R** | ✅ **Validé pour la démo*** |
| Bot or M15 achat + vente | +0,02 R | +0,01 R | ⚠️ Fragile |

\* Validés **parce que l'or a monté de 129 %** : sur un marché baissier simulé, le bot or M15 perd −42 R.
C'est un suiveur de tendance haussière, à mettre en pause si l'or casse sa tendance.
Challenge prop firm (10 % / 10 % / 5 %, 60 jours) : ~58 % de réussite à 2 % de risque, contre ~41 %
sans avantage. Avant tout argent réel : ≥ 1 mois de démo cohérent avec ces chiffres.

## 🗂️ Structure

```
trading/
├── run.py                  # ligne de commande : download | optimize | backtest | prop | live
├── LOOP.md                 # prompt pour faire du « Loop Engineering » avec Claude
├── RESULTATS.md            # résultats détaillés de l'optimisation et des tests
├── params/                 # paramètres optimisés (un .json par bot) + tous leurs résultats
├── data/                   # historiques téléchargés (non versionnés)
├── requirements.txt
├── tradebot/
│   ├── data.py             # CSV, export MT5, Yahoo Finance, données synthétiques
│   ├── histdata.py         # téléchargement / lecture de l'historique 1 min HistData.com
│   ├── risk.py             # règles prop firm + taille de position
│   ├── backtest.py         # backtester prudent (stop prioritaire, spread, gaps, stop suiveur)
│   ├── strategies.py       # ORBStrategy (NY) + GoldBreakoutStrategy (XAUUSD)
│   ├── presets.py          # marchés, frais réalistes et grilles d'optimisation de chaque bot
│   ├── optimize.py         # Loop Engineering : walk-forward, plateau, calcul parallèle
│   ├── lab.py              # optimiser -> tester sur 2026 -> frais x2 -> prop firm -> params/*.json
│   ├── propfirm.py         # formule L/(L+T), Monte Carlo, rejeu des vrais trades, risque optimal
│   └── live_mt5.py         # bot MetaTrader 5 local (simulation par défaut, démo exigée)
└── tests/test_tradebot.py  # python -m unittest discover -s tests
```
