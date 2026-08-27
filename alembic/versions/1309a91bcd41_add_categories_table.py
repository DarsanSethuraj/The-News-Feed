"""add categories table



Revision ID: 1309a91bcd41

Revises: 8b4dd87ce65a

Create Date: 2026-08-16



"""



from typing import Sequence, Union



from alembic import op

import sqlalchemy as sa





# revision identifiers, used by Alembic.

revision: str = "1309a91bcd41"



down_revision: Union[str, Sequence[str], None] = "8b4dd87ce65a"



branch_labels: Union[str, Sequence[str], None] = None



depends_on: Union[str, Sequence[str], None] = None





def upgrade() -> None:

    """Create categories table."""



    op.create_table(

        "categories",



        sa.Column(

            "id",

            sa.Integer(),

            nullable=False

        ),



        sa.Column(

            "name",

            sa.String(),

            nullable=False

        ),



        sa.Column(

            "active",

            sa.Boolean(),

            nullable=False

        ),



        sa.PrimaryKeyConstraint(

            "id"

        ),



        sa.UniqueConstraint(

            "name"

        )

    )



    op.create_index(

        "ix_categories_id",

        "categories",

        ["id"],

        unique=False

    )





def downgrade() -> None:

    """Remove categories table."""



    op.drop_index(

        "ix_categories_id",

        table_name="categories"

    )



    op.drop_table(

        "categories"

    )
