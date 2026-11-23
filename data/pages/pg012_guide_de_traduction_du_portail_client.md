---
id: pg012
title: "Guide de traduction du portail client"
space: digital_channels
system: customer_portal
type: doc
author: p016
created: 2025-12-08
updated: 2026-08-25
language: fr
---

# Guide de traduction du portail client

**Responsable :** Marc-André Gagnon (Canaux numériques) · **Dernière mise à jour :** août 2026

Ce guide explique comment on traduit le portail client. Depuis Portail 2026, chaque page existe en français et en anglais, et aucune page ne sort dans une seule langue.

## Le principe

Aucun texte n'est écrit directement dans le code. Chaque texte a une clé, et la clé existe dans deux fichiers :

    locales/fr/claims.json
    locales/en/claims.json

Exemple, pour la clé `claims.form.title` :

    fr : "Déclarer une réclamation"
    en : "Report a claim"

Si une clé manque en français, le portail affiche le texte anglais. C'est pratique pendant le développement, mais ça ne doit jamais arriver en production : la vérification de l'étape 4 bloque la livraison.

## Les étapes pour un nouveau texte

1. Écris le texte en français d'abord. La majorité de nos clients lisent le portail en français.
2. Ajoute la clé dans les deux fichiers. Si tu n'es pas sûr de l'anglais, écris `TODO-EN` et demande une révision.
3. Vérifie le glossaire (plus bas). Un même mot anglais doit toujours donner le même mot français.
4. Lance `npm run i18n:check`. La commande échoue s'il manque une clé ou s'il reste un `TODO`.
5. Fais relire le texte par quelqu'un qui ne l'a pas écrit.

## Les pièges qu'on a déjà rencontrés

- **Le module de paiement** a son propre fichier (`payment.fr.json`). On l'avait oublié en mars 2026 (DIG-141).
- **Les courriels** sont des gabarits à part, dans `templates/email/`. Ils ne passent pas par les fichiers de traduction.
- **Les messages d'erreur du serveur** arrivent en anglais. Le portail doit les remplacer par un message traduit, jamais les afficher tels quels.
- **Les textes trop longs.** Le français prend environ 20 % de place de plus que l'anglais. Teste toujours sur un écran de téléphone.

## Glossaire (extrait)

| Anglais | Français | Note |
|---|---|---|
| claim | réclamation | Jamais « sinistre » dans le portail (DIG-156) |
| policy | police | |
| premium | prime | |
| deductible | franchise | |
| broker | courtier | |
| quote | soumission | Pas « devis » |
| log in | ouvrir une session | Pas « se logger » |

Le glossaire complet est dans `docs/glossaire.csv`.

## Ton et style

- On vouvoie le client.
- Des phrases courtes, et pas de jargon d'assurance quand un mot simple existe.
- Pas de majuscules partout : « Mes polices », pas « Mes Polices ».

## Besoin d'aide ?

Écris-moi, ou demande dans le canal de l'équipe Canaux numériques.
