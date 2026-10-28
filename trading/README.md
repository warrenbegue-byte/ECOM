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

# 1) Vos chances de réussir un challenge prop firm (reel 5)
python run.py prop --win-rate 0.45 --rr 2 --risk 0.5 --target 10 --max-loss 10 --daily-loss 5 --fee 500

# 2) Backtest ORB New York sur le Nasdaq (reel 3)
python run.py backtest orb --yf QQQ --interval 5m --spread 0.01 --target 0
python run.py backtest orb --yf NQ=F --interval 5m --point-value 20      # futures NQ

# 3) Backtest du bot or sur un export MT5 (reel 6) — serveur broker en UTC+2
python run.py backtest gold --csv XAUUSD_M5.csv --tz-in Etc/GMT-2 --point-value 100 --qty-step 0.01 --spread 0.25

# 4) Loop Engineering sans se mentir (reel 4)
python run.py optimize orb --yf QQQ --interval 5m

# 5) Bot live MT5 — SIMULATION (aucun ordre envoyé, juste les logs)
python run.py live gold --symbol XAUUSD --timeframe M5 --risk 0.25

# 6) Bot live MT5 — ordres réels sur le compte DÉMO
python run.py live gold --symbol XAUUSD --timeframe M5 --risk 0.25 --live
python run.py live orb  --symbol US100  --timeframe M5 --risk 0.25 --live   # le nom du symbole dépend du broker
```

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

## 📈 Résultats honnêtes (60 derniers jours, Yahoo, 5 min, octobre 2026)

| Test | Trades | Réussite | Profit factor | Espérance |
|------|-------:|---------:|--------------:|----------:|
| ORB NY sur QQQ (paramètres par défaut) | 59 | 44 % | 0,76 | −0,11 R |
| Bot or sur GC=F (paramètres par défaut) | 140 | 41 % | 0,98 | −0,01 R |
| Walk-forward ORB sur QQQ | 36 hors échantillon | — | — | −0,13 R → **rejeté** |

Aucune des deux stratégies n'a d'avantage prouvé sur cette période courte. C'est **normal** et c'est
le vrai message : les reels montrent les meilleurs moments, pas la moyenne. Avant tout passage en
réel, exigez : ≥ 1 an de données (export MT5), ≥ 200 trades, walk-forward « ROBUSTE », puis
≥ 1 mois en démo avec des résultats cohérents avec le backtest.

---

## 🗂️ Structure

```
trading/
├── run.py                  # ligne de commande : prop | backtest | optimize | live
├── LOOP.md                 # prompt pour faire du « Loop Engineering » avec Claude
├── requirements.txt
├── tradebot/
│   ├── data.py             # CSV, export MT5, Yahoo Finance, données synthétiques
│   ├── risk.py             # règles prop firm + taille de position
│   ├── backtest.py         # backtester prudent (stop prioritaire, spread, gaps)
│   ├── strategies.py       # ORBStrategy (NY) + GoldBreakoutStrategy (XAUUSD)
│   ├── optimize.py         # walk-forward anti-surapprentissage
│   ├── propfirm.py         # formule L/(L+T) + Monte Carlo
│   └── live_mt5.py         # bot MetaTrader 5 local (simulation par défaut, démo exigée)
└── tests/test_tradebot.py  # python -m unittest discover -s tests
```
