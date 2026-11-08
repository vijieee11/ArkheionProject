from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0019_barangay_population_snapshot")]

    operations = [
        migrations.AlterField(
            model_name="auditlog",
            name="action",
            field=models.CharField(
                choices=[
                    ("login", "Login"),
                    ("logout", "Logout"),
                    ("create", "Create"),
                    ("edit", "Edit"),
                    ("delete", "Delete"),
                    ("upload", "Upload"),
                    ("search", "Search"),
                    ("approve", "Approve"),
                    ("export", "Export"),
                ],
                max_length=20,
            ),
        ),
    ]
