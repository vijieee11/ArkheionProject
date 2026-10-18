# Register your models here.
from django.contrib import admin
from .models import Barangay, MedicineBooklet, MedicineBookletEntry, StaffProfile


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


@admin.register(MedicineBooklet)
class MedicineBookletAdmin(admin.ModelAdmin):
    list_display = ("booklet_number", "senior_citizen", "date_issued", "status", "loss_status", "is_active")
    list_filter = ("status", "loss_status", "is_active", "date_issued")
    search_fields = ("booklet_number", "senior_citizen__osca_id", "senior_citizen__first_name", "senior_citizen__last_name")
    readonly_fields = ("created_at", "full_at", "loss_reported_at", "loss_reviewed_at", "digital_replacement_issued_at")


@admin.register(MedicineBookletEntry)
class MedicineBookletEntryAdmin(admin.ModelAdmin):
    list_display = ("booklet", "category", "purchase_date", "review_status", "uploaded_at", "reviewed_by")
    list_filter = ("category", "review_status", "purchase_date")
    search_fields = ("booklet__booklet_number", "booklet__senior_citizen__osca_id", "description")
    readonly_fields = ("uploaded_by", "uploaded_at", "reviewed_by", "reviewed_at")


