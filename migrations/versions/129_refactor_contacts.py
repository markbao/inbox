"""refactor contacts

Revision ID: 5eb9b70cf13
Revises: 284227d72f51
Create Date: 2015-01-21 00:20:27.625946

"""

# revision identifiers, used by Alembic.
revision = '5eb9b70cf13'
down_revision = '284227d72f51'

from alembic import op
import sqlalchemy as sa


def upgrade():
    connection = op.get_bind()
    connection.execute(
        sa.sql.text(
            '''
            delete from contact where source like "%remote%"
            '''
        )
    )
    op.drop_column('contact', 'provider_name')

    op.drop_constraint('uid', 'contact', type_='unique')
    op.drop_column('contact', 'source')

    op.create_unique_constraint('uid', 'contact',
                                ['uid', 'namespace_id'])


def downgrade():
    raise Exception('Will not downgrade')
