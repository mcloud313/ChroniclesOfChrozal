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
from .forms import RoomAdminForm, EXIT_DIRECTIONS

# We create a custom admin class for the Rooms model
class RoomAdmin(admin.ModelAdmin):
    # Tell the admin to use our new form for creating/editing rooms
    form = RoomAdminForm

    # These fields improve the list view of all rooms
    list_display = ('name', 'id', 'area')
    list_filter = ('area',)
    search_fields = ('name', 'description')

    def save_model(self, request, obj, form, change):
        """
        This special method runs when you click "Save" in the admin.
        It builds the exits JSON from our custom form fields.
        """
        exits_json = {}
        for direction in EXIT_DIRECTIONS:
            # Get the selected Room object from the form's data for each direction
            field_name = f'{direction}_exit'
            target_room = form.cleaned_data.get(field_name)
            if target_room:
                # Add the exit to our JSON dictionary, storing the target room's ID
                exits_json[direction] = target_room.id
        
        # Assign the newly constructed JSON to the room's 'exits' field
        obj.exits = exits_json
        
        # Call the original save method to save the object to the database
        super().save_model(request, obj, form, change)

# --- Register all the models ---

# First, un-register the default Room admin
admin.site.unregister(Rooms)
# Now, re-register Rooms using our custom RoomAdmin class
admin.site.register(Rooms, RoomAdmin)

# Register all other models with their default admin interface
admin.site.register(AbilityTemplates)
admin.site.register(Areas)
admin.site.register(Characters)
admin.site.register(ItemTemplates)
admin.site.register(MobTemplates)
admin.site.register(Players)
admin.site.register(Races)
admin.site.register(Classes)
admin.site.register(ShopInventories)
admin.site.register(BankAccounts)