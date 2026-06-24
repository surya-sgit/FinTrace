"""add asset_class to transaction_ledger

Adds a tax-routing class to each ledger row so mutual funds (equity / debt / hybrid /
other) can be taxed under the correct rules. Existing rows backfill to 'EQUITY'.

Revision ID: b1c2d3e4f5a6
Revises: d6843d93010f
Create Date: 2026-06-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, Sequence[str], None] = 'd6843d93010f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'transaction_ledger',
        sa.Column('asset_class', sa.String(length=16), nullable=False, server_default='EQUITY'),
    )


def downgrade() -> None:
    op.drop_column('transaction_ledger', 'asset_class')
