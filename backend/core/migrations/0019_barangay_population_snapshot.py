from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0018_staff_settings"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BarangayPopulationSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reference_year", models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1900), django.core.validators.MaxValueValidator(2100)])),
                ("resident_population", models.PositiveIntegerField()),
                ("source", models.CharField(max_length=150)),
                ("source_reference", models.CharField(blank=True, max_length=300)),
                ("is_verified", models.BooleanField(default=False)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("barangay", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="population_snapshots", to="core.barangay")),
                ("verified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="verified_barangay_populations", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["barangay__name", "-reference_year"],
            },
        ),
        migrations.AddConstraint(
            model_name="barangaypopulationsnapshot",
            constraint=models.UniqueConstraint(fields=("barangay", "reference_year"), name="unique_barangay_population_year"),
        ),
        migrations.AddConstraint(
            model_name="barangaypopulationsnapshot",
            constraint=models.CheckConstraint(condition=models.Q(("resident_population__gt", 0)), name="positive_barangay_resident_population"),
        ),
        migrations.AddConstraint(
            model_name="barangaypopulationsnapshot",
            constraint=models.CheckConstraint(condition=models.Q(("reference_year__gte", 1900), ("reference_year__lte", 2100)), name="valid_barangay_population_year"),
        ),
    ]
