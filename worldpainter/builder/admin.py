# worldpainter/builder/admin.py
from django.contrib import admin
from django.db import models
from django.forms import TextInput, Textarea
from .models import (
    Areas, Races, Classes, DamageTypes, ItemTemplates, MobTemplates,
    Rooms, Exits, RoomObjects, MobAttacks, MobLootTable,
    Players, Characters, CharacterStats, CharacterSkills, CharacterEquipment,
    ItemInstances, ShopInventories, BankAccounts, AbilityTemplates, AmbientScripts
)
from .forms import RoomAdminForm, ItemTemplateAdminForm, MobTemplateAdminForm, AbilityTemplateAdminForm, ExitAdminForm # Add new form

# --- Helper Dictionaries ---
OPPOSITE_DIRECTIONS = {
    "north": "south", "south": "north", "east": "west", "west": "east",
    "up": "down", "down": "up", "northeast": "southwest", "southwest": "northeast",
    "northwest": "southeast", "southeast": "northwest",
}

class NameAsCharFieldAdmin(admin.ModelAdmin):
    formfield_overrides = {
        models.TextField: {'widget': TextInput(attrs={'size':'80'})},
    }

# --- Inline Model Admins ---
class ExitsInline(admin.TabularInline):
    model = Exits
    fk_name = 'source_room'
    extra = 1
    verbose_name_plural = "Exits from this Room"
    form = ExitAdminForm

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

    fieldsets = (
        ('Core Details', {'fields': ('area', 'name', 'description', 'flags')}),
        ('Population', {'fields': ('spawner_1_mob', 'spawner_1_count', 'spawner_2_mob', 'spawner_2_count', 'spawner_3_mob', 'spawner_3_count')}),
        ('Shop Logic (Optional)', {
            'classes': ('collapse',),
            'fields': ('shop_buy_filter', 'shop_sell_modifier'),
            # --- UPDATED HELP TEXT ---
            'description': 'Set these fields if the room has the "SHOP" flag. <br><b>Filter Format:</b> {"types": ["WEAPON"], "template_ids": [8, 15]}'
        }),
        ('Treasure', {'fields': ('coinage',)})
    )

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

@admin.register(AmbientScripts)
class AmbientScriptsAdmin(admin.ModelAdmin):
    list_display = ('get_short_script', 'area', 'room')
    list_filter = ('area')
    search_fields = ('script_text',)

    @admin.display(description='Script Text')
    def get_short_script(self, obj):
        if len(obj.script_text) > 80:
            return f"{obj.script_text[:80]}..."
        return obj.script_text

@admin.register(MobTemplates)
class MobTemplateAdmin(admin.ModelAdmin):
    form = MobTemplateAdminForm
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
    form = ItemTemplateAdminForm
    list_display = ('name', 'id', 'item_type', 'get_value')
    search_fields = ('name', 'description')
    list_filter = ('item_type',)

    fieldsets = (
        ('Core Details', {
            'fields': ('name', 'description', 'item_type', 'damage_type', 'flags')
        }),
        ('Core Stats', {
            'fields': ('value', 'weight')
        }),
        ('Combat Stats (Melee)', {
            'fields': ('damage_base', 'damage_rng', 'speed'),
            'classes': ('collapse',)
        }),
        ('Combat Stats (Ranged)', {
            'fields': ('uses_ammo_type',),
            'classes': ('collapse',)
        }),
        ('Defensive Stats', {
            'fields': ('armor', 'spell_failure', 'block_chance', 'wear_location'),
            'classes': ('collapse',)
        }),
        ('Container Stats', {
            'fields': ('capacity', 'holds_ammo_type'),
            'classes': ('collapse',)
        }),
        ('Consumable Effect', {
            'fields': ('effect', 'amount'),
            'classes': ('collapse',)
        }),
        ('Attribute Bonuses', {
            'fields': ('bonus_might', 'bonus_vitality', 'bonus_agility', 'bonus_intellect', 'bonus_aura', 'bonus_persona'),
            'classes': ('collapse',)
        }),
    )

    @admin.display(description='Value')
    def get_value(self, obj):
        if isinstance(obj.stats, dict):
            return obj.stats.get('value', 0)
        return 0

@admin.register(AbilityTemplates)
class AbilityTemplateAdmin(admin.ModelAdmin):
    form = AbilityTemplateAdminForm
    list_display = ('name', 'ability_type', 'get_classes', 'level_req')
    search_fields = ('name', 'internal_name', 'description')
    list_filter = ('ability_type', 'level_req')

    fieldsets = (
        ('Identification', {
            'fields': ('name', 'internal_name', 'description')
        }),
        ('Requirements', {
            'fields': ('ability_type', 'class_req', 'level_req')
        }),
        ('Casting Mechanics', {
            'fields': ('cost', 'target_type', 'cast_time', 'roundtime')
        }),
        ('Effect Definition', {
            'fields': ('effect_type', 'effect_details')
        }),
        ('Messaging', {
            'fields': ('messages',)
        }),
    )

    @admin.display(description='Classes')
    def get_classes(self, obj):
        if isinstance(obj.class_req, list):
            return ", ".join(c.capitalize() for c in obj.class_req)
        return "None"

# --- Standard Registration for other models ---
admin.site.register(Players)
admin.site.register(Races)
admin.site.register(Classes)
admin.site.register(DamageTypes)
admin.site.register(ItemInstances)
admin.site.register(ShopInventories)
admin.site.register(BankAccounts)
admin.site.register(AmbientScripts)
# We don't register RoomObjects here because it's handled by an Inline