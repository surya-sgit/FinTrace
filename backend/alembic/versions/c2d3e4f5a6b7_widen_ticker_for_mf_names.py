"""widen transaction_ledger.ticker for mutual-fund scheme names

Groww's mutual-fund order history identifies a holding by scheme name (no ISIN), which
exceeds the original 32-char ticker. Widen to 128.

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-06-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, Sequence[str], None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'transaction_ledger', 'ticker',
        existing_type=sa.String(length=32), type_=sa.String(length=128),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        'transaction_ledger', 'ticker',
        existing_type=sa.String(length=128), type_=sa.String(length=32),
        existing_nullable=False,
    )
