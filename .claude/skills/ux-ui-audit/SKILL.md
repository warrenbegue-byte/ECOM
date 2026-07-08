---
name: ux-ui-audit
description: Audit UX/UI et optimisation du taux de conversion (CRO) pour boutiques e-commerce. À utiliser pour analyser une page produit, un tunnel de commande (checkout), une page d'accueil ou de collection, repérer les points de friction et proposer des correctifs mesurables. Déclencheurs — "audit", "CRO", "taux de conversion", "friction", "checkout", "page produit", "UX", "abandon panier".
---

# UX/UI Audit — CRO

Objectif : augmenter le **taux de conversion** en supprimant la friction, pas en ajoutant du "joli".

## Méthode d'audit (dans cet ordre)
1. **Clarté de l'offre (5 secondes)** — le visiteur comprend-il quoi/pour qui/pourquoi acheter ici ?
2. **Confiance** — preuves sociales (avis, notes, UGC), badges paiement, politique de retour visible, garanties.
3. **Friction du parcours** — nombre de clics jusqu'à l'achat, champs inutiles au checkout, coûts surprises (livraison).
4. **Vitesse & mobile** — LCP < 2,5 s, images compressées, sticky "add to cart" mobile.
5. **Hiérarchie visuelle** — un seul CTA primaire par écran, contraste, above-the-fold utile.

## Leviers CRO à fort impact (priorité)
- CTA unique, verbe d'action, contrastant. Éviter les CTA multiples concurrents.
- Preuve sociale au-dessus de la ligne de flottaison (note + nb d'avis).
- Réassurance près du bouton d'achat (retours, livraison, paiement sécurisé).
- Réduction des champs au checkout ; express checkout (Shop Pay / Apple Pay).
- Urgence/rareté **honnête** uniquement (stock réel, offre datée).
- Barre de livraison gratuite progressive (lie ce skill à `offer-crafting`).

## Livrable type
Tableau priorisé : `Problème → Impact estimé (Haut/Moyen/Bas) → Correctif → KPI`.
Toujours trier par (impact ÷ effort) décroissant.

## KPI suivis
Taux de conversion (CVR), taux d'ajout au panier, taux d'abandon checkout, CVR mobile vs desktop.

## Outillage
Utiliser le MCP Shopify (`run-analytics-query`, `get-product`) pour chiffrer l'état actuel avant de recommander.
