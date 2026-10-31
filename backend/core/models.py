import os
import uuid

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings


class Barangay(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True)
    municipality = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "barangays"

    def __str__(self):
        return f"{self.name} ({self.code})"


class StaffProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="staff_profile",
    )
    barangay = models.ForeignKey(
        Barangay,
        on_delete=models.PROTECT,
        related_name="staff",
    )

    def __str__(self):
        return f"{self.user.get_username()} — {self.barangay.name}"


class StaffRegistrationRequest(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="staff_registration_request",
    )
    requested_barangay = models.ForeignKey(
        Barangay,
        on_delete=models.PROTECT,
        related_name="staff_registration_requests",
    )
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="pending")
    review_note = models.CharField(max_length=500, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_staff_registrations",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "staff_registration_requests"
        ordering = ["status", "created_at"]

    def __str__(self):
        return f"{self.user.get_username()} — {self.status}"



    
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
    suffix               = models.CharField(max_length=20, blank=True)
    date_of_birth        = models.DateField()
    age                  = models.IntegerField()
    sex                  = models.CharField(max_length=1, choices=SEX_CHOICES)
    place_of_birth       = models.CharField(max_length=200)
    civil_status         = models.CharField(max_length=20, choices=CIVIL_STATUS_CHOICES)
    address              = models.TextField()

    barangay = models.ForeignKey(
    Barangay,
    on_delete=models.PROTECT,
    related_name="senior_citizens",
    null=True,
    blank=True,
)

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
    is_association_member = models.BooleanField(default=False)
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


class DeathRecord(models.Model):
    REVIEW_STATUS_CHOICES = [
        ("pending", "Pending review"),
        ("verified", "Verified"),
        ("needs_correction", "Needs correction"),
        ("cancelled", "Cancelled"),
    ]
    senior_citizen = models.ForeignKey(
        SeniorCitizen,
        on_delete=models.PROTECT,
        related_name="death_records",
    )
    date_of_death = models.DateField()
    notes = models.TextField(blank=True)
    review_status = models.CharField(max_length=20, choices=REVIEW_STATUS_CHOICES, default="pending")
    review_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_death_reports",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="recorded_deaths",
    )
    cancellation_reason = models.TextField(blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cancelled_death_reports",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "death_records"
        ordering = ["-date_of_death", "-id"]

    def __str__(self):
        return f"Death of {self.senior_citizen} on {self.date_of_death}"


class ResidenceTransferRecord(models.Model):
    senior_citizen = models.ForeignKey(
        SeniorCitizen,
        on_delete=models.PROTECT,
        related_name="residence_transfers",
    )
    from_barangay = models.ForeignKey(
        Barangay,
        on_delete=models.PROTECT,
        related_name="outgoing_senior_transfers",
    )
    to_barangay = models.ForeignKey(
        Barangay,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="incoming_senior_transfers",
    )
    destination_municipality = models.CharField(max_length=120, blank=True)
    destination_address = models.TextField(blank=True)
    transfer_date = models.DateField()
    reason = models.CharField(max_length=300, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="recorded_residence_transfers",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "residence_transfer_records"
        ordering = ["-transfer_date", "-id"]

    def __str__(self):
        destination = self.to_barangay or self.destination_municipality or "Unspecified"
        return f"{self.senior_citizen} transferred from {self.from_barangay} to {destination}"


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


def document_upload_path(instance, filename):
    extension = os.path.splitext(filename)[1].lower()
    return f"documents/{uuid.uuid4().hex}{extension}"


class Document(models.Model):
    REVIEW_STATUS_CHOICES = [
        ("pending", "Pending review"),
        ("verified", "Verified"),
        ("rejected", "Rejected"),
    ]

    senior_citizen     = models.ForeignKey(SeniorCitizen, on_delete=models.CASCADE, related_name='documents')
    document_type      = models.CharField(max_length=100)
    file               = models.FileField(upload_to=document_upload_path)
    file_name          = models.CharField(max_length=200)
    uploaded_by        = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    upload_date        = models.DateField(auto_now_add=True)
    nlp_classification = models.CharField(max_length=100, blank=True)
    nlp_confidence     = models.FloatField(null=True, blank=True)
    classifier_source  = models.CharField(max_length=12, blank=True, default="")
    extracted_entities = models.JSONField(null=True, blank=True)
    is_verified        = models.BooleanField(default=False)
    review_status      = models.CharField(max_length=12, choices=REVIEW_STATUS_CHOICES, default="pending")
    review_note        = models.CharField(max_length=500, blank=True)
    reviewed_by        = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_documents",
    )
    reviewed_at        = models.DateTimeField(null=True, blank=True)
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
    distribution_time   = models.TimeField(null=True, blank=True)
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


class BookletReturn(models.Model):
    STATUS_FULL = "full"
    STATUS_CHOICES = [(STATUS_FULL, "Full")]

    senior_citizen = models.ForeignKey(
        SeniorCitizen, on_delete=models.PROTECT, related_name="booklet_returns"
    )
    date_returned = models.DateField()
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_FULL)
    note = models.CharField(max_length=300, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_booklet_returns",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "booklet_returns"
        ordering = ["-date_returned", "senior_citizen__last_name"]

    def __str__(self):
        return f"Full booklet returned for {self.senior_citizen} on {self.date_returned}"


class MedicineRelease(models.Model):
    """One medicine release to a senior. Stores item name and quantity only."""
    senior_citizen = models.ForeignKey(
        SeniorCitizen, on_delete=models.PROTECT, related_name="medicine_releases"
    )
    medicine_name = models.CharField(max_length=150)
    quantity = models.PositiveIntegerField(default=1)
    unit = models.CharField(max_length=20, blank=True)
    date_released = models.DateField()
    remarks = models.CharField(max_length=300, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_medicine_releases",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "medicine_releases"
        ordering = ["-date_released", "-id"]

    def __str__(self):
        return f"{self.medicine_name} x{self.quantity} to {self.senior_citizen} on {self.date_released}"
