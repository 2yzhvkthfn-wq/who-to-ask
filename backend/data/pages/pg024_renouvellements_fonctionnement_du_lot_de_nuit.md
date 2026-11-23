---
id: pg024
title: "Renouvellements : fonctionnement du lot de nuit"
space: policy_systems
system: policy_admin
type: doc
author: p003
created: 2026-06-29
updated: 2026-06-30
language: fr
---

# Renouvellements : fonctionnement du lot de nuit

**Responsable :** Daniel Morin (Systèmes de polices) · **Rédigé en juin 2026**, après l'incident d'avril

Le lot de renouvellement est le traitement le plus important de Policy Admin. Chaque soir, il prépare le renouvellement des polices qui arrivent à échéance. Cette page explique ce qu'il fait, pour que plus d'une personne puisse le dépanner.

## En bref

- Démarrage : 20 h, tous les soirs
- Durée normale : de 2 h 30 à 3 h
- Volume : environ 6 000 polices par soir, et jusqu'à 11 000 en octobre
- En cas d'échec : le lot peut être relancé le lendemain matin avant 6 h, pas après

## Les étapes

1. **Sélection.** Le lot prend les polices dont l'échéance tombe dans 60 jours.
2. **Exclusions.** Il met de côté les polices annulées, celles qui ont une réclamation en litige, et celles qui ont un changement en cours.
3. **Tarification.** Pour chaque police, il demande la nouvelle prime au moteur de tarification.
4. **Règles de souscription.** Les polices qui ne respectent plus les règles sont envoyées à un souscripteur.
5. **Documents.** Il produit l'avis de renouvellement, en français ou en anglais selon la langue du client.
6. **Envoi.** Les avis partent le lendemain matin, par la poste ou dans le portail client.

## Ce qui peut mal tourner

| Symptôme | Cause probable | Quoi faire |
|---|---|---|
| Beaucoup de polices « ignorées » dans le journal | Un indicateur de changement en cours resté actif (billet POL-181) | Vérifier l'indicateur avant de relancer |
| Le lot dure plus de 4 h | Le moteur de tarification répond lentement | Appeler l'équipe Tarification, et ne pas arrêter le lot |
| Aucun avis produit | Le service de documents est arrêté | Le redémarrer, puis relancer l'étape 5 seulement |

## Règles

- On ne lance jamais le lot à la main en production sans l'accord du chef d'équipe.
- Le journal est conservé 90 jours : `/var/log/pas/renewal`.
- Pendant la migration de la base de données des polices, le lot du samedi soir sera déplacé au dimanche.

## À qui parler

À moi d'abord. Lucas connaît bien l'étape des exclusions depuis le printemps.
