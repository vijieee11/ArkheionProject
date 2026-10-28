from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0012_deathrecord_review_note_deathrecord_review_status_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BookletReturn",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date_returned", models.DateField()),
                ("status", models.CharField(choices=[("full", "Full")], default="full", max_length=12)),
                ("note", models.CharField(blank=True, max_length=300)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("recorded_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="recorded_booklet_returns", to=settings.AUTH_USER_MODEL)),
                ("senior_citizen", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="booklet_returns", to="core.seniorcitizen")),
            ],
            options={"db_table": "booklet_returns", "ordering": ["-date_returned", "senior_citizen__last_name"]},
        ),
    ]