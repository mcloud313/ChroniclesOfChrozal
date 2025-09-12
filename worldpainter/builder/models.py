# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class AbilityTemplates(models.Model):
    internal_name = models.TextField(unique=True)
    name = models.TextField()
    ability_type = models.TextField()
    class_req = models.JSONField(blank=True, null=True)
    level_req = models.IntegerField(blank=True, null=True)
    cost = models.IntegerField(blank=True, null=True)
    target_type = models.TextField(blank=True, null=True)
    effect_type = models.TextField(blank=True, null=True)
    effect_details = models.JSONField(blank=True, null=True)
    cast_time = models.FloatField(blank=True, null=True)
    roundtime = models.FloatField(blank=True, null=True)
    messages = models.JSONField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'ability_templates'


class Areas(models.Model):
    name = models.TextField(unique=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'areas'


class AuthGroup(models.Model):
    name = models.CharField(unique=True, max_length=150)

    class Meta:
        managed = False
        db_table = 'auth_group'


class AuthGroupPermissions(models.Model):
    id = models.BigAutoField(primary_key=True)
    group = models.ForeignKey(AuthGroup, models.DO_NOTHING)
    permission = models.ForeignKey('AuthPermission', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_group_permissions'
        unique_together = (('group', 'permission'),)


class AuthPermission(models.Model):
    name = models.CharField(max_length=255)
    content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING)
    codename = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'auth_permission'
        unique_together = (('content_type', 'codename'),)


class AuthUser(models.Model):
    password = models.CharField(max_length=128)
    last_login = models.DateTimeField(blank=True, null=True)
    is_superuser = models.BooleanField()
    username = models.CharField(unique=True, max_length=150)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.CharField(max_length=254)
    is_staff = models.BooleanField()
    is_active = models.BooleanField()
    date_joined = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'auth_user'


class AuthUserGroups(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)
    group = models.ForeignKey(AuthGroup, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_user_groups'
        unique_together = (('user', 'group'),)


class AuthUserUserPermissions(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)
    permission = models.ForeignKey(AuthPermission, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_user_user_permissions'
        unique_together = (('user', 'permission'),)


class BankAccounts(models.Model):
    character = models.OneToOneField('Characters', models.DO_NOTHING, primary_key=True)
    balance = models.BigIntegerField()

    class Meta:
        managed = False
        db_table = 'bank_accounts'


class BankedItems(models.Model):
    character = models.ForeignKey('Characters', models.DO_NOTHING)
    item_instance = models.OneToOneField('ItemInstances', models.DO_NOTHING)
    stored_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'banked_items'


class Characters(models.Model):
    player = models.ForeignKey('Players', models.DO_NOTHING)
    first_name = models.TextField()
    last_name = models.TextField()
    sex = models.TextField()
    race = models.ForeignKey('Races', models.DO_NOTHING, blank=True, null=True)
    class_field = models.ForeignKey('Classes', models.DO_NOTHING, db_column='class_id', blank=True, null=True)  # Field renamed because it was a Python reserved word.
    level = models.IntegerField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    hp = models.FloatField(blank=True, null=True)
    max_hp = models.FloatField(blank=True, null=True)
    essence = models.FloatField(blank=True, null=True)
    max_essence = models.FloatField(blank=True, null=True)
    spiritual_tether = models.IntegerField(blank=True, null=True)
    xp_pool = models.FloatField(blank=True, null=True)
    xp_total = models.FloatField(blank=True, null=True)
    status = models.TextField()
    stance = models.TextField()
    unspent_skill_points = models.IntegerField()
    unspent_attribute_points = models.IntegerField()
    stats = models.JSONField(blank=True, null=True)
    skills = models.JSONField(blank=True, null=True)
    known_spells = models.JSONField(blank=True, null=True)
    known_abilities = models.JSONField(blank=True, null=True)
    location_id = models.IntegerField(blank=True, null=True)
    inventory = models.JSONField(blank=True, null=True)
    equipment = models.JSONField(blank=True, null=True)
    coinage = models.IntegerField()
    created_at = models.DateTimeField()
    last_saved = models.DateTimeField(blank=True, null=True)
    total_playtime_seconds = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'characters'
        unique_together = (('player', 'first_name', 'last_name'),)


class Classes(models.Model):
    name = models.TextField(unique=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'classes'


class DjangoAdminLog(models.Model):
    action_time = models.DateTimeField()
    object_id = models.TextField(blank=True, null=True)
    object_repr = models.CharField(max_length=200)
    action_flag = models.SmallIntegerField()
    change_message = models.TextField()
    content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING, blank=True, null=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'django_admin_log'


class DjangoContentType(models.Model):
    app_label = models.CharField(max_length=100)
    model = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'django_content_type'
        unique_together = (('app_label', 'model'),)


class DjangoMigrations(models.Model):
    id = models.BigAutoField(primary_key=True)
    app = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    applied = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'django_migrations'


class DjangoSession(models.Model):
    session_key = models.CharField(primary_key=True, max_length=40)
    session_data = models.TextField()
    expire_date = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'django_session'


class GameEconomy(models.Model):
    key = models.TextField(primary_key=True)
    value = models.BigIntegerField()

    class Meta:
        managed = False
        db_table = 'game_economy'


class ItemInstances(models.Model):
    id = models.UUIDField(primary_key=True)
    template = models.ForeignKey('ItemTemplates', models.DO_NOTHING)
    owner_char = models.ForeignKey(Characters, models.DO_NOTHING, blank=True, null=True)
    room = models.ForeignKey('Rooms', models.DO_NOTHING, blank=True, null=True)
    container = models.ForeignKey('self', models.DO_NOTHING, blank=True, null=True)
    condition = models.IntegerField()
    instance_stats = models.JSONField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'item_instances'


class ItemTemplates(models.Model):
    name = models.TextField(unique=True)
    description = models.TextField(blank=True, null=True)
    type = models.TextField()
    stats = models.JSONField(blank=True, null=True)
    flags = models.JSONField(blank=True, null=True)
    damage_type = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'item_templates'


class MobTemplates(models.Model):
    name = models.TextField(unique=True)
    description = models.TextField(blank=True, null=True)
    mob_type = models.TextField(blank=True, null=True)
    level = models.IntegerField()
    stats = models.JSONField(blank=True, null=True)
    max_hp = models.IntegerField()
    attacks = models.JSONField(blank=True, null=True)
    loot = models.JSONField(blank=True, null=True)
    flags = models.JSONField(blank=True, null=True)
    respawn_delay_seconds = models.IntegerField(blank=True, null=True)
    variance = models.JSONField(blank=True, null=True)
    movement_chance = models.FloatField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'mob_templates'


class Players(models.Model):
    username = models.TextField(unique=True)
    hashed_password = models.TextField()
    email = models.TextField(unique=True)
    is_admin = models.BooleanField()
    created_at = models.DateTimeField()
    last_login = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'players'


class Races(models.Model):
    name = models.TextField(unique=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'races'


class RoomObjects(models.Model):
    room = models.ForeignKey('Rooms', models.DO_NOTHING)
    name = models.TextField()
    description = models.TextField(blank=True, null=True)
    keywords = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'room_objects'
        unique_together = (('room', 'name'),)


class Rooms(models.Model):
    area = models.ForeignKey(Areas, models.DO_NOTHING)
    name = models.TextField()
    description = models.TextField(blank=True, null=True)
    exits = models.JSONField(blank=True, null=True)
    flags = models.JSONField(blank=True, null=True)
    spawners = models.JSONField(blank=True, null=True)
    coinage = models.IntegerField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'rooms'


class ShopInventories(models.Model):
    room = models.ForeignKey(Rooms, models.DO_NOTHING)
    item_template = models.ForeignKey(ItemTemplates, models.DO_NOTHING)
    stock_quantity = models.IntegerField()
    buy_price_modifier = models.FloatField()
    sell_price_modifier = models.FloatField()

    class Meta:
        managed = False
        db_table = 'shop_inventories'
        unique_together = (('room', 'item_template'),)
