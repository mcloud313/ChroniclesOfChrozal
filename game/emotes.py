"""Roleplay actions describe only the acting character, never a target's response."""
from functools import partial
VERBS='''acknowledge admire agree applaud beam beckon blink blush bow breathe brood cackle celebrate cheer chuckle clap cough cringe cry curtsey dance daydream disagree dream drool duck exclaim facepalm fidget flinch frown gasp giggle glare glance grin groan growl grumble gulp hiccup hiss hop howl hum hunch hurry incline jest jiggle jump kneel laugh lean listen lookdown lookaway meditate moan mutter nod pace pant peer ponder pout pray preen quiver recoil relax rejoice restlessly rock roll shuffle shiver shrug sigh sing skip slouch smile smirk snap snarl sneeze sniff sniffle snicker snort sob squint stagger stare stretch strut sulk swagger sway sweat tremble twirl twitch wave weep whistle wink wince wonder worry yawn yelp
abide ache agonize assent balance bemoan bend bob bounce bristle brood calmly caper chatter chortle clench crouch dawdle deflate deliberate despair dither doze droop drum emanate enthuse exhale falter fantasize fret frolic gesture glow gravitate grimace grit grouse guffaw hesitate hobble hover huff hush idle improvise inhale interlace investigate lament linger loiter lounge marvel meander mime mumble muse natter nestle observe oscillate overhear perk philosophize pirouette plod posture prance prowl puff purse quail radiate ramble rant rave reflect relent reminisce respond retreat revel reverie ruffle scoff scowl scrutinize seethe settle shamble shudder simper slink slump smolder sneak sniff snuffle speculate sprawl spring startle stew stiffen stomp stoop stutter stumble swoon tap teeter tense tiptoe totter trudge turn tut vacillate vibrate waddle wag wander warm wobble wriggle writhe zip
salute point finger shake flex thank welcome greet apologize congratulate comfort mourn salute ponder ponderously salute nod yes no salute'''.split()
# Avoid vague/incomplete actions and retain established command implementations where present.
EXPLICIT={'finger':'raises a middle finger','shake':'shakes their head','yes':'nods in agreement','no':'shakes their head in disagreement','thank':'offers thanks','welcome':'offers a warm welcome','comfort':'offers a comforting gesture','lookdown':'looks down','lookaway':'looks away','calmly':'takes a steadying breath','restlessly':'shifts restlessly','reverie':'loses themself in a moment of reverie','ponderously':'considers the matter at length','grit':'grits their teeth','purse':'purses their lips','interlace':'interlaces their fingers','emanate':'holds a quiet, composed pose','radiate':'offers a bright smile','wag':'wags a finger','warm':'rubs their hands together','zip':'makes a quick, playful gesture'}
def conjugate(verb):
    if verb in EXPLICIT:return EXPLICIT[verb]
    if verb.endswith('y') and verb[-2] not in 'aeiou':return verb[:-1]+'ies'
    return verb+('es' if verb.endswith(('s','sh','ch','x','o')) else 's')
EMOTES={verb:conjugate(verb) for verb in VERBS}
async def perform(c,w,args,verb):
    target=c.location.get_character_by_name(args) or c.location.get_mob_by_name(args) if args else None
    if args and not target:
        await c.send('No visible target by that name. Use emote for a custom action.');return True
    await c.location.broadcast(f'{c.name} {EMOTES[verb]}'+(f' toward {target.name}' if target else '')+'.')
    return True
async def catalog(c,w,args):
    await c.send('Social actions (optional visible target):\n'+', '.join(sorted(EMOTES))+'\nEMOTE <your action> describes a custom action.');return True
