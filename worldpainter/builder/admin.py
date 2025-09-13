from django.contrib import admin
from .models import (
    AbilityTemplates, 
    Areas, 
    Characters, 
    ItemTemplates, 
    MobTemplates, 
    Rooms,
    Players,
    Races,
    Classes,
    ShopInventories,
    BankAccounts
)
from .forms import RoomAdminForm, EXIT_DIRECTIONS, MobTemplateAdminForm, STAT_NAMES

# --- Custom Admin for Rooms ---
class RoomAdmin(admin.ModelAdmin):
    form = RoomAdminForm
    list_display = ('name', 'id', 'area')
    list_filter = ('area',)
    search_fields = ('name', 'description')

    def save_model(self, request, obj, form, change):
        exits_json = {}
        for direction in EXIT_DIRECTIONS:
            target_room = form.cleaned_data.get(f'{direction}_exit')
            if target_room:
                exits_json[direction] = target_room.id
        obj.exits = exits_json

        # Build spawners_json
        spawners_json = {}
        for i in range(1, 6): # Loop through our 5 spawner slots
            mob_template = form.cleaned_data.get(f'spawner_mob_{i}')
            max_present = form.cleaned_data.get(f'spawner_count_{i}')
            
            if mob_template and max_present:
                spawners_json[str(mob_template.id)] = {"max_present": max_present}
        
        obj.spawners = spawners_json
        
        super().save_model(request, obj, form, change)

class MobTemplateAdmin(admin.ModelAdmin):
    form = MobTemplateAdminForm
    list_display = ('name', 'id', 'level')
    search_fields = ('name',)

    def save_model(self, request, obj, form, change):
        """
        Builds the 'loot' JSON object from the custom form fields before saving.
        """
        loot_json = {}
        
        # Get coinage
        coinage_max = form.cleaned_data.get('loot_coinage_max')
        if coinage_max is not None:
            loot_json['coinage_max'] = coinage_max
        
        # Get item drops
        item_drops = []
        for i in range(1, 6): # Loop through our 5 loot slots
            item_template = form.cleaned_data.get(f'loot_item_{i}')
            chance = form.cleaned_data.get(f'loot_chance_{i}')
            
            # Only add the drop if both an item and a chance are provided
            if item_template and chance is not None:
                item_drops.append({
                    "template_id": item_template.id,
                    "chance": chance
                })
        
        if item_drops:
            loot_json['items'] = item_drops
        
        # Assign the newly constructed JSON to the mob's loot field
        obj.loot = loot_json

        # Build flags json
        obj.flags = form.cleaned_data.get('flags', [])

        # Build stats_json
        stats_json = {}
        for stat_name in STAT_NAMES: 
            stats_json[stat_name] = form.cleaned_data.get(f'stat_{stat_name}', 10)
        obj.stats = stats_json
        
        # Call the original save method
        super().save_model(request, obj, form, change)


# --- Register all the models ---

# Register models with custom admin classes
admin.site.register(Rooms, RoomAdmin)
admin.site.register(MobTemplates, MobTemplateAdmin)

# Register all other models with their default admin interface
admin.site.register(AbilityTemplates)
admin.site.register(Areas)
admin.site.register(Characters)
admin.site.register(ItemTemplates)
admin.site.register(Players)
admin.site.register(Races)
admin.site.register(Classes)
admin.site.register(ShopInventories)
admin.site.register(BankAccounts)