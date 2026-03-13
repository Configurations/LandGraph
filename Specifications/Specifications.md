# Maquette — Application de Gestion de Production

Les psécifications qui suivent sont à intégrer dans l'application existante. cela veut dire qu'un certains nombre de choses sont déjà en place dans l'application. il s'agit de les réutiliser de facon intéligente.

> Spécification détaillée de chaque écran pour le développement.
> Style visuel : inspiré de Linear — dark mode, haute densité, typographie monospace, animations subtiles.

---

## Architecture Générale

L'application est un layout en deux colonnes : une **Sidebar** fixe à gauche et une **Zone de contenu** principale à droite.

### Modèle Workflow des Issues

Le système sépare clairement trois dimensions indépendantes pour chaque issue :

**1. État workflow** (stocké) — séquence linéaire de 5 états :
```
backlog → todo → in-progress → in-review → done
```
Chaque issue est dans exactement un de ces états. Les transitions se font dans l'ordre logique, mais ne sont pas strictement contraintes (on peut revenir en arrière si besoin).

**2. Priorité** (stockée) — 4 niveaux, P1 à P4 :
- P1 (critique), P2 (haute), P3 (moyenne), P4 (basse)
- Orthogonale au workflow : une issue P1 peut être dans n'importe quel état.

**3. Flag "Bloqué"** (calculé dynamiquement) :
- Dérivé des relations `blocked-by` entre issues.
- Se superpose visuellement à n'importe quel état workflow.
- Se résout automatiquement quand toutes les issues bloquantes passent en `done`.
- Sert de signal visuel, pas de verrou : on peut techniquement avancer une issue bloquée, mais l'interface affiche un warning.

Cette séparation permet des combinaisons comme "todo + P1 + bloqué" ou "in-progress + P3 + non bloqué", chacune représentée visuellement par la superposition de ses indicateurs.

### Design Tokens (Palette de couleurs)

| Token | Valeur | Usage |
|-------|--------|-------|
| `--bg-primary` | `#0a0a0c` | Fond principal de l'app |
| `--bg-secondary` | `#111114` | Fond sidebar, panneaux, cartes |
| `--bg-tertiary` | `#1a1a1f` | Fonds d'éléments interactifs (search, progress bars) |
| `--bg-hover` | `#1e1e24` | État hover sur les lignes |
| `--bg-active` | `#24242c` | État actif / sélectionné |
| `--border-subtle` | `#222228` | Séparateurs légers entre éléments |
| `--border-strong` | `#2e2e36` | Bordures plus marquées |
| `--text-primary` | `#e8e8ec` | Texte principal (titres, contenus) |
| `--text-secondary` | `#9898a4` | Texte secondaire (labels de sidebar) |
| `--text-tertiary` | `#6b6b78` | Texte tertiaire (métadonnées) |
| `--text-quaternary` | `#45454f` | Texte le plus discret (timestamps, identifiants) |
| `--accent-blue` | `#5b8def` | Liens, badges actifs, onglets sélectionnés |
| `--accent-green` | `#3ecf8e` | Status "Done", approved, métriques positives |
| `--accent-orange` | `#f0a050` | Status "Todo", priorité moyenne, warnings |
| `--accent-yellow` | `#e8c44a` | Status "In Progress", pending |
| `--accent-red` | `#ef5555` | Flag "Blocked", bugs critiques, priorité P1 |
| `--accent-purple` | `#a78bfa` | Tags génériques |

### Typographie

Police principale : pile monospace — `SF Mono`, `Fira Code`, `JetBrains Mono`, `Cascadia Code`, `monospace`. Taille de base : 13px.

---

## Sidebar (colonne gauche)

Largeur : **220px** (dépliée) / **52px** (réduite). Fond `--bg-secondary`, bordure droite `--border-subtle`. La sidebar est rétractable par clic sur le header workspace.

### Composition verticale de la sidebar

1. **Workspace Header** (en haut)
   - Icône workspace : carré 24×24px, `border-radius: 6px`, dégradé violet (`#6366f1 → #8b5cf6`), contenant la lettre "P" en blanc, bold
   - Label : "Production" en `font-weight: 600`, `font-size: 13px`
   - Clic sur cette zone → toggle sidebar réduite/dépliée

2. **Barre de recherche**
   - Visible uniquement en mode déplié
   - Input stylisé (non fonctionnel dans la maquette) : fond `--bg-tertiary`, `border-radius: 6px`, icône loupe + placeholder "Search..." + badge clavier `⌘K`

3. **Section "Navigation"** (label en majuscules, `font-size: 10px`, `letter-spacing: 0.08em`, couleur `--text-quaternary`)
   - **Inbox** — icône boîte de réception, badge compteur "3" (fond `--accent-blue` à 13% d'opacité, texte `--accent-blue`)
   - **Issues** — icône cible (double cercle)
   - **Reviews** — icône bulle de commentaire, badge compteur "1"
   - **Pulse** — icône électrocardiogramme (ligne brisée)

4. **Section "Workspace"** (même style de label)
   - **Projects** — icône grille 2×2

5. **Section "Teams"** (visible uniquement en mode déplié)
   - **Engineering** — pastille carrée `#6366f1` (indigo) + label + code "ENG"
   - **Design** — pastille `#ec4899` (rose) + label + code "DES"
   - **Operations** — pastille `#f59e0b` (ambre) + label + code "OPS"

6. **Utilisateur courant** (en bas, `margin-top: auto`)
   - Avatar circulaire avec initiales "GB" + nom "Gabriel B"
   - Séparé par une bordure `--border-subtle`

### Comportement des items de navigation

- Chaque item : `padding: 7px 10px`, `border-radius: 6px`
- **État actif** : fond `--bg-active`, texte `--text-primary`, `font-weight: 500`
- **État inactif** : fond transparent, texte `--text-secondary`
- **Transition** : `background 0.15s ease`
- En mode réduit, seules les icônes sont visibles, centrées

---

## Header Bar (barre supérieure de la zone de contenu)

Hauteur : **46px**. Bordure inférieure `--border-subtle`.

Contenu :
- **Titre de la vue active** à gauche (`font-size: 14px`, `font-weight: 600`)
- **Bouton Filter** à droite : bordure `--border-subtle`, `border-radius: 6px`, icône entonnoir + label "Filter"
- **Bouton "+"** : carré 28×28px, fond `--accent-blue`, icône "+" blanc, `border-radius: 6px`

---

## Composants Partagés

### Avatar

Cercle coloré contenant les initiales (2 lettres max). Couleur de fond déterminée par le premier caractère du nom parmi 7 couleurs : `#6366f1`, `#f59e0b`, `#10b981`, `#ef4444`, `#8b5cf6`, `#ec4899`, `#06b6d4`. Taille paramétrable (20px par défaut).

### StatusIcon

Icônes indiquant l'état workflow d'une issue. Le workflow est une séquence linéaire de 5 états :

`backlog` → `todo` → `in-progress` → `in-review` → `done`

| État | Icône | Couleur |
|------|-------|---------|
| `backlog` | Cercle vide (trait pointillé) | `--text-quaternary` |
| `todo` | Cercle vide (trait plein) | `--accent-orange` |
| `in-progress` | Demi-cercle rempli | `--accent-yellow` |
| `in-review` | Horloge | `--accent-blue` |
| `done` | Check | `--accent-green` |

**Flag "Blocked"** : le flag bloqué n'est PAS un statut — c'est une surcouche visuelle calculée dynamiquement (voir Système de Dépendances). Quand une issue est bloquée :
- Un indicateur cadenas `🔒` en `--accent-red` se superpose à côté du StatusIcon (ne le remplace pas — on voit toujours l'état workflow réel)
- Le titre de l'issue passe en `opacity: 0.6`
- Dans le panneau de détail, une bannière rouge apparaît

Cela signifie qu'une issue peut être "todo + bloquée", "in-progress + bloquée", etc. L'état workflow et le flag de blocage sont deux dimensions indépendantes.

### PriorityBadge

4 barres verticales de hauteur croissante (3px → 13px). Remplies jusqu'au niveau de priorité :
- **P1** (critique) : rouge `--accent-red`
- **P2** (haute) : orange `--accent-orange`
- **P3** (moyenne) : jaune `--accent-yellow`
- **P4** (basse) : gris `--text-quaternary`
- Barres non remplies : `--border-subtle` à 30% d'opacité

Note : la priorité est orthogonale au statut workflow et au flag bloqué. Une issue P1 peut être dans n'importe quel état et être bloquée ou non.

### Tag

Pill compact : `font-size: 10px`, `padding: 1px 6px`, `border-radius: 3px`. Fond = couleur du tag à ~10% d'opacité, texte = couleur du tag. Couleurs contextuelles : `critical`/`bug` → rouge, `feature` → bleu, autres → violet.

### Sparkline

Polyline SVG sur un array de données numériques. Paramètres : `width` (défaut 80px), `height` (défaut 24px), `color`. La courbe est normalisée min/max.

### ProgressBar

Barre horizontale de 80px × 4px, fond `--bg-tertiary`, remplissage animé (`transition: width 0.6s cubic-bezier`).

### DependencyIndicator

Indicateur compact affiché dans les lignes d'issues pour signaler les relations de dépendance. Deux variantes :

- **Bloqué** (l'issue est bloquée par au moins une autre) : icône cadenas / flèche entrante, couleur `--accent-red`, tooltip listant les issues bloquantes. Le texte de la ligne d'issue passe en `opacity: 0.6` pour signaler visuellement le blocage.
- **Bloquant** (l'issue en bloque d'autres) : icône flèche sortante / warning, couleur `--accent-orange`, tooltip listant les issues bloquées.

Style : `font-size: 10px`, pill similaire au Tag — fond de la couleur à ~10% d'opacité, texte en couleur. Contenu : icône + nombre d'issues liées (ex. "🔒 2" pour "bloqué par 2 issues", "⚠ 3" pour "bloque 3 issues").

Si une issue a les deux (bloque ET est bloquée), les deux badges sont affichés côte à côte.

### RelationTypeBadge

Badge utilisé dans le panneau de détail pour qualifier chaque lien. Pill compact, `font-size: 10px`, `border-radius: 3px`.

| Type de relation | Label affiché | Couleur |
|------------------|---------------|---------|
| `blocks` | Blocks | `--accent-red` |
| `blocked-by` | Blocked by | `--accent-red` |
| `relates-to` | Related | `--accent-blue` |
| `parent` | Parent | `--accent-purple` |
| `sub-task` | Sub-task | `--accent-purple` |
| `duplicates` | Duplicate | `--text-tertiary` |

---

## Système de Dépendances — Concepts

### Types de liens entre issues

Le système supporte 6 types de relations, organisés en paires symétriques :

| Relation | Inverse | Sémantique |
|----------|---------|------------|
| `blocks` | `blocked-by` | L'issue source empêche la progression de l'issue cible. Une issue avec au moins un lien `blocked-by` non résolu (l'issue bloquante n'est pas `done`) est considérée **bloquée**. |
| `blocked-by` | `blocks` | Inverse automatique : créer un lien `blocks` de A→B crée implicitement un `blocked-by` de B→A. |
| `relates-to` | `relates-to` | Lien informatif symétrique, sans impact sur le statut. |
| `parent` | `sub-task` | Hiérarchie. Un parent agrège la progression de ses sub-tasks. |
| `sub-task` | `parent` | Inverse automatique de `parent`. |
| `duplicates` | `duplicates` | Marque un doublon. Symétrique. |

### Règles de blocage

- Une issue est **bloquée** si au moins un de ses liens `blocked-by` pointe vers une issue dont le statut n'est PAS `done`.
- Une issue bloquée ne peut pas être passée en `in-progress` ou `in-review` (contrainte visuelle : le changement de statut affiche un warning, mais n'est pas empêché — c'est un signal, pas un verrou dur).
- Le statut "bloqué" est **calculé dynamiquement**, pas stocké — il se résout automatiquement quand toutes les issues bloquantes passent en `done`.

---

## Écran 1 — Inbox

### Onglets de filtrage

Barre d'onglets horizontale sous le header : **All** (actif par défaut), **Mentions**, **Assigned**, **Reviews**. L'onglet actif a un texte `--text-primary`, `font-weight: 500`, et un trait inférieur de 2px en `--accent-blue`. Les inactifs sont en `--text-tertiary`.

### Liste des notifications

Chaque notification est une ligne cliquable avec hover (`--bg-hover`), séparée par `--border-subtle`. Animation d'entrée en cascade (`fadeSlideIn`, décalage de 60ms entre chaque ligne).

Contenu d'une ligne de notification (de gauche à droite) :
1. **Indicateur non-lu** : point bleu 6×6px (`--accent-blue`), ou espace vide si lu
2. **Avatar** de l'émetteur (28px)
3. **Bloc texte** (flex: 1) :
   - Ligne principale : texte descriptif (`font-size: 13px`, `font-weight: 500` si non lu, 400 si lu)
   - Sous-ligne : identifiant de l'issue liée (`font-size: 11px`, `--text-quaternary`)
4. **Timestamp** à droite (`font-size: 11px`, `--text-quaternary`)

Les notifications lues sont affichées à **60% d'opacité**.

### Types de notifications dans la maquette

| Type | Texte exemple | Avatar |
|------|---------------|--------|
| `mention` | "Léa t'a mentionné dans ENG-420" | Léa M |
| `assign` | "ENG-418 t'a été assigné — priorité critique" | System |
| `comment` | "Thomas a commenté sur ENG-419" | Thomas R |
| `status` | "DES-111 marqué comme terminé" | Clara V |
| `review` | "PR #247 prête pour review" | Léa M |
| `blocked` | "ENG-419 est maintenant bloqué par ENG-421" | System |
| `unblocked` | "ENG-417 n'est plus bloqué — ENG-420 terminé" | System |
| `dependency_added` | "Gabriel a ajouté une dépendance : ENG-418 blocks ENG-419" | Gabriel B |

---

## Écran 2 — Issues

Layout en deux colonnes : **Liste des issues** (flex: 1) + **Panneau de détail** (340px, conditionnel).

### Onglets de groupement

Barre d'onglets : **status** (actif par défaut), **team**, **assignee**, **dependency**. Même style que les onglets Inbox.

Le groupement **dependency** affiche 3 groupes dans cet ordre :
- **Blocked** (icône cadenas, couleur `--accent-red`) : issues qui ont au moins un `blocked-by` non résolu. Compteur d'issues.
- **Blocking others** (icône warning, couleur `--accent-orange`) : issues qui bloquent au moins une autre issue. Compteur d'issues.
- **No dependencies** (icône check, couleur `--text-quaternary`) : issues sans aucune relation de blocage active.

### Liste groupée

Les issues sont regroupées par le critère sélectionné. Chaque groupe a :
- **Header de groupe** : fond `--bg-secondary`, sticky en haut du scroll. Contient l'icône de status (si groupé par status), le label du groupe (`font-size: 12px`, `font-weight: 600`), et le compteur d'items.
- **Ordre des groupes** (par status) : In Progress → In Review → Todo → Backlog → Done

### Ligne d'issue

Chaque issue est une ligne cliquable. Composition horizontale :

1. **PriorityBadge** (4 barres verticales)
2. **Identifiant** : ex. "ENG-421" — `font-size: 11px`, `font-weight: 500`, `--text-quaternary`, largeur fixe 64px
3. **StatusIcon** (icône colorée selon le statut)
4. **DependencyIndicator** (conditionnel) : affiché uniquement si l'issue a des relations `blocks` ou `blocked-by`. Voir composant partagé DependencyIndicator. Si l'issue est bloquée, le titre passe en `opacity: 0.6`.
5. **Titre** : texte principal, `font-size: 13px`, `--text-primary`, tronqué avec ellipsis si trop long
6. **Tags** : maximum 2 tags affichés (composant Tag)
7. **Avatar** de l'assigné (20px)
8. **Temps de création** : ex. "2h", "1d" — `font-size: 11px`, `--text-quaternary`, largeur fixe 28px, aligné à droite

**États visuels** :
- Hover : fond `--bg-hover`
- Sélectionné : fond `--bg-active`

### Panneau de détail (côté droit, 340px)

S'affiche avec une animation `slideIn` (translateX de 20px vers 0, avec fade). Fond `--bg-secondary`, bordure gauche `--border-subtle`.

Contenu du panneau :

1. **Header** : identifiant de l'issue + bouton fermer "×"
2. **Titre** : `font-size: 16px`, `font-weight: 600`, `line-height: 1.4`
3. **Bannière de blocage** (conditionnelle) : si l'issue est bloquée, une bannière pleine largeur s'affiche sous le titre. Fond `--accent-red` à ~10% d'opacité, bordure gauche 3px solid `--accent-red`, padding 8px 12px. Icône cadenas + texte "Bloqué par X issue(s)" avec les identifiants cliquables des issues bloquantes.
4. **Tableau de propriétés** (chaque ligne séparée par `--border-subtle`) :
   - **Status** : StatusIcon + label textuel
   - **Priority** : PriorityBadge + label "P1"/"P2"/etc.
   - **Assignee** : Avatar (18px) + nom complet
   - **Team** : code équipe (ex. "ENG")
   - **Created** : timestamp relatif (ex. "2h ago")
5. **Tags** : liste de tous les tags de l'issue, en wrap
6. **Section Dépendances** : section dédiée sous les tags, avec titre "Dependencies" (`font-size: 12px`, `font-weight: 600`, `--text-secondary`, `margin-top: 16px`). Si aucune dépendance, affiche un texte gris "No dependencies" + bouton "+ Add dependency".

Pour chaque relation liée à l'issue, une ligne compacte :

| Élément | Description |
|---------|-------------|
| RelationTypeBadge | Badge coloré du type de relation (ex. "Blocks", "Blocked by", "Related") |
| Identifiant cible | ID de l'issue liée, en `--accent-blue`, cliquable (ouvre cette issue dans le panneau) |
| Titre cible | Titre de l'issue liée, tronqué, `font-size: 12px`, `--text-secondary` |
| StatusIcon cible | Statut actuel de l'issue liée (mini, 10px) |
| Bouton supprimer | Icône "×" discrète en `--text-quaternary`, visible au hover de la ligne |

Les relations sont groupées par type dans l'ordre : `blocked-by` (en premier, le plus critique), `blocks`, `parent`, `sub-task`, `relates-to`, `duplicates`.

Bouton "+ Add dependency" en bas de section : ouvre un mini-sélecteur (dropdown) avec champ de recherche pour trouver une issue + sélecteur de type de relation.

### Données des issues dans la maquette

| ID | Titre | Status | Priorité | Assigné | Équipe | Tags |
|----|-------|--------|----------|---------|--------|------|
| ENG-421 | Pipeline CI/CD — migration vers GitHub Actions | in-progress | P1 | Gabriel B | ENG | infra, devops |
| ENG-420 | Optimiser les requêtes N+1 sur l'API produits | in-review | P2 | Léa M | ENG | perf, api |
| ENG-419 | Implémenter le websocket pour les notifications temps réel | todo | P2 | Thomas R | ENG | feature |
| DES-112 | Design system — composants de tableaux de bord | in-progress | P2 | Clara V | DES | design-system |
| ENG-418 | Fix memory leak dans le worker de synchronisation | in-progress | P1 | Gabriel B | ENG | bug, critical |
| OPS-089 | Configurer le monitoring Prometheus + Grafana | todo | P3 | Nadia K | OPS | monitoring |
| ENG-417 | Ajouter les tests e2e pour le flow d'onboarding | backlog | P3 | Léa M | ENG | testing |
| DES-111 | Refonte des écrans de paramètres utilisateur | done | P4 | Clara V | DES | ui |
| OPS-088 | Automatiser le backup quotidien des bases de données | in-progress | P2 | Nadia K | OPS | infra, data |
| ENG-416 | Migrer les modèles Prisma vers la v5 | todo | P3 | Thomas R | ENG | migration |

### Relations de dépendance dans la maquette

| Source | Type | Cible | Commentaire |
|--------|------|-------|-------------|
| ENG-421 | `blocks` | ENG-419 | Le CI/CD doit être migré avant de déployer les WebSockets |
| ENG-421 | `blocks` | ENG-417 | Les tests e2e dépendent du nouveau pipeline |
| ENG-418 | `blocks` | ENG-419 | Le memory leak doit être résolu avant d'ajouter les WebSockets |
| ENG-420 | `blocks` | ENG-416 | L'optimisation N+1 doit être mergée avant la migration Prisma v5 |
| DES-112 | `relates-to` | DES-111 | Le design system s'appuie sur la refonte des paramètres |
| OPS-089 | `blocked-by` | OPS-088 | Le monitoring nécessite les backups automatisés d'abord |
| ENG-419 | `parent` | ENG-418 | Le fix du memory leak est une sub-task du chantier WebSocket (conceptuellement) |

**Issues bloquées résultantes** (calculé dynamiquement) :
- **ENG-419** : bloqué par ENG-421 (in-progress) et ENG-418 (in-progress) → 🔒 affiché
- **ENG-417** : bloqué par ENG-421 (in-progress) → 🔒 affiché
- **ENG-416** : bloqué par ENG-420 (in-review) → 🔒 affiché
- **OPS-089** : bloqué par OPS-088 (in-progress) → 🔒 affiché

**Issues bloquantes** (issues qui en bloquent d'autres) :
- **ENG-421** : bloque 2 issues (ENG-419, ENG-417) → ⚠ affiché
- **ENG-418** : bloque 1 issue (ENG-419) → ⚠ affiché
- **ENG-420** : bloque 1 issue (ENG-416) → ⚠ affiché
- **OPS-088** : bloque 1 issue (OPS-089) → ⚠ affiché

---

## Écran 3 — Reviews

### Onglets de filtrage

Barre d'onglets : **All PRs** (actif par défaut), **Needs Review**, **Approved**, **Drafts**.

### Liste des Pull Requests

Chaque PR est une ligne avec animation d'entrée en cascade. Composition horizontale :

1. **Avatar** de l'auteur (28px)
2. **Bloc texte** (flex: 1) :
   - Ligne 1 : identifiant PR en `--accent-blue` (`font-weight: 500`) + titre de la PR (`font-weight: 500`)
   - Ligne 2 : nom de l'auteur + séparateur "•" + issue liée + "•" + nombre de fichiers — tout en `font-size: 11px`, `--text-quaternary`
3. **Diff summary** : ex. "+342 / -28" — `font-family: monospace`, `font-size: 11px`, `--text-tertiary`
4. **Badge de statut** : pill coloré, `font-size: 10px`, `font-weight: 500`, `border-radius: 4px`

### Statuts des PRs

| Statut | Label | Couleur texte | Couleur fond |
|--------|-------|---------------|--------------|
| `pending` | Pending | `--accent-yellow` | yellow à ~10% opacité |
| `approved` | Approved | `--accent-green` | green à ~10% opacité |
| `changes_requested` | Changes | `--accent-orange` | orange à ~10% opacité |
| `draft` | Draft | `--text-quaternary` | `--bg-tertiary` |

### Données des PRs dans la maquette

| ID | Titre | Auteur | Issue liée | Statut | Diff | Fichiers |
|----|-------|--------|------------|--------|------|----------|
| PR-251 | feat: real-time notifications via WebSocket | Thomas R | ENG-419 | pending | +342 / -28 | 8 |
| PR-250 | perf: optimize N+1 queries on products API | Léa M | ENG-420 | approved | +89 / -156 | 4 |
| PR-247 | fix: memory leak in sync worker | Gabriel B | ENG-418 | changes_requested | +23 / -12 | 2 |
| PR-245 | chore: migrate Prisma models to v5 | Thomas R | ENG-416 | draft | +567 / -489 | 15 |

---

## Écran 4 — Pulse

Dashboard de métriques en layout vertical avec 3 sections.

### Section 1 — Métriques principales (grille 4 colonnes)

4 cartes métriques identiques en structure. Chaque carte : `padding: 16px`, `border-radius: 8px`, bordure `--border-subtle`, fond `--bg-secondary`.

Contenu d'une carte :
- **Label** en haut : `font-size: 11px`, `--text-tertiary`
- **Zone basse** en flex row, alignée en bas :
  - Colonne gauche : **valeur principale** (`font-size: 24px`, `font-weight: 700`, `letter-spacing: -0.04em`) + **sous-texte** (`font-size: 11px`, `--text-quaternary`)
  - Colonne droite : **Sparkline** (80×24px)

| Métrique | Valeur | Sous-texte | Couleur sparkline | Données sparkline |
|----------|--------|------------|-------------------|-------------------|
| Velocity | 28 | +12% vs last week | `--accent-blue` | [12, 18, 15, 22, 19, 25, 21, 28] |
| Burndown | 14 | issues remaining | `--accent-green` | [45, 40, 38, 32, 28, 25, 20, 14] |
| Cycle Time | 2.4d | avg resolution | `--accent-purple` | [4, 3.5, 3, 2.8, 3.2, 2.6, 2.5, 2.4] |
| Throughput | 6/w | completed per week | `--accent-orange` | [3, 5, 4, 6, 5, 7, 6, 6] |

### Section 2 — Status Distribution

Carte avec même style que les métriques. Titre "Status Distribution" (`font-size: 12px`, `font-weight: 600`).

- **Barre empilée horizontale** : hauteur 8px, `border-radius: 4px`, gap 2px entre les segments. Chaque segment a un `flex` proportionnel à son compte.
- **Légende** en dessous : pastille colorée 8×8px + label + count bold + pourcentage

| Statut | Compte | Pourcentage | Couleur |
|--------|--------|-------------|---------|
| Done | 1 | 10% | `--accent-green` |
| In Review | 1 | 10% | `--accent-blue` |
| In Progress | 4 | 40% | `--accent-yellow` |
| Todo | 3 | 30% | `--accent-orange` |
| Backlog | 1 | 10% | `--text-quaternary` |

### Section 3 — Team Activity

Carte avec titre "Team Activity". Liste de membres avec :

Chaque ligne membre :
1. **Avatar** (24px)
2. **Nom** : largeur fixe 90px, `font-size: 12px`
3. **ProgressBar** : 80px, couleur `--accent-green`, valeur = `completed / (completed + inProgress) × 100`
4. **Label "X done"** en `--accent-green`, `font-size: 11px`
5. **Label "X active"** en `--accent-yellow`, `font-size: 11px`

| Membre | Terminés | En cours |
|--------|----------|----------|
| Gabriel B | 5 | 2 |
| Léa M | 4 | 1 |
| Thomas R | 2 | 2 |
| Clara V | 3 | 1 |
| Nadia K | 1 | 2 |

### Section 4 — Dependency Health

Carte avec titre "Dependency Health" (`font-size: 12px`, `font-weight: 600`). Fournit une vue synthétique de l'état des dépendances à l'échelle du workspace.

**Métriques en ligne** (3 mini-cartes horizontales dans la carte, même style que les métriques principales mais plus compactes — `padding: 12px`, pas de sparkline) :

| Métrique | Valeur | Couleur | Description |
|----------|--------|---------|-------------|
| Blocked Issues | 4 | `--accent-red` | Nombre d'issues actuellement bloquées |
| Blocking Issues | 4 | `--accent-orange` | Nombre d'issues qui en bloquent d'autres (bottlenecks) |
| Dependency Chains | 2 | `--accent-yellow` | Nombre de chaînes de dépendances de profondeur ≥ 2 (ex. A bloque B qui bloque C) |

**Liste des bottlenecks** (sous les métriques) : liste ordonnée par impact décroissant (nombre d'issues bloquées, directement + transitivement). Chaque ligne :

1. **StatusIcon** de l'issue bloquante
2. **Identifiant** en `--accent-blue`, cliquable
3. **Titre** tronqué, `font-size: 12px`
4. **Compteur d'impact** : pill rouge — "Blocks X" (nombre d'issues bloquées directement + transitivement)
5. **Avatar** de l'assigné (18px)

Données dans la maquette :

| Issue bloquante | Titre | Impact direct | Impact transitif | Assigné |
|-----------------|-------|---------------|------------------|---------|
| ENG-421 | Pipeline CI/CD — migration vers GHA | 2 (ENG-419, ENG-417) | 2 (ENG-419 bloque potentiellement d'autres via parent) | Gabriel B |
| ENG-418 | Fix memory leak dans le sync worker | 1 (ENG-419) | 1 | Gabriel B |
| ENG-420 | Optimiser les requêtes N+1 | 1 (ENG-416) | 1 | Léa M |
| OPS-088 | Automatiser le backup quotidien | 1 (OPS-089) | 1 | Nadia K |

**Lecture clé** : ENG-421 est le bottleneck principal — il bloque 2 issues directement et crée la chaîne la plus longue. C'est l'issue à débloquer en priorité.

---

## Écran 5 — Projects (Workspace)

### Layout

Grille 2 colonnes (`grid-template-columns: repeat(2, 1fr)`, gap 12px), padding 20px. Animation d'entrée en cascade (`fadeSlideIn`, décalage de 80ms).

### Carte Projet

Chaque carte : `padding: 20px`, `border-radius: 10px`, bordure `--border-subtle`, fond `--bg-secondary`, hover → `--bg-hover`.

Composition verticale :

1. **Header** :
   - Pastille de couleur projet (10×10px, `border-radius: 3px`)
   - Nom du projet (`font-size: 14px`, `font-weight: 600`)
   - Badge de statut projet : pill avec fond à ~10% d'opacité

2. **Barre de progression** :
   - Ligne au-dessus : "X/Y issues" (`--text-tertiary`) + pourcentage en couleur du projet
   - Barre pleine largeur, 4px de haut, `border-radius: 2px`, fond `--bg-tertiary`, remplissage en couleur du projet, transition animée

3. **Indicateurs de dépendances** (conditionnel, affiché seulement si le projet a des issues bloquées ou bloquantes) :
   - Ligne compacte entre la barre de progression et le footer
   - Deux badges inline : "🔒 X blocked" en `--accent-red` à 10% d'opacité + "⚠ Y blocking" en `--accent-orange` à 10% d'opacité
   - Si un projet a des issues bloquées par des issues **extérieures** au projet (dépendances cross-projet), un badge supplémentaire "↗ Z external" en `--accent-blue` à 10% d'opacité signale la dépendance inter-projets

4. **Footer** :
   - Gauche : Avatar du lead (20px) + nom
   - Droite : Sparkline de vélocité (60×20px, en couleur du projet)

### Statuts Projet

| Statut | Label | Couleur |
|--------|-------|---------|
| `on-track` | On Track | `--accent-green` |
| `at-risk` | At Risk | `--accent-orange` |
| `off-track` | Off Track | `--accent-red` |

### Données des projets dans la maquette

| Nom | Lead | Progression | Statut | Issues (total/terminées) | Équipe | Couleur | Vélocité (sparkline) | Bloquées | Bloquantes | Ext. |
|-----|------|-------------|--------|--------------------------|--------|---------|----------------------|----------|------------|------|
| Infrastructure Modernization | Gabriel B | 65% | on-track | 12/8 | ENG | `#6366f1` | [3,5,4,7,6,8,5,9] | 2 | 3 | 0 |
| Design System v2 | Clara V | 40% | at-risk | 8/3 | DES | `#ec4899` | [2,3,1,4,2,3,4,2] | 0 | 0 | 0 |
| API Performance Sprint | Léa M | 80% | on-track | 6/5 | ENG | `#10b981` | [4,6,5,7,8,6,7,9] | 1 | 1 | 0 |
| Observability Stack | Nadia K | 25% | on-track | 10/2 | OPS | `#f59e0b` | [1,2,1,3,2,3,4,3] | 1 | 1 | 0 |

### Navigation vers le détail

Un clic sur une carte projet navigue vers l'**Écran 6 — Project Detail** (ci-dessous). La sidebar reste visible mais l'item "Projects" dans la section Workspace conserve l'état actif.

---

## Écran 6 — Project Detail

Écran affiché quand on clique sur un projet depuis la grille (Écran 5). Il remplace le contenu de la zone principale. L'écran est composé d'un **header projet fixe** (avec pipeline workflow) et d'un **contenu à onglets** en dessous.

### Header Projet (fixe, en haut)

Le header est fixe (ne scrolle pas) et contient 3 sous-sections empilées verticalement :

#### 1. Barre de navigation supérieure (hauteur 46px)

Composition horizontale :

1. **Fil d'Ariane** : lien "← Projects" cliquable (`color: --text-tertiary`, hover → `--text-secondary`), retourne à la grille de l'écran 5
2. **Séparateur** : trait vertical 1×16px en `--border-subtle`
3. **Pastille couleur projet** : 10×10px, `border-radius: 3px`
4. **Nom du projet** : `font-size: 14px`, `font-weight: 600`, `letter-spacing: -0.02em`
5. **Badge statut projet** : pill "On Track" / "At Risk" / "Off Track" (mêmes styles que l'écran 5)
6. **Bouton settings** (à droite, `--text-quaternary`) : icône engrenage

#### 2. Ligne de métadonnées

Ligne horizontale de métadonnées, `font-size: 12px`, `padding-bottom: 14px`. Éléments espacés de 20px :

| Élément | Contenu | Style |
|---------|---------|-------|
| Lead | Avatar (18px) + nom + badge "Lead" en `font-size: 10px`, `--text-quaternary` | `--text-tertiary` |
| Dates | Icône calendrier + "15 Jan 2026 → 30 Apr 2026" | `--text-tertiary` |
| Membres | Icône utilisateurs + "3 members" | `--text-tertiary` |
| Badge Blocked | Pill "🔒 X blocked" — `font-size: 10px`, fond `--accent-red` à 10%, texte `--accent-red` | Conditionnel (si X > 0) |
| Badge Blocking | Pill "⚠ Y blocking" — `font-size: 10px`, fond `--accent-orange` à 10%, texte `--accent-orange` | Conditionnel (si Y > 0) |

#### 3. Workflow Pipeline (barre segmentée)

Barre horizontale segmentée représentant la distribution des issues du projet par état workflow. 5 segments côte à côte (gap: 3px), chacun représentant un état.

Pour chaque segment :
- **Barre colorée** : hauteur 6px, `border-radius: 3px`. `flex` proportionnel au nombre d'issues dans cet état (minimum flex de 4 pour les segments à 0 issue, pour rester visible). Couleur = couleur de l'état. Si le compte est 0 : fond `--bg-tertiary` à 30% d'opacité.
- **Labels en dessous** : `font-size: 10px`. Label de l'état à gauche (`--text-quaternary`), compte à droite en `font-weight: 600` (couleur de l'état si > 0, sinon `--text-quaternary`).

| Segment | Label | Couleur |
|---------|-------|---------|
| backlog | Backlog | `--text-quaternary` |
| todo | Todo | `--accent-orange` |
| in-progress | In Progress | `--accent-yellow` |
| in-review | In Review | `--accent-blue` |
| done | Done | `--accent-green` |

#### 4. Barre d'onglets

Sous le pipeline, barre d'onglets standard (même style que les autres écrans). 4 onglets :
- **Issues** (actif par défaut)
- **Dependencies**
- **Team**
- **Activity**

---

### Onglet Issues

Layout identique à l'écran 2 (Issues global) mais filtré sur les issues du projet uniquement.

**Liste groupée par statut workflow** — mêmes composants et comportements que l'écran 2 :
- Headers de groupe sticky avec StatusIcon + label + compteur
- Ordre : In Progress → In Review → Todo → Backlog → Done
- Chaque ligne d'issue : PriorityBadge, identifiant, StatusIcon, flags de dépendance, titre, tags, avatar, timestamp

**Flags de dépendance sur les lignes** — deux indicateurs conditionnels insérés entre le StatusIcon et le titre :
- **Flag bloqué** : si `isBlocked === true`, icône cadenas en `--accent-red` (10×10px). Le titre passe en `opacity: 0.5`.
- **Flag bloquant** : si `blockingCount > 0`, pill "⚠ N" en `--accent-orange` à 10% d'opacité, `font-size: 10px`.

**Panneau de détail latéral** (320px, côté droit) — s'ouvre au clic sur une issue (animation `slideIn`). Contenu :

1. **Header** : identifiant + bouton fermer "×"
2. **Bannière de blocage** (conditionnelle) : fond `--accent-red` à ~7% d'opacité, bordure gauche 3px solid `--accent-red`, `border-radius: 6px`, `padding: 8px 12px`. Icône cadenas + "Blocked by X issue(s)".
3. **Titre** : `font-size: 15px`, `font-weight: 600`, `line-height: 1.4`
4. **Propriétés** (lignes séparées par `--border-subtle`) :
   - Status : StatusIcon + label + mention "+ blocked" en `--accent-red` `font-size: 10px` si bloqué
   - Priority : PriorityBadge + "P1"/"P2"/etc.
   - Assignee : Avatar (18px) + nom
   - Created : timestamp relatif
5. **Tags** : en wrap
6. **Section Dependencies** : titre "Dependencies" (`font-size: 12px`, `font-weight: 600`, `--text-secondary`). Pour chaque relation liée à cette issue :
   - RelationTypeBadge ("Blocks" ou "Blocked by") en `--accent-red` à 10% d'opacité
   - Identifiant de l'issue liée en `--accent-blue`, `font-weight: 500`
   - StatusIcon de l'issue liée
   - Titre tronqué de l'issue liée en `--text-tertiary`
   - Si aucune relation : texte "No dependencies" en `--text-quaternary`

---

### Onglet Dependencies

Vue graphique SVG des dépendances entre les issues du projet. Fond `--bg-secondary`, `border-radius: 10px`, bordure `--border-subtle`, `padding: 20px`.

#### Disposition du graphe

Les issues sont disposées en **colonnes par état workflow** (axe X) et empilées verticalement dans chaque colonne (axe Y). Positions X des colonnes :

| Colonne | Position X |
|---------|-----------|
| Backlog | 60px |
| Todo | 200px |
| In Progress | 360px |
| In Review | 520px |
| Done | 680px |

Position Y : chaque issue dans une colonne est espacée de 80px verticalement (première à y=60px).

#### Headers de colonnes

Texte centré au-dessus de chaque colonne : label de l'état, `font-size: 10px`, `font-weight: 600`, couleur de l'état à 60% d'opacité, y=40px.

#### Nœuds (issues)

Chaque issue est un rectangle SVG :
- Dimensions : 100×36px, `rx: 6`
- Fond : `--bg-tertiary`
- Bordure : 1px en couleur de l'état workflow. Si l'issue est bloquée : 1.5px en `--accent-red` + overlay rouge à 6% d'opacité.
- Contenu texte :
  - Ligne 1 (y+15) : identifiant, `font-size: 10px`, `font-weight: 600`, `--text-quaternary`
  - Ligne 2 (y+27) : titre tronqué à 14 caractères + "…", `font-size: 9px`, couleur `--accent-red` si bloqué sinon `--text-secondary`
- Badge bloqué (conditionnel) : cercle 12px en haut à droite du nœud, fond `--accent-red` à 20%, emoji 🔒

#### Arêtes (relations)

Chaque relation `blocks` est tracée comme une courbe de Bézier cubique entre le bord droit du nœud source (x+100, y+18) et le bord gauche du nœud cible (x, y+18).
- Couleur : `--accent-red`, `stroke-width: 1.5`, `opacity: 0.5`
- Type trait : continu pour `blocks`, pointillé (`strokeDasharray: 4 3`) pour les autres types
- Flèche : triangle plein (`polygon`) au point d'arrivée, 6px de large, rempli en `--accent-red` à 60%

#### Légende

Sous le graphe, `margin-top: 14px`, `font-size: 11px`, `--text-tertiary` :
- Trait rouge continu + "Blocks"
- Carré avec bordure rouge + fond rouge à 10% + "Blocked issue"

---

### Onglet Team

Vue de la charge de travail par membre du projet. Layout vertical, `padding: 24px`, gap 12px entre les cartes.

#### Carte Membre

Une carte par membre. `padding: 16px`, `border-radius: 8px`, bordure `--border-subtle`, fond `--bg-secondary`. Animation d'entrée en cascade (80ms stagger).

Composition verticale :

1. **Header membre** (flex row) :
   - Avatar (32px) + bloc nom/rôle : nom en `font-size: 13px`, `font-weight: 600` ; rôle en `font-size: 11px`, `--text-tertiary` (ex. "Lead", "Engineer")
   - À droite : ratio de complétion en gros — "X/Y" en `font-size: 18px`, `font-weight: 700` + label "completed" en `font-size: 10px`, `--text-quaternary`

2. **Barre de progression** : pleine largeur, 4px de haut, `border-radius: 2px`, fond `--bg-tertiary`, remplissage `--accent-green`, `transition: width 0.6s ease`. Valeur = `tasksDone / tasksTotal × 100`.

3. **Liste des issues du membre** : liste compacte des issues assignées à ce membre dans le projet. Chaque ligne :
   - Fond `--bg-tertiary`, `padding: 4px 8px`, `border-radius: 4px`
   - StatusIcon + flag cadenas (si bloqué, en `--accent-red`) + identifiant (`font-size: 11px`, `--text-quaternary`, largeur 56px) + titre (`font-size: 12px`, `--text-secondary`, opacité 0.6 si bloqué)

4. **Indicateur de blocage** (conditionnel) : si le membre a des tâches bloquées, ligne en bas — icône cadenas + "X task(s) blocked" en `font-size: 10px`, `--accent-red`, `margin-top: 8px`

#### Données des membres dans la maquette (projet Infrastructure Modernization)

| Membre | Rôle | Issues total | Issues terminées | Issues bloquées |
|--------|------|-------------|-----------------|-----------------|
| Gabriel B | Lead | 5 | 3 | 0 |
| Léa M | Engineer | 4 | 3 | 0 |
| Thomas R | Engineer | 3 | 2 | 2 (ENG-419, ENG-416) |

---

### Onglet Activity

Timeline verticale des événements récents du projet. `padding: 24px`.

#### Structure de la timeline

- **Trait vertical** : position absolue à gauche (left: 8px), 1.5px de large, couleur `--border-subtle`, `border-radius: 1px`, s'étend sur toute la hauteur de la liste
- **Contenu** : `padding-left: 20px` (pour dégager l'espace du trait)

#### Événement (ligne de timeline)

Chaque événement est positionné relativement. Animation d'entrée en cascade (60ms stagger). Composition :

1. **Point sur la timeline** : cercle 9×9px, positionné à `left: -16px`, `top: 6px`. Fond `--bg-primary`, bordure 2px solid `--accent-blue`.
2. **Ligne de texte** (flex row, aligné baseline, wrap) :
   - Nom de l'utilisateur : `font-size: 12px`, `font-weight: 500`, `--text-primary`
   - Action : `font-size: 12px`, `--text-tertiary` (ex. "a changé le statut de", "a commencé", "a soumis PR-250 pour", "a terminé")
   - Issue : `font-size: 12px`, `font-weight: 500`, `--accent-blue`
   - Détail (optionnel) : `font-size: 11px`, `--text-quaternary`, précédé de " — " (ex. "todo → in-progress", "bloqué par ENG-421, ENG-418")
3. **Timestamp** : `font-size: 10px`, `--text-quaternary`, `margin-top: 2px`

Espacement entre événements : `padding-bottom: 20px`.

#### Données d'activité dans la maquette

| Temps | Utilisateur | Action | Issue | Détail |
|-------|-------------|--------|-------|--------|
| Il y a 30m | Gabriel B | a changé le statut de | ENG-418 | todo → in-progress |
| Il y a 2h | Gabriel B | a commencé | ENG-421 | — |
| Il y a 5h | Léa M | a soumis PR-250 pour | ENG-420 | — |
| Il y a 1d | Thomas R | a signalé un blocage sur | ENG-419 | bloqué par ENG-421, ENG-418 |
| Il y a 2d | Léa M | a terminé | ENG-414 | — |
| Il y a 3d | Gabriel B | a terminé | ENG-415 | — |

---

## Flow de Création de Projet

Le bouton "+" dans le header bar (quand on est sur la vue Projects, Écran 5) déclenche un parcours guidé en 3 étapes qui remplace le contenu de la zone principale. La sidebar reste visible. Un **stepper horizontal** dans le header bar indique la progression.

### Stepper (dans le header bar)

Remplace le titre de vue habituel. Composition horizontale, alignée à droite du header :

3 étapes : **Setup** → **AI Planning** → **Review**

Pour chaque étape :
- **Cercle numéroté** : 22×22px, `border-radius: 50%`
  - État futur : fond `--bg-tertiary`, texte `--text-quaternary`, bordure transparente
  - État courant : fond `--accent-blue` à 13%, texte `--accent-blue`, bordure 1.5px `--accent-blue`
  - État terminé : fond `--accent-blue` plein, icône check blanche
- **Label** : `font-size: 11px`, `font-weight: 500` si courant, 400 sinon
- **Connecteur** entre les étapes : trait horizontal 20×1px, couleur `--accent-blue` si l'étape précédente est terminée, sinon `--border-subtle`

À gauche du stepper : fil d'Ariane "← Projects" + séparateur + titre "New Project" (`font-weight: 600`).

---

## Écran 7 — Setup (Étape 1)

Écran de formulaire centré pour saisir les informations de base du projet. Layout centré, largeur max 520px, `padding: 48px 24px`.

### En-tête

- Titre "Create a new project" : `font-size: 20px`, `font-weight: 700`, `letter-spacing: -0.03em`
- Sous-titre : "Set up the basics, then let AI help you plan the details." — `font-size: 13px`, `--text-tertiary`

### Champs du formulaire

#### 1. Project name (obligatoire)

- Label : "Project name" avec astérisque rouge, `font-size: 12px`, `font-weight: 500`, `--text-secondary`
- Input : pleine largeur, `padding: 10px 14px`, `font-size: 13px`, fond `--bg-tertiary`, bordure `--border-subtle`, `border-radius: 8px`. Focus → bordure `--accent-blue`.
- Placeholder : "e.g. API Microservices Migration"

#### 2. Team (obligatoire)

- Label : "Team" avec astérisque rouge
- 3 cartes sélectionnables en ligne (flex row, gap 8px), une par équipe

Chaque carte équipe :
- `flex: 1`, `padding: 14px`, `border-radius: 8px`, fond `--bg-secondary`
- Bordure : `1.5px solid --border-subtle` par défaut → `{team.color}` au hover → `{team.color}` + fond `{team.color}` à 6% si sélectionné
- Contenu :
  - Pastille couleur (10×10px) + nom de l'équipe (`font-size: 13px`, `font-weight: 600`)
  - Avatars des membres empilés (chevauchement de -6px) + compteur "X members" en `font-size: 10px`, `--text-quaternary`
  - Si sélectionné : indicateur "✓ Selected" en couleur de l'équipe, `font-size: 10px`

#### 3. Dates (optionnelles)

Deux champs date côte à côte (flex row, gap 12px) :
- **Start date** : label avec icône calendrier, input type date
- **Target date** : idem

### Bouton principal

Pleine largeur, `padding: 12px 20px`, `border-radius: 8px` :
- **Activé** (nom + équipe remplis) : fond `--accent-blue`, texte blanc, `font-weight: 600`. Icône sparkle + "Continue with AI Planning"
- **Désactivé** : fond `--bg-tertiary`, texte `--text-quaternary`, `opacity: 0.6`, `cursor: not-allowed`

### Lien alternatif

Sous le bouton : "Or skip and create empty project" — lien en `--accent-blue`. Crée un projet vide et navigue directement vers l'Écran 6.

### Données des équipes

| ID | Nom | Couleur | Membres |
|----|-----|---------|---------|
| ENG | Engineering | `#6366f1` | Gabriel B, Léa M, Thomas R |
| DES | Design | `#ec4899` | Clara V, Yann G |
| OPS | Operations | `#f59e0b` | Nadia K, Hugo P |

---

## Écran 8 — AI Planning (Étape 2)

Conversation avec un assistant IA qui structure le projet en issues et dépendances. Layout en 2 colonnes : **zone de chat** (flex: 1) + **panneau de prévisualisation** (300px).

### Zone de chat (colonne gauche)

#### Header du chat

Hauteur fixe, `padding: 12px 24px`, bordure inférieure `--border-subtle`.
- Avatar IA : cercle 28px, dégradé `--accent-purple → --accent-blue`, icône sparkle blanche
- "AI Project Planner" : `font-size: 13px`, `font-weight: 600`
- Sous-titre : 'Helps you structure "{projectName}" into actionable issues' — `font-size: 10px`, `--text-quaternary`

#### Zone de messages

Scrollable, `padding: 20px 24px`, gap 16px. Auto-scroll vers le bas à chaque nouveau message.

**Bulle IA** (alignée gauche) :
- `max-width: 70%` (90% si contient des issues générées), fond `--bg-secondary`, bordure `--border-subtle`, `border-radius: 12px`, `padding: 10px 14px`

**Bulle utilisateur** (alignée droite) :
- `max-width: 70%`, fond `--accent-blue`, texte blanc, `border-radius: 12px`

**Indicateur de frappe IA** : 3 points animés (6×6px, `pulse` décalé de 200ms)

#### Contenu généré dans une bulle IA

Quand l'IA génère des issues, la bulle s'étend avec :

1. Texte introductif
2. Séparateur `--border-subtle`
3. **Compteur** : "8 issues generated" — `font-size: 11px`, `font-weight: 600`
4. **Liste des issues** : lignes compactes dans fond `--bg-tertiary`, `border-radius: 6px`. Chaque ligne : identifiant temporaire (T-001…) + StatusIconMini + PriorityDots + titre. Animation cascade 60ms.
5. **Compteur dépendances** : "7 dependencies"
6. **Liste des relations** : fond `--accent-red` à 3%. Source → "→ blocks →" → Cible → Raison
7. **Message de suivi** (bulle séparée, 800ms après) : proposition d'ajustements

#### Barre d'input

Fixe en bas, `padding: 12px 24px`, bordure supérieure `--border-subtle`.
- Input + bouton d'envoi (32×32px, fond `--accent-blue` si texte, `--bg-tertiary` sinon)
- Envoi par clic ou Entrée

Boutons de navigation sous l'input :
- "← Back to Setup" (gauche)
- "Review & Create →" (droite) — fond `--accent-green`, **visible seulement après génération**

### Panneau de prévisualisation (colonne droite, 300px)

Fond `--bg-secondary`, bordure gauche `--border-subtle`, `padding: 20px`. Titre "PROJECT PREVIEW" (majuscules, `font-size: 11px`, `letter-spacing: 0.08em`).

**Avant la génération** :
- Nom du projet + pastille couleur + nom équipe
- Zone vide avec icône sparkle + texte d'invitation

**Après la génération** (mise à jour en temps réel) :
- Description générée
- Mini workflow pipeline (barre 5 segments, hauteur 4px)
- Label "Pipeline (X issues)"
- Label "Dependencies (Y)"
- Badges de relations en pills compacts : "T-001 → T-003", `font-size: 9px`, fond `--accent-red` à 7%

### Séquence de conversation mock

| # | Rôle | Contenu |
|---|------|---------|
| 1 | IA | "Je suis prêt à t'aider à structurer ce projet. Décris-moi ce que tu veux accomplir — les objectifs, les contraintes, le périmètre — et je te proposerai un découpage en issues avec les dépendances." |
| 2 | User | (description libre du projet) |
| 3 | IA | Texte intro + bloc généré (8 issues, 7 relations) |
| 4 | IA | "Tu veux qu'on ajuste quelque chose ? Je peux ajouter des issues, modifier les priorités, ou revoir les dépendances." |
| 5+ | (itérations — l'utilisateur peut affiner, l'IA régénère) |

### Données mock générées par l'IA

#### Issues générées

| ID | Titre | Status | Priorité | Tags |
|----|-------|--------|----------|------|
| T-001 | Audit de l'API existante — cartographier les endpoints et dépendances | todo | P2 | audit, api |
| T-002 | Définir le schéma du gateway API (routes, auth, rate-limiting) | todo | P1 | architecture, gateway |
| T-003 | Extraire le service utilisateurs en microservice autonome | todo | P2 | migration, users |
| T-004 | Extraire le service produits en microservice autonome | todo | P2 | migration, products |
| T-005 | Implémenter le gateway API avec Kong/Traefik | todo | P1 | infra, gateway |
| T-006 | Configurer le tracing distribué (Jaeger/Tempo) | todo | P3 | observability |
| T-007 | Tests de charge et validation de la migration | backlog | P2 | testing, perf |
| T-008 | Rollout progressif avec feature flags | backlog | P3 | deployment |

#### Relations générées

| Source | Type | Cible | Raison |
|--------|------|-------|--------|
| T-001 | blocks | T-003 | L'audit doit identifier les frontières du service users |
| T-001 | blocks | T-004 | L'audit doit identifier les frontières du service products |
| T-002 | blocks | T-005 | Le schéma doit être validé avant l'implémentation |
| T-003 | blocks | T-007 | Le service doit exister pour être testé |
| T-004 | blocks | T-007 | Le service doit exister pour être testé |
| T-005 | blocks | T-007 | Le gateway doit router le trafic pour les tests de charge |
| T-007 | blocks | T-008 | Les tests doivent passer avant le rollout |

---

## Écran 9 — Review (Étape 3)

Révision finale avant création du projet. Layout centré, largeur max 800px, `padding: 32px 48px`, scrollable.

### En-tête

- "Review your project" : `font-size: 20px`, `font-weight: 700`
- "Everything looks good? You can still edit before creating." — `font-size: 13px`, `--text-tertiary`

### Carte résumé

`padding: 20px`, `border-radius: 10px`, bordure `--border-subtle`, fond `--bg-secondary`.
- Pastille couleur (12×12px) + nom du projet (`font-size: 16px`, `font-weight: 700`)
- Description générée
- Métadonnées : nom équipe, dates, compteur issues en `--accent-blue`, compteur dépendances en `--accent-red`

### Table des issues

Container avec header "Issues (8)". Chaque ligne (animation 40ms stagger) :
- PriorityDots + ID temporaire + StatusIconMini
- Flag bloqué (🔒) si cible d'un `blocks` → titre en `opacity: 0.5`
- Flag bloquant (⚠ N) si source de `blocks`
- Titre tronqué + tags en pills `--accent-purple`

### Table des dépendances

Container avec header "Dependencies (7)". Chaque ligne :
- Source en `--accent-blue` → badge "blocks" en `--accent-red` → Cible en `--accent-blue`
- Raison tronquée, `--text-quaternary`, max 300px

### Boutons d'action (alignés droite)

- "← Back to AI" : bordure `--border-subtle`, fond transparent
- "✓ Create Project" : fond `--accent-green`, texte blanc, `font-weight: 600`

### Interconnexion complète des écrans

```
Écran 5 (Grille Projects)
  │
  ├── Clic sur carte → Écran 6 (Project Detail)
  │     └── ← Projects → Écran 5
  │
  └── Bouton "+" → Écran 7 (Setup)
        │
        ├── "Continue with AI Planning" → Écran 8 (AI Planning)
        │     │
        │     ├── "← Back to Setup" → Écran 7
        │     │
        │     └── "Review & Create →" → Écran 9 (Review)
        │           │
        │           ├── "← Back to AI" → Écran 8
        │           │
        │           └── "✓ Create Project" → Écran 6 (nouveau projet)
        │
        └── "Skip and create empty project" → Écran 6 (projet vide)
```

---

## Animations

| Nom | Description | Durée | Easing |
|-----|-------------|-------|--------|
| `fadeSlideIn` | `opacity: 0 → 1` + `translateY(6px) → 0` | 300–400ms | ease |
| `slideIn` | `translateX(20px) → 0` + `opacity: 0 → 1` | 200ms | ease |
| App load | `opacity: 0 → 1` + `translateY(4px) → 0` | 500ms | ease, déclenché après 100ms |

Les animations d'entrée des listes utilisent un **décalage en cascade** (stagger) : chaque item a un `animation-delay` incrémenté de 60–80ms.

---

## Modèle de Données (schéma complet)

```
Team {
  id: string          // "ENG", "DES", "OPS"
  name: string
  color: string       // hex
}

Issue {
  id: string          // "ENG-421"
  title: string
  status: enum        // backlog | todo | in-progress | in-review | done
                      // ↑ Workflow séquentiel pur, 5 états.
                      // Pas de "urgent" — l'urgence est portée par priority.
                      // Pas de "blocked" — c'est un flag calculé, pas un état.
  priority: number    // 1 (critique) → 4 (low)
  assignee: string
  team: string        // Team.id
  tags: string[]
  created: string     // temps relatif "2h", "1d", "30m"
  // Flags calculés (non stockés, dérivés des IssueRelation) :
  // isBlocked: boolean     — true si ≥1 lien blocked-by pointe vers une issue non-done
  // blockedByCount: number — nombre d'issues bloquantes non résolues
  // blockingCount: number  — nombre d'issues que cette issue bloque
}

IssueRelation {
  id: string                // identifiant unique de la relation
  type: enum                // blocks | blocked-by | relates-to | parent | sub-task | duplicates
  sourceIssueId: string     // Issue.id — l'issue "depuis"
  targetIssueId: string     // Issue.id — l'issue "vers"
  createdBy: string         // nom de l'utilisateur ayant créé le lien
  createdAt: string         // timestamp
  // Note : les relations symétriques (blocks/blocked-by, parent/sub-task)
  // sont stockées une seule fois (ex. blocks de A→B) et la relation inverse
  // (blocked-by de B→A) est déduite automatiquement à l'affichage.
  // Les relations relates-to et duplicates sont symétriques nativement.
}

InboxItem {
  id: number
  type: enum          // mention | assign | comment | status | review | blocked | unblocked | dependency_added
  text: string
  issue: string       // Issue.id
  time: string        // temps relatif
  read: boolean
  avatar: string      // nom pour l'avatar
  // Pour les types blocked/unblocked/dependency_added :
  relatedIssue?: string    // Issue.id de l'issue liée dans la dépendance
  relationType?: string    // type de relation concernée
}

PullRequest {
  id: string          // "PR-251"
  title: string
  author: string
  issue: string       // Issue.id
  status: enum        // pending | approved | changes_requested | draft
  changes: string     // "+342 / -28"
  files: number
}

Project {
  id: number
  name: string
  lead: string
  description: string   // description courte du projet
  startDate: string     // "15 Jan 2026"
  targetDate: string    // "30 Apr 2026"
  progress: number      // 0-100
  status: enum          // on-track | at-risk | off-track
  issues: number        // total
  completed: number
  team: string          // Team.id
  color: string         // hex
  velocity: number[]    // données sparkline
  members: ProjectMember[]
  // Propriétés calculées :
  // blockedCount: number       — issues du projet actuellement bloquées
  // blockingCount: number      — issues du projet qui en bloquent d'autres
  // externalDepsCount: number  — issues bloquées par des issues hors du projet
}

ProjectMember {
  name: string          // nom complet
  role: string          // "Lead", "Engineer", "Designer", etc.
  tasksTotal: number    // nombre d'issues assignées dans le projet
  tasksDone: number     // nombre d'issues terminées
  // Propriétés calculées :
  // tasksBlocked: number — issues assignées au membre qui sont bloquées
}

ActivityEvent {
  time: string          // temps relatif "Il y a 30m"
  user: string          // nom de l'utilisateur
  action: string        // verbe d'action "a changé le statut de", "a terminé", etc.
  issue: string         // Issue.id
  detail?: string       // détail optionnel "todo → in-progress", "bloqué par ENG-421"
}
```

### Diagramme des relations (maquette)

```
ENG-421 (in-progress, P1)
  ├── blocks → ENG-419 (todo, P2)  [bloqué]   ← aussi bloqué par ENG-418
  └── blocks → ENG-417 (backlog, P3)  [bloqué]

ENG-418 (in-progress, P1)
  └── blocks → ENG-419 (todo, P2)  [bloqué]

ENG-420 (in-review, P2)
  └── blocks → ENG-416 (todo, P3)  [bloqué]

OPS-088 (in-progress, P2)
  └── blocks → OPS-089 (todo, P3)  [bloqué]

DES-112 (in-progress, P2)
  └── relates-to → DES-111 (done, P4)

ENG-419 (todo, P2)  [bloqué]
  └── parent → ENG-418 (in-progress, P1)

Légende :
  [bloqué] = flag isBlocked actif (au moins un blocage non résolu)
  Les issues sans [bloqué] ne sont pas bloquées, quel que soit leur statut workflow
```