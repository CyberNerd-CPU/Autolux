# API LuxeAuto - Location de Voitures de Luxe

API REST pour la gestion d'un service de location de voitures de luxe.

## Prérequis

- Python 3.8+
- PostgreSQL
- pip (gestionnaire de paquets Python)

## Installation

1. Cloner le repository :
```bash
git clone <repository-url>
cd luxeauto
```

2. Créer un environnement virtuel et l'activer :
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

3. Installer les dépendances :
```bash
pip install -r requirements.txt
```

4. Créer la base de données PostgreSQL :
```sql
CREATE DATABASE luxeauto;
```

5. Configurer les variables d'environnement :
- Copier le fichier `.env.example` en `.env`
- Modifier les valeurs selon votre configuration

## Lancement

```bash
flask run
```

L'API sera accessible à l'adresse : http://localhost:5000

## Routes API

### Authentification
- POST `/api/register` - Inscription
- POST `/api/login` - Connexion
- GET `/api/profile` - Profil utilisateur

### Véhicules
- GET `/api/vehicles` - Liste des véhicules
- GET `/api/vehicles/<id>` - Détails d'un véhicule
- POST `/api/vehicles` - Ajouter un véhicule (admin)
- PUT `/api/vehicles/<id>` - Modifier un véhicule (admin)
- DELETE `/api/vehicles/<id>` - Supprimer un véhicule (admin)
- POST `/api/vehicles/<id>/upload` - Upload d'images (admin)

### Réservations
- POST `/api/reservations` - Créer une réservation
- GET `/api/reservations` - Liste des réservations de l'utilisateur
- GET `/api/admin/reservations` - Liste de toutes les réservations (admin)

## Compte Admin par défaut
- Email : admin@luxeauto.com
- Mot de passe : admin123

## Tests avec Postman

1. Créer une nouvelle collection
2. Importer les routes depuis le fichier `postman_collection.json`
3. Configurer l'environnement avec la variable `base_url` : http://localhost:5000
4. Pour les routes protégées, utiliser le token JWT obtenu après login 