from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    ROLE_CHOICES = [
        ('head_staff',    'Head Staff'),
        ('regular_staff', 'Regular Staff'),
        ('senior',        'Senior Citizen'),
        ('family',        'Family Member'),
    ]
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='regular_staff'
    )
    must_change_password = models.BooleanField(default=True)
    contact_number = models.CharField(max_length=20, blank=True)
    senior_citizen = models.ForeignKey(
        'SeniorCitizen',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='portal_users'
    )

    def __str__(self):
        return f"{self.username} ({self.role})"

    class Meta:
        db_table = 'users'


class SeniorCitizen(models.Model):
    SEX_CHOICES = [('M', 'Male'), ('F', 'Female')]
    CIVIL_STATUS_CHOICES = [
        ('single', 'Single'),
        ('married', 'Married'),
        ('widowed', 'Widowed'),
        ('others', 'Others'),
    ]
    STATUS_CHOICES = [
        ('pending',    'Pending'),
        ('complete',   'Complete'),
        ('incomplete', 'Incomplete'),
    ]

    # IDs
    osca_id              = models.CharField(max_length=20, unique=True)
    registration_cert_no = models.CharField(max_length=20, unique=True)

    # Personal info — OSCA Form No. 1
    last_name            = models.CharField(max_length=100)
    first_name           = models.CharField(max_length=100)
    middle_name          = models.CharField(max_length=100, blank=True)
    date_of_birth        = models.DateField()
    age                  = models.IntegerField()
    sex                  = models.CharField(max_length=1, choices=SEX_CHOICES)
    place_of_birth       = models.CharField(max_length=200)
    civil_status         = models.CharField(max_length=20, choices=CIVIL_STATUS_CHOICES)
    address              = models.TextField()
    barangay             = models.CharField(max_length=100)
    latitude             = models.FloatField(null=True, blank=True)
    longitude            = models.FloatField(null=True, blank=True)

    # Background
    educational_attainment = models.CharField(max_length=100, blank=True)
    occupation             = models.CharField(max_length=100, blank=True)
    annual_income          = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    other_skills           = models.TextField(blank=True)

    # Photo
    photo = models.ImageField(upload_to='senior_photos/', null=True, blank=True)

    # Association
    association_name    = models.CharField(max_length=200, blank=True)
    association_address = models.TextField(blank=True)
    date_of_membership  = models.DateField(null=True, blank=True)
    position            = models.CharField(max_length=100, blank=True)

    # Registration
    date_of_registration = models.DateField(auto_now_add=True)
    issued_at            = models.CharField(max_length=200, blank=True)
    issued_on            = models.DateField(null=True, blank=True)

    # Status
    milestone_age        = models.IntegerField(null=True, blank=True)
    registration_status  = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    is_active            = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.last_name}, {self.first_name} — {self.osca_id}"

    class Meta:
        db_table = 'senior_citizens'
        ordering = ['last_name', 'first_name']


class FamilyMember(models.Model):
    senior_citizen = models.ForeignKey(
        SeniorCitizen, on_delete=models.CASCADE,
        related_name='family_members'
    )
    name       = models.CharField(max_length=200)
    relation   = models.CharField(max_length=100)
    age        = models.IntegerField(null=True, blank=True)
    status     = models.CharField(max_length=50, blank=True)
    occupation = models.CharField(max_length=100, blank=True)
    income     = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'family_members'


class Document(models.Model):
    senior_citizen     = models.ForeignKey(SeniorCitizen, on_delete=models.CASCADE, related_name='documents')
    document_type      = models.CharField(max_length=100)
    file               = models.FileField(upload_to='documents/')
    file_name          = models.CharField(max_length=200)
    uploaded_by        = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    upload_date        = models.DateField(auto_now_add=True)
    nlp_classification = models.CharField(max_length=100, blank=True)
    nlp_confidence     = models.FloatField(null=True, blank=True)
    extracted_entities = models.JSONField(null=True, blank=True)
    is_verified        = models.BooleanField(default=False)
    created_at         = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'documents'


class GroceryDistribution(models.Model):
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('ongoing',   'Ongoing'),
        ('completed', 'Completed'),
    ]
    distribution_date   = models.DateField()
    barangay            = models.CharField(max_length=100)
    period              = models.CharField(max_length=20)
    total_beneficiaries = models.IntegerField(default=0)
    total_released      = models.IntegerField(default=0)
    status              = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    created_at          = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'grocery_distributions'


class GroceryClaim(models.Model):
    distribution      = models.ForeignKey(GroceryDistribution, on_delete=models.CASCADE, related_name='claims')
    senior_citizen    = models.ForeignKey(SeniorCitizen, on_delete=models.CASCADE, related_name='grocery_claims')
    claimed           = models.BooleanField(default=False)
    date_claimed      = models.DateField(null=True, blank=True)
    claimed_by        = models.CharField(max_length=20, default='self')
    representative    = models.CharField(max_length=200, blank=True)
    remarks           = models.TextField(blank=True)
    created_at        = models.DateTimeField(auto_now_add=True)
    updated_at        = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'grocery_claims'


class PensionRecord(models.Model):
    senior_citizen = models.ForeignKey(SeniorCitizen, on_delete=models.CASCADE, related_name='pension_records')
    period         = models.CharField(max_length=20)
    amount         = models.DecimalField(max_digits=10, decimal_places=2, default=500.00)
    claimed        = models.BooleanField(default=False)
    date_claimed   = models.DateField(null=True, blank=True)
    claimed_by     = models.CharField(max_length=20, default='self')
    representative = models.CharField(max_length=200, blank=True)
    remarks        = models.TextField(blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'pension_records'


class MedicineBooklet(models.Model):
    senior_citizen = models.ForeignKey(SeniorCitizen, on_delete=models.CASCADE, related_name='medicine_booklets')
    booklet_number = models.CharField(max_length=50, unique=True)
    date_issued    = models.DateField()
    place_issued   = models.CharField(max_length=200)
    is_active      = models.BooleanField(default=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'medicine_booklets'


class MedicinePrescription(models.Model):
    booklet          = models.ForeignKey(MedicineBooklet, on_delete=models.CASCADE, related_name='prescriptions')
    medicine_name    = models.CharField(max_length=200)
    qty_prescribed   = models.IntegerField()
    physician_name   = models.CharField(max_length=200)
    physician_address= models.TextField(blank=True)
    ptr_number       = models.CharField(max_length=50)
    balance          = models.IntegerField(default=0)
    prescription_date= models.DateField()
    expiry_date      = models.DateField(null=True, blank=True)

    # Partial fillings
    filling_1_qty       = models.IntegerField(null=True, blank=True)
    filling_1_date      = models.DateField(null=True, blank=True)
    filling_1_drugstore = models.CharField(max_length=200, blank=True)
    filling_1_pharmacist= models.CharField(max_length=200, blank=True)

    filling_2_qty       = models.IntegerField(null=True, blank=True)
    filling_2_date      = models.DateField(null=True, blank=True)
    filling_2_drugstore = models.CharField(max_length=200, blank=True)
    filling_2_pharmacist= models.CharField(max_length=200, blank=True)

    filling_3_qty       = models.IntegerField(null=True, blank=True)
    filling_3_date      = models.DateField(null=True, blank=True)
    filling_3_drugstore = models.CharField(max_length=200, blank=True)
    filling_3_pharmacist= models.CharField(max_length=200, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        filled = (
            (self.filling_1_qty or 0) +
            (self.filling_2_qty or 0) +
            (self.filling_3_qty or 0)
        )
        self.balance = self.qty_prescribed - filled
        super().save(*args, **kwargs)

    class Meta:
        db_table = 'medicine_prescriptions'


class AuditLog(models.Model):
    ACTION_CHOICES = [
        ('login',  'Login'),
        ('logout', 'Logout'),
        ('create', 'Create'),
        ('edit',   'Edit'),
        ('delete', 'Delete'),
        ('upload', 'Upload'),
        ('search', 'Search'),
        ('approve','Approve'),
    ]
    user        = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action      = models.CharField(max_length=20, choices=ACTION_CHOICES)
    module      = models.CharField(max_length=50)
    record_id   = models.IntegerField(null=True, blank=True)
    description = models.TextField()
    ip_address  = models.GenericIPAddressField(null=True, blank=True)
    timestamp   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table  = 'audit_logs'
        ordering  = ['-timestamp']