# Generated manually on 2026-07-31 to match project migration style
# (Django/DB tooling unavailable offline to autogenerate this one)

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('staffing', '0002_alter_allocationproposal_status_allocationauditlog_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='developerleave',
            name='is_approved',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='developerleave',
            name='approved_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='approved_leaves',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
