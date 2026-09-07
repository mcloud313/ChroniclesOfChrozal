"""Authored, race-specific physical descriptions without invented personality."""
from game.definitions.traits import get_default_traits
from game import utils

def describe(data):
    race=data.get('race_name','Chrozalin')
    traits={**get_default_traits(race),**data.get('description_traits',{})}
    def value(key):return str(traits.get(key,'')).strip().lower()
    def present(text):return text and not text.startswith(('none','no ','clean-shaven'))
    subj,_,poss,_,has=utils.get_pronouns(data.get('sex','They/Them'))
    name=data.get('first_name','A traveler')
    sentences=[f"You see {name}, a {race}."]
    if value('Height'):sentences.append(f"{subj} {utils.get_pronouns(data.get('sex','They/Them'))[3]} {value('Height')} in stature, with a {value('Build') or 'balanced'} build.")
    features=[]
    handled={'Height','Build','Hair Style','Hair Color','Beard Style','Fur Color','Fur Pattern'}
    if present(value('Fur Color')):
        features.append(f"{value('Fur Color')} fur"+(f" with {value('Fur Pattern')} markings" if present(value('Fur Pattern')) else ''))
    hair=value('Hair Style')
    if hair.startswith(('bald','clean-shaven')):features.append('a shaven head' if hair!='bald' else 'a bald head')
    elif present(hair):features.append(' '.join(filter(None,[hair,value('Hair Color'),'hair'])))
    if present(value('Beard Style')):features.append(f"a {value('Beard Style')} beard")
    # Every race-specific trait participates, including scales, horns, tails and shells.
    nouns={'Skin Tone':'skin','Eye Color':'eyes','Ear Shape':'ears','Nose Type':'nose','Head Shape':'head','Shell Color':'shell','Tail Type':'tail','Skin Pattern':'skin markings'}
    for key in traits:
        if key in handled or not present(value(key)):continue
        noun=nouns.get(key,key.lower())
        features.append(f'{value(key)} {noun}')
    if features:sentences.append(f'{subj} {has} '+', '.join(features[:-1])+(' and ' if len(features)>1 else '')+features[-1]+'.')
    return ' '.join(sentences)
