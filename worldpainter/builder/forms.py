# worldpainter/builder/forms.py
import json
from django import forms
# --- FIX: Import the missing models ---
from .models import Rooms, MobTemplates, ItemTemplates, Classes, AbilityTemplates
from game.definitions.item_defs import ITEM_TYPE_CHOICES
from game.definitions import abilities as ability_defs
from game.definitions import slots

# Wear location choices for dropdowns, now matching slots.py
WEAR_LOCATION_CHOICES = [
    ("", "---------"),
    (slots.WIELD_MAIN, "Main Hand"),
    (slots.WIELD_OFF, "Off Hand"),
    (slots.ARMOR_HEAD, "Head"),
    (slots.ACCESSORY_NECK, "Neck"),
    (slots.ARMOR_SHOULDERS, "Shoulders"),
    (slots.ARMOR_TORSO, "Torso"),
    (slots.ACCESSORY_BACK, "Back"),
    (slots.ACCESSORY_CLOAK, "Cloak"),
    (slots.ARMOR_ARMS, "Arms"),
    (slots.ARMOR_HANDS, "Hands"),
    (slots.ACCESSORY_WRIST_L, "Wrist (L)"),
    (slots.ACCESSORY_FINGER_L, "Finger (L)"),
    (slots.ACCESSORY_WRIST_R, "Wrist (R)"),
    (slots.ACCESSORY_FINGER_R, "Finger (R)"),
    (slots.ACCESSORY_WAIST, "Waist"),
    (slots.ARMOR_LEGS, "Legs"),
    (slots.ARMOR_FEET, "Feet"),
]

class RoomAdminForm(forms.ModelForm):
    # --- Spawner Fields ---
    spawner_1_mob = forms.ModelChoiceField(queryset=MobTemplates.objects.all(), required=False, label="Spawner 1: Mob")
    spawner_1_count = forms.IntegerField(min_value=1, required=False, label="Max Count")

    spawner_2_mob = forms.ModelChoiceField(queryset=MobTemplates.objects.all(), required=False, label="Spawner 2: Mob")
    spawner_2_count = forms.IntegerField(min_value=1, required=False, label="Max Count")

    spawner_3_mob = forms.ModelChoiceField(queryset=MobTemplates.objects.all(), required=False, label="Spawner 3: Mob")
    spawner_3_count = forms.IntegerField(min_value=1, required=False, label="Max Count")
    
    # You can add more spawner slots here if needed

    class Meta:
        model = Rooms
        # FIX: Explicitly list fields instead of using 'exclude'.
        # This ensures the form is aware of the 'spawners' field
        # but doesn't display its raw text box.
        fields = [
            'area', 'name', 'description', 'flags', 'coinage', 'spawners'
        ]
        widgets = {
            'spawners': forms.HiddenInput(),
        }


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate the spawner fields from the existing JSON data
        if self.instance and self.instance.spawners:
            for i, (mob_id, spawn_info) in enumerate(self.instance.spawners.items(), 1):
                if i > 5: break
                try:
                    self.fields[f'spawner_{i}_mob'].initial = mob_id
                    self.fields[f'spawner_{i}_count'].initial = spawn_info.get('max_present')
                except (ValueError, TypeError, KeyError):
                    continue

    def save(self, commit=True):
        # Build the JSON from our form fields before saving
        spawners_json = {}
        for i in range(1, 6):
            # Use self.cleaned_data which is available after validation
            mob = self.cleaned_data.get(f'spawner_{i}_mob')
            count = self.cleaned_data.get(f'spawner_{i}_count')
            if mob and count:
                spawners_json[str(mob.id)] = {"max_present": count}
        
        # Assign the generated JSON to the instance's spawners field
        self.instance.spawners = spawners_json
        
        # Call the parent save method to save the instance to the database
        return super().save(commit)

class ItemTemplateAdminForm(forms.ModelForm):
    """A custom form to manage the 'stats' JSONField for ItemTemplates."""

    # --- Core Stats ---
    value = forms.IntegerField(required=False, help_text="The base value in coinage for buying/selling.")
    weight = forms.FloatField(required=False, help_text="The weight of the item.")

    # --- Combat Stats (Melee/Ranged) ---
    damage_base = forms.IntegerField(required=False, label="Damage Base")
    damage_rng = forms.IntegerField(required=False, label="Damage Random")
    speed = forms.FloatField(required=False, label="Speed (Roundtime)")
    
    # --- Ranged Weapon Specific ---
    uses_ammo_type = forms.CharField(required=False, label="Uses Ammo Type", help_text="e.g., 'arrow', 'bolt'. Must match ammo's type.")

    # --- Defensive Stats ---
    armor = forms.IntegerField(required=False, label="Armor Value (AV)")
    spell_failure = forms.IntegerField(required=False, label="Spell Failure %", help_text="e.g., 15 for 15%.")
    block_chance = forms.FloatField(required=False, label="Block Chance (Shields)")
    wear_location = forms.MultipleChoiceField(
        choices=WEAR_LOCATION_CHOICES, 
        widget=forms.CheckboxSelectMultiple, 
        required=False
    )

    # --- Container Stats ---
    capacity = forms.IntegerField(required=False, help_text="Max weight a container can hold.")
    holds_ammo_type = forms.CharField(required=False, label="Holds Ammo Type", help_text="For quivers, e.g., 'arrow', 'bolt'.")

    # --- Consumable Stats ---
    effect = forms.CharField(required=False, label="Consumable Effect", help_text="e.g., 'heal_hp'.")
    amount = forms.IntegerField(required=False, label="Effect Amount")

    # --- Attribute Bonuses ---
    bonus_might = forms.IntegerField(required=False)
    bonus_vitality = forms.IntegerField(required=False)
    bonus_agility = forms.IntegerField(required=False)
    bonus_intellect = forms.IntegerField(required=False)
    bonus_aura = forms.IntegerField(required=False)
    bonus_persona = forms.IntegerField(required=False)

    class Meta:
        model = ItemTemplates
        fields = '__all__'
        widgets = {
            'stats': forms.HiddenInput(), # Hide the raw JSON field
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.stats:
            if isinstance(self.instance.stats, dict):
                for key, value in self.instance.stats.items():
                    if key in self.fields:
                        self.fields[key].initial = value

    def save(self, commit=True):
        stats_json = {}
        stat_field_names = [
            'value', 'weight', 'damage_base', 'damage_rng', 'speed', 'uses_ammo_type',
            'armor', 'spell_failure', 'block_chance', 'wear_location', 'capacity',
            'holds_ammo_type', 'effect', 'amount', 'bonus_might', 'bonus_vitality',
            'bonus_agility', 'bonus_intellect', 'bonus_aura', 'bonus_persona'
        ]
        
        for field_name in stat_field_names:
             value = self.cleaned_data.get(field_name)
             if value is not None and value != '':
                stats_json[field_name] = value
        
        self.instance.stats = stats_json if stats_json else None
        return super().save(commit)
    
class MobTemplateAdminForm(forms.ModelForm):
    """A custom form to manage the 'stats' JSONField for MobTemplates."""
    
    # Define individual fields for mob stats
    might = forms.IntegerField(required=False)
    vitality = forms.IntegerField(required=False)
    agility = forms.IntegerField(required=False)
    intellect = forms.IntegerField(required=False)
    aura = forms.IntegerField(required=False)
    persona = forms.IntegerField(required=False)

    class Meta:
        model = MobTemplates
        fields = '__all__'
        widgets = {
            'stats': forms.HiddenInput(), # Hide the raw JSON field
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate fields from existing stats JSON
        if self.instance and self.instance.stats:
            for key, value in self.instance.stats.items():
                if key in self.fields:
                    self.fields[key].initial = value

    def save(self, commit=True):
        # Build the stats JSON from form fields
        stats_json = {}
        stat_fields = ['might', 'vitality', 'agility', 'intellect', 'aura', 'persona']
        for field_name in stat_fields:
            value = self.cleaned_data.get(field_name)
            if value is not None:
                stats_json[field_name] = value
        
        self.instance.stats = stats_json if stats_json else None
        return super().save(commit)
    

# Choices for ability dropdowns
ABILITY_TYPE_CHOICES = [("SPELL", "Spell"), ("ABILITY", "Ability")]
TARGET_TYPE_CHOICES = [
    (ability_defs.TARGET_SELF, "Self"),
    (ability_defs.TARGET_CHAR, "Character Only"),
    (ability_defs.TARGET_MOB, "Mob Only"),
    (ability_defs.TARGET_CHAR_OR_MOB, "Character or Mob"),
    (ability_defs.TARGET_AREA, "Area of Effect"),
    (ability_defs.TARGET_NONE, "No Target"),
]
EFFECT_TYPE_CHOICES = [
    (ability_defs.EFFECT_DAMAGE, "Damage"),
    (ability_defs.EFFECT_HEAL, "Heal"),
    (ability_defs.EFFECT_BUFF, "Buff"),
    (ability_defs.EFFECT_DEBUFF, "Debuff"),
    (ability_defs.EFFECT_MODIFIED_ATTACK, "Modified Attack"),
    ("CURE", "Cure"),
    ("RESURRECT", "Resurrect"),
]

class AbilityTemplateAdminForm(forms.ModelForm):
    # Make dropdowns for choice fields
    ability_type = forms.ChoiceField(choices=ABILITY_TYPE_CHOICES)
    target_type = forms.ChoiceField(choices=TARGET_TYPE_CHOICES)
    effect_type = forms.ChoiceField(choices=EFFECT_TYPE_CHOICES)

    # Use a checkbox widget for class requirements
    class_req_choices = [(c.name.lower(), c.name) for c in Classes.objects.all()]
    class_req = forms.MultipleChoiceField(choices=class_req_choices, widget=forms.CheckboxSelectMultiple, required=False)
    
    # Use Textarea for complex JSON fields, with extensive help text
    effect_details_help = """
    Examples:<br>
    <b>Damage:</b> {"damage_base": 10, "damage_rng": 5, "damage_type": "fire", "school": "Arcane"}<br>
    <b>Buff:</b> {"name": "Rage", "type": "buff", "stat_affected": "might", "amount": 5, "duration": 30.0}<br>
    <b>Modified Attack:</b> {"damage_multiplier": 1.5, "bonus_mar": 10}<br>
    <b>AoE Heal:</b> {"aoe_target_scope": "allies", "heal_base": 15, "heal_rng": 10}
    """
    effect_details = forms.CharField(widget=forms.Textarea(attrs={'rows': 10, 'cols': 80}), required=False, help_text=effect_details_help)
    
    messages_help = """
    Example:<br>
    {"caster_self_complete": "A bolt of fire erupts!", "room_complete": "{caster_name} hurls a bolt of fire!"}
    """
    messages = forms.CharField(widget=forms.Textarea(attrs={'rows': 5, 'cols': 80}), required=False, help_text=messages_help)

    class Meta:
        model = AbilityTemplates
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate JSON fields if editing an existing instance
        if self.instance:
            if self.instance.class_req:
                self.fields['class_req'].initial = self.instance.class_req
            if self.instance.effect_details:
                self.fields['effect_details'].initial = json.dumps(self.instance.effect_details, indent=2)
            if self.instance.messages:
                self.fields['messages'].initial = json.dumps(self.instance.messages, indent=2)

    def save(self, commit=True):
        # Convert form data back into JSON for the model
        self.instance.class_req = self.cleaned_data.get('class_req')
        try:
            self.instance.effect_details = json.loads(self.cleaned_data.get('effect_details') or '{}')
        except json.JSONDecodeError:
            # Handle potential bad JSON from user input
            self.add_error('effect_details', 'Invalid JSON format.')
            return super().save(commit=False)
        try:
            self.instance.messages = json.loads(self.cleaned_data.get('messages') or '{}')
        except json.JSONDecodeError:
            self.add_error('messages', 'Invalid JSON format.')
            return super().save(commit=False)
            
        return super().save(commit)