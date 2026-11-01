"""monitored servers

Revision ID: 0002
Revises: 0001
"""
from typing import Sequence, Union

from alembic import op
import finops_api.db
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('fleet_keys',
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('public_key', sa.Text(), nullable=False),
    sa.Column('private_key_encrypted', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
    sa.PrimaryKeyConstraint('organization_id')
    )
    op.create_table('servers',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('host', sa.String(length=255), nullable=False),
    sa.Column('port', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('host_key', sa.Text(), nullable=True),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('hostname', sa.String(length=200), nullable=True),
    sa.Column('os', sa.String(length=200), nullable=True),
    sa.Column('cpu_cores', sa.Integer(), nullable=True),
    sa.Column('mem_total_kb', sa.BigInteger(), nullable=True),
    sa.Column('disk_total_kb', sa.BigInteger(), nullable=True),
    sa.Column('usage', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('environment', sa.String(length=50), nullable=True),
    sa.Column('provider_id', sa.String(length=50), nullable=True),
    sa.Column('sku', sa.String(length=100), nullable=True),
    sa.Column('resource_class', sa.String(length=50), nullable=True),
    sa.Column('storage_type', sa.String(length=50), nullable=True),
    sa.Column('download_gb_override', finops_api.db.Money(18, 3), nullable=True),
    sa.Column('upload_gb_override', finops_api.db.Money(18, 3), nullable=True),
    sa.Column('renewal_date', sa.Date(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'host', 'port', name='uq_server_host')
    )
    op.create_index(op.f('ix_servers_organization_id'), 'servers', ['organization_id'], unique=False)
    op.create_table('server_samples',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('server_id', sa.String(length=36), nullable=False),
    sa.Column('taken_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('cpu_total', sa.BigInteger(), nullable=False),
    sa.Column('cpu_idle', sa.BigInteger(), nullable=False),
    sa.Column('mem_total_kb', sa.BigInteger(), nullable=False),
    sa.Column('mem_available_kb', sa.BigInteger(), nullable=False),
    sa.Column('disk_total_kb', sa.BigInteger(), nullable=False),
    sa.Column('disk_used_kb', sa.BigInteger(), nullable=False),
    sa.Column('rx_bytes', sa.BigInteger(), nullable=False),
    sa.Column('tx_bytes', sa.BigInteger(), nullable=False),
    sa.ForeignKeyConstraint(['server_id'], ['servers.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_server_samples_server_time', 'server_samples', ['server_id', 'taken_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_server_samples_server_time', table_name='server_samples')
    op.drop_table('server_samples')
    op.drop_index(op.f('ix_servers_organization_id'), table_name='servers')
    op.drop_table('servers')
    op.drop_table('fleet_keys')
