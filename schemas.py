from marshmallow import Schema, fields, validate, pre_load, ValidationError
from datetime import datetime

class UserSchema(Schema):
    id = fields.Int(dump_only=True)
    nom = fields.Str(required=True, validate=validate.Length(min=2, max=100))
    email = fields.Email(required=True)
    role = fields.Str(dump_only=True)
    date_inscription = fields.DateTime(dump_only=True)

class UserRegisterSchema(Schema):
    nom = fields.Str(required=True, validate=validate.Length(min=2, max=100))
    name = fields.Str(load_only=True)  # Pour accepter le champ 'name' du frontend
    email = fields.Email(required=True)
    password = fields.Str(required=True, validate=validate.Length(min=8))

    @pre_load
    def process_name(self, data, **kwargs):
        """Convertit le champ 'name' en 'nom' si nécessaire"""
        if 'name' in data and 'nom' not in data:
            data['nom'] = data.pop('name')
        return data

    def handle_error(self, error, data, **kwargs):
        """Gestion personnalisée des erreurs de validation"""
        error_messages = {
            'nom': 'Le nom doit contenir entre 2 et 100 caractères',
            'email': 'L\'email doit être une adresse valide',
            'password': 'Le mot de passe doit contenir au moins 8 caractères'
        }
        return {field: [error_messages.get(field, str(err)) for err in errors] 
                for field, errors in error.messages.items()}

    class Meta:
        strict = True

class VehicleSchema(Schema):
    id = fields.Int(dump_only=True)
    marque = fields.Str(required=True, validate=validate.Length(min=2, max=50))
    modele = fields.Str(required=True, validate=validate.Length(min=2, max=50))
    annee = fields.Int(required=True, validate=validate.Range(min=1900, max=datetime.now().year))
    description = fields.Str(allow_none=True)
    prix_journalier = fields.Float(required=True, validate=validate.Range(min=0))
    statut = fields.Str(validate=validate.OneOf(['disponible', 'reserve', 'vendu']))
    images = fields.List(fields.Str(), allow_none=True)
    date_ajout = fields.DateTime(dump_only=True)

class ReservationSchema(Schema):
    id = fields.Int(dump_only=True)
    user_id = fields.Int(dump_only=True)
    vehicle_id = fields.Int(required=True)
    date_debut = fields.DateTime(required=True)
    date_fin = fields.DateTime(required=True)
    statut = fields.Str(dump_only=True)
    date_creation = fields.DateTime(dump_only=True)
    
    def validate_dates(self, data):
        if data['date_debut'] >= data['date_fin']:
            raise ValidationError('La date de fin doit être postérieure à la date de début')
        if data['date_debut'] < datetime.now():
            raise ValidationError('La date de début doit être dans le futur')

    class Meta:
        datetimeformat = '%Y-%m-%dT%H:%M:%S' 