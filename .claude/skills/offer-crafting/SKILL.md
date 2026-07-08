---
name: offer-crafting
description: Conception d'offres irrésistibles pour augmenter le panier moyen (AOV) — bundles, upsells, cross-sells, seuils de livraison gratuite, garanties et bonus. À utiliser pour structurer le pricing et les mécaniques d'incitation d'une boutique. Déclencheurs — "offre", "bundle", "upsell", "cross-sell", "AOV", "panier moyen", "pack", "remise", "livraison gratuite".
---

# Offer Crafting

Objectif : augmenter l'**AOV** (panier moyen) et la valeur perçue sans casser la marge. Une bonne offre rend le "non" difficile.

## Équation de valeur (Hormozi)
Valeur perçue = (Résultat rêvé × Probabilité perçue de l'atteindre) ÷ (Temps × Effort).
→ On augmente le haut (résultat + preuve), on réduit le bas (facilité, garantie).

## Mécaniques par étape du parcours
- **Sur la page produit** : bundles ("Pack de 3, -20 %"), choix de quantité par défaut sur le plus rentable.
- **À l'ajout au panier** : cross-sell d'un complément logique ("va bien avec").
- **Au panier** : barre de progression vers la **livraison gratuite** (seuil ≈ AOV × 1,3).
- **Au checkout** : upsell one-click à faible friction (produit d'impulsion, petit prix).
- **Post-achat** : upsell sur la page de confirmation (n'affecte pas le CVR initial).

## Construire un bundle qui convertit
1. Ancrer le prix : afficher le prix "à l'unité" barré vs le pack.
2. Nommer l'économie en € ET en % ("Économisez 24 € / -30 %").
3. Le pack doit résoudre le problème **plus complètement** que l'unité (pas juste "plus").

## Renforcer l'offre (empiler la valeur)
Garantie forte (satisfait ou remboursé), bonus gratuit à valeur perçue élevée, urgence honnête, paiement fractionné si AOV élevé.

## Livrable type
`Produit d'appel → Bundle → Cross-sell → Upsell checkout → Seuil livraison gratuite → Garantie`, avec prix et marge de chaque niveau.

## Outillage
Créer les remises via MCP Shopify (`create-discount`) ; mesurer l'effet via `run-analytics-query` (AOV avant/après).

## KPI suivis
AOV, taux d'attachement (attach rate) des upsells/cross-sells, marge par commande.
