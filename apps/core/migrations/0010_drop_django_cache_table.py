"""Drop the `django_cache` table: the cache moved to Redis.

The cache used to be `DatabaseCache`, a table in this same Postgres database
created by `manage.py createcachetable`. It is now Render Key Value, and
Postgres holds application data and nothing else.

The table is dropped rather than left in place. It is not a Django model, so
nothing would ever touch it again, and an orphaned table full of pickled
roll-ups is exactly the kind of thing someone reads next year and mistakes for
data. Everything in it was derived from the tables around it, so there is
nothing to migrate out first.

`IF EXISTS` because a database created after this change never had one, and the
name could have been overridden by the old `CACHE_TABLE` environment variable
(the default is what is dropped here; a custom one has to go by hand).

Reversing recreates the empty table with the same schema `createcachetable`
builds, so rolling back to the database-cache commit lands on a working app.
"""
from django.db import migrations

DROP = 'DROP TABLE IF EXISTS "django_cache";'

# Exactly what `manage.py createcachetable` emits (see Django's
# createcachetable command): the key, the pickled value and the expiry.
RECREATE = """
CREATE TABLE IF NOT EXISTS "django_cache" (
    "cache_key" varchar(255) NOT NULL PRIMARY KEY,
    "value" text NOT NULL,
    "expires" timestamp with time zone NOT NULL
);
CREATE INDEX IF NOT EXISTS "django_cache_expires"
    ON "django_cache" ("expires");
"""


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_userprofile_is_new_user'),
    ]

    operations = [
        migrations.RunSQL(sql=DROP, reverse_sql=RECREATE),
    ]
