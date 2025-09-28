import json
from django import forms
from .models import Rooms, MobTemplates, ItemTemplates, Classes, AbilityTemplates, Exits
from game.definitions.item_defs import ITEM_TYPE_CHOICES
from game.definitions import abilities as ability_defs
from game.definitions import slots
from django.core.exceptions import ValidationError


# Wear location choices for dropdowns, now matching slots.py
WEAR_LOCATION_CHOICES = [
    ("", "---------"),
    (slots.WIELD_MAIN, "Main Hand"),
    (slots.WIELD_OFF, "Off Hand"),
    (slots.ARMOR_HEAD, "Head"),
    (slots.ARMOR_TORSO, "Torso"),
    (slots.ARMOR_LEGS, "Legs"),
    (slots.ARMOR_FEET, "Feet"),
    (slots.ARMOR_HANDS, "Hands"),
    (slots.ARMOR_SHOULDERS, "Shoulders"),
    (slots.ACCESSORY_NECK, "Neck"),
    (slots.ACCESSORY_FINGER_L, "Finger (Left)"),
    (slots.ACCESSORY_FINGER_R, "Finger (Right)"),
    (slots.ACCESSORY_WRIST_L, "Wrist (Left)"),
    (slots.ACCESSORY_WRIST_R, "Wrist (Right)"),
    (slots.ACCESSORY_WAIST, "Waist"),
    (slots.ACCESSORY_CLOAK, "Cloak"),
    (slots.BACK, "Back"),
    # --------------------------------
]

class RoomAdminForm(forms.ModelForm):
    # --- Spawner Fields ---
    # Define fields with a temporary empty queryset to avoid DB access on import
    spawner_1_mob = forms.ModelChoiceField(queryset=MobTemplates.objects.none(), required=False, label="Spawner 1: Mob")
    spawner_1_count = forms.IntegerField(min_value=1, required=False, label="Max Count")
    spawner_2_mob = forms.ModelChoiceField(queryset=MobTemplates.objects.none(), required=False, label="Spawner 2: Mob")
    spawner_2_count = forms.IntegerField(min_value=1, required=False, label="Max Count")
    spawner_3_mob = forms.ModelChoiceField(queryset=MobTemplates.objects.none(), required=False, label="Spawner 3: Mob")
    spawner_3_count = forms.IntegerField(min_value=1, required=False, label="Max Count")
    
    class Meta:
        model = Rooms
        fields = [
            'area', 'name', 'description', 'flags', 'coinage', 'spawners'
        ]
        widgets = {
            'spawners': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # --- FIX: Set the real queryset here, inside the __init__ method ---
        mob_queryset = MobTemplates.objects.all()
        self.fields['spawner_1_mob'].queryset = mob_queryset
        self.fields['spawner_2_mob'].queryset = mob_queryset
        self.fields['spawner_3_mob'].queryset = mob_queryset
        # --- END FIX ---
        
        # Populate the spawner fields from the existing JSON data
        if self.instance and self.instance.spawners:
            for i, (mob_id, spawn_info) in enumerate(self.instance.spawners.items(), 1):
                if i > 3: break # Ensure this matches the number of spawner fields
                try:
                    self.fields[f'spawner_{i}_mob'].initial = mob_id
                    self.fields[f'spawner_{i}_count'].initial = spawn_info.get('max_present')
                except (ValueError, TypeError, KeyError):
                    continue

    def save(self, commit=True):
        # Build the JSON from our form fields before saving
        spawners_json = {}
        for i in range(1, 4): # Ensure this matches the number of spawner fields
            mob = self.cleaned_data.get(f'spawner_{i}_mob')
            count = self.cleaned_data.get(f'spawner_{i}_count')
            if mob and count:
                spawners_json[str(mob.id)] = {"max_present": count}
        
        self.instance.spawners = spawners_json
        return super().save(commit)
    
class ExitAdminForm(forms.ModelForm):
    """Provides a textarea for the 'details' JSON field on Exits."""
    details_help = """
    <strong>Enter valid JSON.</strong> Use double quotes for keys and string values.<br><br>
    <strong><u>Locked Door Example:</u></strong><br>
    <code>{"is_locked": true, "lockpick_dc": 20, "key_name": "a rusty key"}</code><br>
    <em>- `is_locked`: (true/false) If the exit is locked by default.</em><br>
    <em>- `lockpick_dc`: (number) The difficulty to pick the lock.</em><br>
    <em>- `key_name`: (string) The name of the item that unlocks this exit.</em><br><br>

    <strong><u>Skill Check Example:</u></strong><br>
    <code>{"skill_check": {"skill": "climbing", "dc": 15, "fail_msg": "You slip and fall!"}}</code><br>
    <em>- `skill`: The name of the required skill (e.g., climbing, swimming).</em><br>
    <em>- `dc`: (number) The difficulty of the check.</em><br>
    <em>- `fail_msg`: (string) Message shown on failure.</em><br><br>

    <strong><u>Combined Example (Locked & Climbable):</u></strong><br>
    <code>{"is_locked": true, "lockpick_dc": 25, "skill_check": {"skill": "athletics", "dc": 12}}</code>
    """
    details = forms.CharField(widget=forms.Textarea(attrs={'rows': 15, 'cols': 60}), required=False, help_text=details_help)

    class Meta:
        model = Exits
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate the textarea from the existing JSON data, formatted nicely
        if self.instance and self.instance.details:
            self.fields['details'].initial = json.dumps(self.instance.details, indent=2)

    def save(self, commit=True):
        # Convert the string from the textarea back into JSON before saving
        try:
            self.instance.details = json.loads(self.cleaned_data.get('details') or '{}')
        except json.JSONDecodeError:
            # If the user enters invalid JSON, add an error to the form instead of crashing
            self.add_error('details', 'Invalid JSON format.')
            return super().save(commit=False)
        return super().save(commit)

class ItemTemplateAdminForm(forms.ModelForm):
    """A custom form to manage the 'stats' JSONField for ItemTemplates."""
    # This form is correct and does not need changes
    lock_details_help = """
    <strong>Enter valid JSON.</strong> Use double quotes.<br><br>
    <strong><u>Example:</u></strong><br>
    <code>{"is_locked": true, "lockpick_dc": 25, "key_name": "a small iron key"}</code><br>
    <em>- `is_locked`: (true/false) If the container is locked by default.</em><br>
    <em>- `lockpick_dc`: (number) The difficulty to pick the lock.</em><br>
    <em>- `key_name`: (string, optional) The name of the item that unlocks this.</em>
    """
    trap_details_help = """
    <strong>Enter valid JSON.</strong> Use double quotes.<br><br>
    <strong><u>Example:</u></strong><br>
    <code>{"is_active": true, "perception_dc": 18, "disarm_dc": 20, "damage": 50}</code><br>
    <em>- `is_active`: (true/false) If the trap is armed by default.</em><br>
    <em>- `perception_dc`: (number) The difficulty to notice the trap.</em><br>
    <em>- `disarm_dc`: (number) The difficulty to disarm the trap.</em><br>
    <em>- `damage`: (number, optional) Amount of damage the trap deals.</em>
    """

    # --- Core Stats ---
    value = forms.IntegerField(required=False, help_text="The base value in coinage for buying/selling.")
    weight = forms.FloatField(required=False, help_text="The weight of the item.")
    # ... (rest of the fields are correct)
    damage_base = forms.IntegerField(required=False, label="Damage Base")
    damage_rng = forms.IntegerField(required=False, label="Damage Random")
    speed = forms.FloatField(required=False, label="Speed (Roundtime)")
    uses_ammo_type = forms.CharField(required=False, label="Uses Ammo Type", help_text="e.g., 'arrow', 'bolt'. Must match ammo's type.")
    armor = forms.IntegerField(required=False, label="Armor Value (AV)")
    spell_failure = forms.IntegerField(required=False, label="Spell Failure %", help_text="e.g., 15 for 15%.")
    block_chance = forms.FloatField(required=False, label="Block Chance (Shields)")
    wear_location = forms.MultipleChoiceField(
        choices=WEAR_LOCATION_CHOICES, 
        widget=forms.CheckboxSelectMultiple, 
        required=False
    )
    lock_details = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4, 'cols': 60}),
        required=False,
        help_text=lock_details_help
    )
    trap_details = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4, 'cols': 60}),
        required=False,
        help_text=trap_details_help
    )
    capacity = forms.IntegerField(required=False, help_text="Max weight a container can hold.")
    holds_ammo_type = forms.CharField(required=False, label="Holds Ammo Type", help_text="For quivers, e.g., 'arrow', 'bolt'.")
    effect = forms.CharField(required=False, label="Consumable Effect", help_text="e.g., 'heal_hp'.")
    amount = forms.IntegerField(required=False, label="Effect Amount")
    bonus_might = forms.IntegerField(required=False)
    bonus_vitality = forms.IntegerField(required=False)
    bonus_agility = forms.IntegerField(required=False)
    bonus_intellect = forms.IntegerField(required=False)
    bonus_aura = forms.IntegerField(required=False)
    bonus_persona = forms.IntegerField(required=False)

    class Meta:
        model = ItemTemplates
        # Add the new fields to the form
        fields = ['name', 'description', 'item_type', 'flags', 'wear_location', 'stats', 'loot_table', 'lock_details', 'trap_details']
        widgets = {
            'stats': forms.Textarea(attrs={'rows': 10, 'cols': 60}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.stats:
            if isinstance(self.instance.stats, dict):
                for key, value in self.instance.stats.items():
                    if key in self.fields:
                        self.fields[key].initial = value
            if self.instance.lock_details:
                self.fields['lock_details'].initial = json.dumps(self.instance.lock_details, indent=2)
            if self.instance.trap_details:
                self.fields['trap_details'].initial = json.dumps(self.instance.trap_details, indent=2)

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

        try:
            self.instance.lock_details = json.loads(self.cleaned_data.get('lock_details') or '{}')
        except json.JSONDecodeError:
            self.add_error('lock_details', 'Invalid JSON format.')
        try:
            self.instance.trap_details = json.loads(self.cleaned_data.get('trap_details') or '{}')
        except json.JSONDecodeError:
            self.add_error('trap_details', 'Invalid JSON format.')
        
        self.instance.stats = stats_json if stats_json else None
        return super().save(commit)
    
class MobTemplateAdminForm(forms.ModelForm):
    """A custom form to manage the 'stats' JSONField for MobTemplates."""
    # This form is correct and does not need changes
    
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
            'stats': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.stats:
            for key, value in self.instance.stats.items():
                if key in self.fields:
                    self.fields[key].initial = value

    def save(self, commit=True):
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
    ability_type = forms.ChoiceField(choices=ABILITY_TYPE_CHOICES)
    target_type = forms.ChoiceField(choices=TARGET_TYPE_CHOICES)
    effect_type = forms.ChoiceField(choices=EFFECT_TYPE_CHOICES)

    # Define field with temporary empty choices to avoid DB access on import
    class_req = forms.MultipleChoiceField(choices=[], widget=forms.CheckboxSelectMultiple, required=False)
    
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
        # --- FIX: Set the real choices here, inside the __init__ method ---
        self.fields['class_req'].choices = [(c.name.lower(), c.name) for c in Classes.objects.all()]
        # --- END FIX ---

        if self.instance:
            if self.instance.class_req:
                self.fields['class_req'].initial = self.instance.class_req
            if self.instance.effect_details:
                self.fields['effect_details'].initial = json.dumps(self.instance.effect_details, indent=2)
            if self.instance.messages:
                self.fields['messages'].initial = json.dumps(self.instance.messages, indent=2)


    def save(self, commit=True):
        self.instance.class_req = self.cleaned_data.get('class_req')
        try:
            self.instance.effect_details = json.loads(self.cleaned_data.get('effect_details') or '{}')
        except json.JSONDecodeError:
            self.add_error('effect_details', 'Invalid JSON format.')
            return super().save(commit=False)
        try:
            self.instance.messages = json.loads(self.cleaned_data.get('messages') or '{}')
        except json.JSONDecodeError:
            self.add_error('messages', 'Invalid JSON format.')
            return super().save(commit=False)

        return super().save(commit)

        
    def clean(self):
        """
        Custom validation for the effect_details JSON field based on the
        selected effect_type.
        """
        cleaned_data = super().clean()
        effect_type = cleaned_data.get("effect_type")
        effect_details = cleaned_data.get("effect_details", {})
        damage_type = cleaned_data.get("damage_type")

        if not isinstance(effect_details, dict):
            raise ValidationError("Effect Details must be a valid JSON object (e.g., {\"key\": \"value\"}).")

        # Validation for DAMAGE or HEAL effects
        if effect_type in [ability_defs.EFFECT_DAMAGE, ability_defs.EFFECT_HEAL]:
            if "damage_type" not in effect_details:
                raise ValidationError("For DAMAGE/HEAL, 'effect_details' must contain 'damage_type'.")
            if "damage_base" not in effect_details:
                raise ValidationError("For DAMAGE/HEAL, 'effect_details' must contain 'damage_base'.")
            if "damage_rng" not in effect_details:
                raise ValidationError("For DAMAGE/HEAL, 'effect_details' must contain 'damage_rng'.")
 
        # If the damage spell also applies a secondary effect, validate it.
            if secondary_effect := effect_details.get("applies_effect"):
                if not isinstance(secondary_effect, dict):
                    raise ValidationError("'applies_effect' must be a dictionary.")
                if "name" not in secondary_effect:
                    raise ValidationError("The 'applies_effect' dictionary must have a 'name'.")
                if "duration" not in secondary_effect:
                    raise ValidationError("The 'applies_effect' dictionary must have a 'duration'.")
                if "stat_affected" not in secondary_effect:
                    raise ValidationError("The 'applies_effect' dictionary must have a 'stat_affected'.")

                # Check for 'amount' OR 'potency' to support different effect types.
                if "amount" not in secondary_effect and "potency" not in secondary_effect:
                    raise ValidationError("The 'applies_effect' dictionary must have an 'amount' or 'potency'.")

        # Validation for BUFF or DEBUFF effects
        elif effect_type in [ability_defs.EFFECT_BUFF, ability_defs.EFFECT_DEBUFF]:
            if "name" not in effect_details:
                raise ValidationError("For BUFF/DEBUFF, 'effect_details' must have 'name'.")
            if "duration" not in effect_details:
                raise ValidationError("For BUFF/DEBUFF, 'effect_details' must have 'duration'.")
            if "stat_affected" not in effect_details:
                raise ValidationError("For BUFF/DEBUFF, 'effect_details' must have 'stat_affected'.")
            if "amount" not in effect_details:
                raise ValidationError("For BUFF/DEBUFF, 'effect_details' must have 'amount'.")

        # Data consistency check
        if damage_type and effect_details.get("damage_type") and damage_type != effect_details.get("damage_type"):
            raise ValidationError(
                "The top-level 'Damage Type' and the 'damage_type' in Effect Details must match."
            )

        if not damage_type and effect_details.get("damage_type"):
            cleaned_data["damage_type"] = effect_details.get("damage_type")

        return cleaned_data
