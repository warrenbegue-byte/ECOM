---
name: gabby-product-onboarding
description: Protocole d'intégration d'un nouveau produit pour la marque GABBY (boutique gabby-atelier.myshopify.com). À déclencher quand l'utilisateur dit "traite les nouveaux produits", "j'ai ajouté des robes", "gabbyfie le catalogue", ou après tout import de produits. Applique automatiquement : traduction FR, réécriture de la fiche, SEO, marque, tags, variantes. Déclencheurs — "nouveaux produits", "traite les produits", "GABBY protocole", "j'ai ajouté", "import".
---

# Protocole GABBY — Intégration d'un nouveau produit

Marque : **GABBY** — Fast-Luxury, robes de soirée. Slogan : « Le glamour n'a pas de prix ».
Voix : séductrice mais distinguée, "vous", vocabulaire riche (silhouettée, seconde peau, drapé délicat, minimalisme hypnotique). Interdits : "pas cher", "promo", "sexy" (→ sensuel), emojis dans les fiches.

## Détection des produits à traiter
Interroger Shopify : produits dont `vendor != "GABBY"` OU titre contenant de l'anglais (Dress, Women, Vestidos, Sexy…) OU description brute d'import (« SPECIFICATIONS », « Brand Name »). Ce sont les produits non "gabbyfiés".
Vérifier aussi les **doublons d'import** (même image/titre en plusieurs exemplaires) → à supprimer avant traitement.

## Traitement de chaque produit (via graphql_mutation productUpdate)
Envoyer les mutations en **petits lots** (max ~4 opérations par appel) — les grosses mutations coupent le connecteur.

1. **Titre premium** : un nom-personnage + descriptif (ex. « La Sulfureuse — Robe de Soirée Noire Dos Nu »).
2. **Handle** propre en français + `redirectNewHandle: true`.
3. **descriptionHtml** structurée :
   - Phrase d'accroche (vend le moment, PAS de libellé "L'Accroche")
   - `<p><strong>La Promesse Silhouette</strong>…` (coupe, confort, légèreté)
   - `<p><strong>Les Détails Haute Couture</strong>` + `<ul>` (matière, finitions, entretien)
   - `<p><strong>L'Offre Irrésistible</strong>` + livraison offerte + « <em>Le glamour n'a pas de prix.</em> »
4. **seo** : `title` « Nom — descriptif | GABBY », `description` 150-160 car. avec mots-clés (robe de soirée moulante, dos nu chic, robe longue…).
5. **vendor** : « GABBY ».
6. **tags** FR : type + coupe + détail (ex. Robe de soirée, Dos nu, Moulante).

## Variantes (via productOptionUpdate, 1 option/appel, petits lots)
- Renommer les options : `Color → Couleur`, `Size → Taille`.
- Traduire chaque valeur couleur en français (Black→Noir, Blue→Bleu, DEEP BLUE→Bleu nuit, Pink→Rose, green→Vert, Khaki→Kaki, Light-blue→Bleu clair…).
- Valeurs corrompues (« only top C », « green B ») : renommer au mieux et signaler à l'utilisateur pour vérification.

## Bijoux (colliers, parures…)
- Nom-personnage aussi (La Riviera, Le Serment, L'Éblouissante…) + descriptif « Collier / Ras-de-Cou / Parure ».
- Description plus courte : accroche + **Le Détail Précieux** (matière, éclat) + `<ul>` 4 puces + **L'Offre Irrésistible**.
- Tags : « Bijoux », « Collier » + spécifiques (Doré, Argent, Perles, Ras-de-cou, Cœur…).
- Options : `Metal Color → Couleur` (si valeurs lisibles) ou `Modèle` (si codes fournisseur), `Gem Color → Pierre`, `Length → Longueur` (valeurs en cm), `Ships From → Expédition`.
- Valeurs codes fournisseur intraduisibles (ex. « 8097 », « N155 ») : renommer l'option en « Modèle », garder les codes, **signaler à l'utilisateur** (mapping précis = besoin des photos).

## Rattachement & offres
- Les collections sont **intelligentes** (auto-remplies par tag/vendeur) : bien poser les tags suffit à ranger le produit.
- Robes : tag « Robe de soirée » → collections Robes de Soirée + Glamour à moins de 20€ (si prix < 20€, règle = prix ET tag robe).
- Bijoux : tag « Bijoux » → collection Colliers & Bijoux.
- L'Offre Duo (-15% dès 2 articles) est scopée à la collection « Robes de Soirée » — ne pas l'étendre aux bijoux sans décision de Warren.
- Mention livraison dans les fiches : toujours « Livraison offerte dès 29 € » (aligné sur la remise automatique).

## Rappel technique
- Toujours `validate_graphql_codeblocks` avant d'exécuter une mutation (si le validateur est indisponible, vérifier les inputs via `graphql_schema`).
- Le connecteur coupe sur les gros payloads : pour les descriptions, préférer **1 produit par appel, en appels parallèles** ; ≤4 opérations légères (options) par appel sinon.
- En cas de coupure « stream closed », l'écriture n'est PAS appliquée : re-vérifier l'état puis renvoyer (les productUpdate sont idempotents).
- Confirmer le résultat produit par produit (userErrors vides).
