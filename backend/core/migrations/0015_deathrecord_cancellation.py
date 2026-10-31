import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0014_grocerydistribution_distribution_time"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="deathrecord",
            name="senior_citizen",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="death_records",
                to="core.seniorcitizen",
            ),
        ),
        migrations.AlterField(
            model_name="deathrecord",
            name="review_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending review"),
                    ("verified", "Verified"),
                    ("needs_correction", "Needs correction"),
                    ("cancelled", "Cancelled"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="deathrecord",
            name="cancellation_reason",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="deathrecord",
            name="cancelled_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="cancelled_death_reports",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="deathrecord",
            name="cancelled_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
