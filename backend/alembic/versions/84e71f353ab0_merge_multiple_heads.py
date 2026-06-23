"""Merge multiple heads

Revision ID: 84e71f353ab0
Revises: aaa08e8d142d, f02ed429ae7c
Create Date: 2026-06-23 15:19:25.280341

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '84e71f353ab0'
down_revision: Union[str, Sequence[str], None] = ('aaa08e8d142d', 'f02ed429ae7c')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
