"""remove url column from vehicle_images

Revision ID: remove_url_column
Revises: 
Create Date: 2025-06-18 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'remove_url_column'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Supprimer la colonne url de la table vehicle_images
    op.drop_column('vehicle_images', 'url')

def downgrade():
    # Ajouter la colonne url à la table vehicle_images
    op.add_column('vehicle_images',
        sa.Column('url', sa.String(255), nullable=True)
    ) 