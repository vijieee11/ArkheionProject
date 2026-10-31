from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0013_bookletreturn"),
    ]

    operations = [
        migrations.AddField(
            model_name="grocerydistribution",
            name="distribution_time",
            field=models.TimeField(blank=True, null=True),
        ),
    ]
