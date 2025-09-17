# worldpainter/builder/admin.py
from django.contrib import admin
from .models import (
    Areas, Races, Classes, DamageTypes, ItemTemplates, MobTemplates,
    Rooms, Exits, MobAttacks, MobLootTable,
    Players, Characters, CharacterStats, CharacterSkills, CharacterEquipment,
    ItemInstances, ShopInventories, BankAccounts, RoomObjects, AbilityTemplates
)

# --- Inlines: The core of the new world building UI ---

class ExitsInline(admin.TabularInline):
    """Allows editing exits directly within the Room admin page."""
    model = Exits
    fk_name = 'source_room' #Specify which foreign key to use for the inline
    extra = 1
    verbose_name = "Exit"
    verbose_name_plural = "Exits from this Room"

class RoomObjectsInline(admin.TabularInline):
    """Allows editing static room objects directly within the Room admin page."""
    model = RoomObjects
    extra = 1

class MobAttacksInline(admin.TabularInline):
    """Allows editing a mobs attacks directly on its template page."""
    model = MobAttacks
    extra = 1

class MobLootTableInline(admin.TabularInline):
    """Allows editing a mob's loot table directly on its template page."""
    model = MobLootTable
    extra = 1

# --- Read-Only Inlines for Viewing Character Sheets ---

class CharacterStatsInline(admin.StackedInline):
    """Read-only view of a character's stats"""
    model = CharacterStats
    can_delete = False
    verbose_name_plural = 'Character Stats'
    # Make all fields read-only
    readonly_fields = [f.name for f in CharacterStats._meta.get_fields() if f.name != 'character']

class CharacterSkillsInline(admin.TabularInline):
    """Read-only view of a character's skills."""
    model = CharacterSkills
    extra = 0
    can_delete = False
    verbose_name_plural = 'Character Skills'
    readonly_fields = ('skill_name', 'rank')

class CharacterEquipmentInline(admin.StackedInline):
    """Read-only view of a character's equipment."""
    model = CharacterEquipment
    can_delete = False
    verbose_name_plural = 'Character Equipment'
    readonly_fields = [f.name for f in CharacterEquipment._meta.get_fields() if f.name != 'character']

# --- Main Admin Model Configurations ---

@admin.register(Areas)
class AreaAdmin(admin.ModelAdmin):
    list_display = ('name', 'id')
    search_fields = ('name', 'description')

@admin.register(Rooms)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('name', 'id', 'area')
    list_filter = ('area',)
    search_fields = ('name', 'description')
    inlines = [ExitsInline, RoomObjectsInline]  # <-- RoomObjectsInline is now included!
    exclude = ('exits')

@admin.register(MobTemplates)
class MobTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'id', 'level')
    search_fields = ('name',)
    list_filter = ('level', 'mob_type')
    # Embed both attacks and loot tables for a complete editing experience
    inlines = [MobAttacksInline, MobLootTableInline]
    # Exclude the old, now-deprecated JSON fields
    exclude = ('attacks', 'loot')

@admin.register(Characters)
class CharacterAdmin(admin.ModelAdmin):
    """A read-only view for player characters, useful for support and debugging."""
    list_display = ('first_name', 'last_name', 'player', 'level', 'race', 'class_field')
    search_fields = ('first_name', 'last_name', 'player__username')
    inlines = [CharacterStatsInline, CharacterSkillsInline, CharacterEquipmentInline]

    # Make the entire character admin read-only to prevent accidental edits
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False
    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(ItemTemplates)
class ItemTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'id', 'type', 'damage_type')
    search_fields = ('name', 'description')
    list_filter = ('type',)

# --- Register all other models with the default admin interface ---
# These can be customized later if needed.

admin.site.register(Players)
admin.site.register(Races)
admin.site.register(Classes)
admin.site.register(DamageTypes)
admin.site.register(ItemInstances)
admin.site.register(ShopInventories)
admin.site.register(BankAccounts)
admin.site.register(RoomObjects)
admin.site.register(AbilityTemplates)