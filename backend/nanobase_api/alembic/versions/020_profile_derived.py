"""020 — sl_schema_profile.derived_json: where a table's description came from.

The dataclass has carried a `derived` list since the profile was written, the compiler reads it when
a table has no description of its own, and nothing ever stored it: the save did not write the field
and the load did not ask for it, so it came back empty on every read. A table description therefore
sat in the catalog with no account of who said so — the source's own word and this system's guess
were indistinguishable, and the compiler's fallback could never fire.

Columns already record this, each entry tagged with its source. Tables now do the same.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "020_profile_derived"
down_revision: Union[str, None] = "019_suggestions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sl_schema_profile",
                  sa.Column("derived_json", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("sl_schema_profile", "derived_json")
