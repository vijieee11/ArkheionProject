# Register your models here.
from django.contrib import admin
from .models import Barangay, BookletReturn, DeathRecord, Document, ResidenceTransferRecord, StaffProfile, StaffRegistrationRequest


@admin.register(Barangay)
class BarangayAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "municipality", "is_active")
    list_filter = ("is_active", "municipality")
    search_fields = ("name", "code", "municipality")


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "barangay")
    list_filter = ("barangay",)
    search_fields = ("user__username", "user__first_name", "user__last_name")


@admin.register(StaffRegistrationRequest)
class StaffRegistrationRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "requested_barangay", "status", "created_at", "reviewed_by", "reviewed_at")
    list_filter = ("status", "requested_barangay", "created_at")
    search_fields = ("user__username", "user__first_name", "user__last_name", "user__email")
    readonly_fields = ("user", "created_at", "updated_at", "reviewed_by", "reviewed_at")


@admin.register(DeathRecord)
class DeathRecordAdmin(admin.ModelAdmin):
    list_display = ("senior_citizen", "date_of_death", "recorded_by", "created_at")
    list_filter = ("date_of_death",)
    search_fields = ("senior_citizen__osca_id", "senior_citizen__first_name", "senior_citizen__last_name")
    readonly_fields = ("recorded_by", "created_at")


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("file_name", "senior_citizen", "document_type", "review_status", "upload_date", "uploaded_by", "reviewed_by")
    list_filter = ("document_type", "review_status", "is_verified", "upload_date")
    search_fields = ("file_name", "senior_citizen__osca_id", "senior_citizen__first_name", "senior_citizen__last_name")
    readonly_fields = ("uploaded_by", "upload_date", "created_at", "nlp_classification", "nlp_confidence", "classifier_source", "extracted_entities", "reviewed_by", "reviewed_at")


@admin.register(ResidenceTransferRecord)
class ResidenceTransferRecordAdmin(admin.ModelAdmin):
    list_display = ("senior_citizen", "from_barangay", "to_barangay", "destination_municipality", "transfer_date", "recorded_by")
    list_filter = ("from_barangay", "to_barangay", "transfer_date")
    search_fields = ("senior_citizen__osca_id", "senior_citizen__first_name", "senior_citizen__last_name", "destination_municipality")
    readonly_fields = ("from_barangay", "recorded_by", "created_at")




@admin.register(BookletReturn)
class BookletReturnAdmin(admin.ModelAdmin):
    list_display = ("date_returned", "senior_citizen", "status", "recorded_by", "created_at")
    list_filter = ("date_returned", "status")
    search_fields = ("senior_citizen__osca_id", "senior_citizen__first_name", "senior_citizen__last_name", "note")
    readonly_fields = ("created_at",)