# Register your models here.
from django.contrib import admin
from .models import Barangay, StaffProfile


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


