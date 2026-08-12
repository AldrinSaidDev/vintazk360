from django.db import migrations, models


class Migration(migrations.Migration):
    """Soft-delete for an upload, matching kpi_record and kpi_definition.

    A batch that was uploaded by mistake has to leave Recent Import History
    without destroying the audit trail of what it did, so this is a flag rather
    than a DELETE. The records it wrote are soft-deleted alongside it.
    """

    dependencies = [
        ('kpi', '0003_alter_kpirecord_remarks'),
    ]

    operations = [
        migrations.AddField(
            model_name='kpiimportbatch',
            name='is_active',
            field=models.BooleanField(
                default=True,
                help_text='Cleared when the import is deleted. The row and its issues survive.',
            ),
        ),
    ]
