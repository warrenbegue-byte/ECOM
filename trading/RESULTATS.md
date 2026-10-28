# 📊 Résultats — optimisation puis test des 4 bots (octobre 2026)

> Données : HistData.com, bougies 1 min → 5 min, **janvier 2023 → septembre 2026** (3 ans et 9 mois).
> Or (XAUUSD) : 1 826 $ → 4 176 $ (**+129 %**). Nasdaq 100 (NSXUSD).
> Frais : spread 0,25 $ sur l'or, 1,5 point sur le Nasdaq (CFD, hypothèse prudente).
> 1 R = la somme risquée sur un trade (ex. 0,5 % du compte).

## 🧪 Protocole (le « Loop Engineering » sans se mentir)

1. **Optimisation** sur 2023-2025 : 432 à 1 296 combinaisons de paramètres par bot, calcul parallèle.
2. **Walk-forward** : optimisé sur 12 mois → testé sur les 6 mois suivants, 4 fois (2024 S1 → 2025 S2).
3. **Plateau** : on retient une zone de paramètres où les voisins marchent aussi, pas un pic isolé.
4. **Holdout 2026** : 9 mois jamais utilisés pendant l'optimisation, testés une seule fois.
5. **Frais ×2** sur le holdout.
6. **Prop firm** : 10 000 challenges simulés en rejouant les vraies journées hors échantillon
   (objectif 10 %, perte max 10 %, perte journalière 5 %, 60 jours de bourse).

Verdict : **VALIDÉ pour la démo** = positif en walk-forward (≥ 60 % des plis), sur 2026 et avec frais ×2.
**FRAGILE** = positif sur une partie seulement. **REJETÉ** = rien ne tient.

## 🏁 Tableau de synthèse

| Bot (reel) | Paramètres optimisés | Optimisé (biaisé) | Walk-forward hors éch. | 2026 jamais vu | 2026 frais ×2 | Verdict |
|---|---|---:|---:|---:|---:|---|
| **ORB NY Nasdaq** (reel 3) | cassure du range 5 min, stop 0,2 ATR, objectif 1,5 R, filtre moyenne 20 j | +0,121 R | −0,041 R (2/4 plis) | −0,075 R | −0,076 R | ❌ **REJETÉ** |
| **ORB or** (reel 3 appliqué à l'or) | cassure du range 5 min après **8h20 NY** (ouverture COMEX), sortie fin de séance, filtre 20 j | +0,265 R | +0,087 R (**1/4** plis) | +0,037 R | +0,013 R | ⚠️ **FRAGILE** |
| **Bot or M5** (reel 6) | Donchian 40, stop 3 ATR, objectif 3 R, breakeven à 1 R, 12h-24h UTC, **achat seul** | +0,156 R | +0,046 R (3/4) | +0,077 R | +0,103 R | ✅ VALIDÉ* |
| **Bot or M15** (reel 6) | Donchian 40, stop 3 ATR, objectif 3 R, stop suiveur 3 ATR, 24h/24, **achat seul** | +0,147 R | **+0,120 R** (3/4) | **+0,093 R** | +0,086 R | ✅ VALIDÉ* — **le meilleur** |
| Bot or M15 symétrique | Donchian 10, stop 1 ATR, stop suiveur 3 ATR, 12h-24h UTC, achat + vente | +0,161 R | +0,022 R (3/4) | +0,008 R | −0,015 R | ⚠️ **FRAGILE** |

Détail complet (plis, années, prop firm) : `params/<bot>.json`.

## ⚠️ \*Le piège découvert : les bots or « validés » parient sur la hausse de l'or

L'optimiseur a choisi **« achat seul »** dans tous les plis, car l'or a monté de 129 % sur la période.
Test de régime sur le bot or M15 :

| Situation | R/trade | Total |
|---|---:|---:|
| Données réelles, achat seul | +0,137 | +94 R |
| Mois où l'or **baisse** (15 mois sur 44) | — | **−15,5 R** (−1,0 R/mois) |
| Mois où l'or monte | — | +3,8 R/mois |
| **Marché baissier simulé** (cours inversé), achat seul | **−0,087** | **−42 R** |
| Marché baissier simulé, achat + vente | +0,024 | +28 R |

➡️ Le bot or M15 « achat seul » est un **suiveur de tendance haussière** : excellent tant que l'or monte,
perdant si l'or entre dans un marché baissier. La version symétrique ne dépend pas du régime, mais son
avantage est trop faible pour survivre à des frais doublés.

## 🏦 Prop firm (reel 5) — risque optimal, sur trades hors échantillon uniquement

Challenge 100 k : objectif 10 %, perte max 10 %, perte journalière 5 %, 60 jours de bourse.

| Risque / trade | Bot or M15 : réussite | échec | encore en cours au jour 60 |
|---:|---:|---:|---:|
| 0,50 % | 5 % | 0 % | 95 % |
| 1,00 % | 35 % | 8 % | 58 % |
| 1,50 % | 53 % | 21 % | 27 % |
| **2,00 %** | **58 %** | 31 % | 11 % |

Comparaison honnête : un trader **sans avantage** (mêmes trades, espérance ramenée à zéro) réussit
~41 % dans ces conditions. Le bot apporte donc **+15 à +17 points** de réussite, mais au risque optimal
il échoue encore **1 fois sur 3**. Avec un challenge à 500 $, cela fait en moyenne ~860 $ dépensés par compte obtenu.

- ORB or : ~45 % à 1,5 % de risque contre ~42 % sans avantage → l'avantage est quasi nul.
- ORB Nasdaq : 35 % à 2 % de risque pour 55 % d'échecs → à éviter.

Exemple de trajectoire unique (bot or M15, challenge démarré le 2 janvier 2026, risque 0,5 %) :
objectif de +10 % atteint en 39 trades avec 1,8 % de drawdown max. C'est **un seul scénario favorable**
(l'or a monté début 2026), pas une promesse : la probabilité réelle est celle du tableau ci-dessus.

## ✅ Recommandations

1. **À mettre en démo** : `params/gold_breakout_m15.json`, en **M15**, risque **0,5 %** au début.
   ```bash
   python run.py live --params params/gold_breakout_m15.json --symbol XAUUSD --risk 0.5          # simulation
   python run.py live --params params/gold_breakout_m15.json --symbol XAUUSD --risk 0.5 --live   # démo
   ```
   Objectif de la démo : retrouver ≈ +0,1 R/trade sur 1-2 mois (≈ 13 trades/mois). Si l'or casse sa
   tendance (cours sous sa moyenne 200 jours), **mettre le bot en pause** : c'est son point faible connu.
2. **Optionnel en démo, pour comparer** : `params/orb_gold.json` (or, ouverture 8h20 NY).
3. **Ne pas utiliser** : ORB Nasdaq (rejeté), version symétrique (fragile).
4. **Jamais d'argent réel** avant : ≥ 1 mois de démo cohérent avec ces chiffres, et acceptation
   d'un drawdown d'au moins 20 R (soit 10 % du compte à 0,5 % de risque).

## 🔁 Prochaine itération (Loop Engineering)

Hypothèses à tester sur de **nouvelles données** (le holdout 2026 a maintenant été vu, il ne compte plus
comme « jamais vu ») :
- filtre de régime pour le bot or : n'acheter que si le cours est au-dessus de sa moyenne 200 jours ;
- même bot sur l'argent (XAGUSD) ou d'autres marchés en tendance, pour vérifier qu'il ne s'agit pas
  d'un hasard propre à l'or ;
- ORB or : tester l'ouverture de Londres (3h NY) et les annonces de 8h30.

Pour refaire tous les tests chez vous :
```bash
python run.py download xauusd 2023 && python run.py download nsxusd 2023
python run.py optimize gold_breakout_m15 --histdata "data/xauusd_*.zip"   # ~1 min sur 4 cœurs
```
