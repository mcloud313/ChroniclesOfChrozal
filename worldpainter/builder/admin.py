# worldpainter/builder/admin.py
from django.contrib import admin
from django.db.models import Count
from .models import (
    Areas, Races, Classes, DamageTypes, ItemTemplates, MobTemplates,
    Rooms, Exits, RoomObjects, MobAttacks, MobLootTable,
    Players, Characters, CharacterStats, CharacterSkills, CharacterEquipment,
    ItemInstances, ShopInventories, BankAccounts, AbilityTemplates
)
from .forms import RoomAdminForm

# --- Helper Dictionaries ---
OPPOSITE_DIRECTIONS = {
    "north": "south", "south": "north", "east": "west", "west": "east",
    "up": "down", "down": "up", "northeast": "southwest", "southwest": "northeast",
    "northwest": "southeast", "southeast": "northwest",
}

# --- Inline Model Admins ---
class ExitsInline(admin.TabularInline):
    model = Exits
    fk_name = 'source_room'
    extra = 1
    verbose_name_plural = "Exits from this Room"

class RoomObjectsInline(admin.TabularInline):
    model = RoomObjects
    extra = 1

class MobAttacksInline(admin.TabularInline):
    model = MobAttacks
    extra = 1

class MobLootTableInline(admin.TabularInline):
    model = MobLootTable
    extra = 1

class CharacterStatsInline(admin.StackedInline):
    model = CharacterStats
    can_delete = False
    readonly_fields = [f.name for f in CharacterStats._meta.get_fields() if f.name != 'character']

class CharacterSkillsInline(admin.TabularInline):
    model = CharacterSkills
    extra = 0
    can_delete = False
    readonly_fields = ('skill_name', 'rank')

class CharacterEquipmentInline(admin.StackedInline):
    model = CharacterEquipment
    can_delete = False
    readonly_fields = [f.name for f in CharacterEquipment._meta.get_fields() if f.name != 'character']


# --- Main Model Admin Configurations ---
@admin.register(Areas)
class AreaAdmin(admin.ModelAdmin):
    list_display = ('name', 'id')
    search_fields = ('name', 'description')

@admin.register(Rooms)
class RoomAdmin(admin.ModelAdmin):
    form = RoomAdminForm
    list_display = ('name', 'id', 'area')
    list_filter = ('area',)
    search_fields = ('name', 'description')
    inlines = [ExitsInline, RoomObjectsInline]
    exclude = ('exits',)

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        if formset.model == Exits:
            for f in formset.forms:
                if not f.is_valid() or f.cleaned_data.get('DELETE'): continue
                exit_instance = f.instance
                opposite_dir = OPPOSITE_DIRECTIONS.get(exit_instance.direction.lower())
                if opposite_dir and not Exits.objects.filter(source_room=exit_instance.destination_room, direction=opposite_dir).exists():
                    Exits.objects.create(
                        source_room=exit_instance.destination_room,
                        direction=opposite_dir,
                        destination_room=exit_instance.source_room,
                        is_hidden=False
                    )

@admin.register(MobTemplates)
class MobTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'id', 'level')
    search_fields = ('name',)
    list_filter = ('level', 'mob_type')
    inlines = [MobAttacksInline, MobLootTableInline]
    exclude = ('attacks', 'loot')

@admin.register(Characters)
class CharacterAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'player', 'level')
    search_fields = ('first_name', 'last_name', 'player__username')
    inlines = [CharacterStatsInline, CharacterSkillsInline, CharacterEquipmentInline]

    # Make most fields read-only, but leave some editable for GM tasks
    readonly_fields = ('player', 'first_name', 'last_name', 'sex', 'race', 
                       'class_field', 'description', 'created_at', 'last_saved', 
                       'total_playtime_seconds')

    # This prevents new characters from being created here
    def has_add_permission(self, request):
        return False

@admin.register(ItemTemplates)
class ItemTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'id', 'type', 'damage_type')
    search_fields = ('name', 'description')
    list_filter = ('type',)

# --- Standard Registration for other models ---
admin.site.register(Players)
admin.site.register(Races)
admin.site.register(Classes)
admin.site.register(DamageTypes)
admin.site.register(ItemInstances)
admin.site.register(ShopInventories)
admin.site.register(BankAccounts)
# We don't register RoomObjects here because it's handled by an Inline
admin.site.register(AbilityTemplates)