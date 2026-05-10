"""merge heads

Revision ID: a185e75ad017
Revises: e2c7598103e4, e6cd58f7a67f
Create Date: 2026-05-05 16:45:34.234768

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a185e75ad017'
down_revision: Union[str, Sequence[str], None] = ('e2c7598103e4', 'e6cd58f7a67f')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
