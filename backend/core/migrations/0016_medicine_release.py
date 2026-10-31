import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0015_deathrecord_cancellation"),
    ]

    operations = [
        migrations.CreateModel(
            name="MedicineRelease",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("medicine_name", models.CharField(max_length=150)),
                ("quantity", models.PositiveIntegerField(default=1)),
                ("unit", models.CharField(blank=True, max_length=20)),
                ("date_released", models.DateField()),
                ("remarks", models.CharField(blank=True, max_length=300)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "recorded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="recorded_medicine_releases",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "senior_citizen",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="medicine_releases",
                        to="core.seniorcitizen",
                    ),
                ),
            ],
            options={
                "db_table": "medicine_releases",
                "ordering": ["-date_released", "-id"],
            },
        ),
    ]