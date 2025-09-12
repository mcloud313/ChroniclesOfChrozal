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

# These lines tell the Django admin to create a full interface for each of your tables.
admin.site.register(AbilityTemplates)
admin.site.register(Areas)
admin.site.register(Characters)
admin.site.register(ItemTemplates)
admin.site.register(MobTemplates)
admin.site.register(Rooms)
admin.site.register(Players)
admin.site.register(Races)
admin.site.register(Classes)
admin.site.register(ShopInventories)
admin.site.register(BankAccounts)