"""password reset and ending sessions

Revision ID: 0003
Revises: 0002
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users') as batch:
        batch.add_column(sa.Column('session_version', sa.Integer(), nullable=False, server_default='0'))
        batch.add_column(sa.Column('reset_token_hash', sa.String(length=64), nullable=True))
        batch.add_column(sa.Column('reset_expires_at', sa.DateTime(timezone=True), nullable=True))
        batch.create_unique_constraint('uq_users_reset_token_hash', ['reset_token_hash'])


def downgrade() -> None:
    with op.batch_alter_table('users') as batch:
        batch.drop_constraint('uq_users_reset_token_hash', type_='unique')
        batch.drop_column('reset_expires_at')
        batch.drop_column('reset_token_hash')
        batch.drop_column('session_version')
