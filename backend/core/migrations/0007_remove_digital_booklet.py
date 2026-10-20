from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0006_staffregistrationrequest"),
    ]

    operations = [
        migrations.DeleteModel(name="MedicinePrescription"),
        migrations.DeleteModel(name="MedicineBookletEntry"),
        migrations.DeleteModel(name="MedicineBooklet"),
    ]
