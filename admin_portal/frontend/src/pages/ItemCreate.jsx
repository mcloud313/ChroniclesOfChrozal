import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api';

function ItemCreate() {
    const navigate = useNavigate();
    const [item, setItem] = useState({
        name: '',
        description: 'An item.',
        item_type: 'MISC',
        subtype: '',
        value: 0,
        weight: 0.0,
        max_stack: 1,
        equip_slot: '',
        stats: {},
        flags: [],
        damage: null,
        armor: null,
        consumable_effect: null
    });

    const handleSubmit = async (e) => {
        e.preventDefault();
        try {
            const response = await api.post('/items', item);
            alert('Item created successfully.');
            navigate(`/items/${response.data.id}`);
        } catch (error) {
            console.error('Error creating item:', error);
            alert('Failed to create item');
        }
    };

    return (
        <div className="item-create">
            <h2>Create New Item Template</h2>
            <form onSubmit={handleSubmit}>
            <label>
                Name:
                <input 
                    type="text"
                    value={item.name}
                    onChange={(e) => setItem({...item, name: e.target.value})}
                    required
                    />
            </label>

            <label>
                Description:
                <textarea
                value={item.description}
                onChange={(e) => setItem({...item, description: e.target.value})}
                rows={3}
                />
            </label>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <label>
                    Item Type:
                    <select
                    value={item.item_type}
                    onChange={(e) => setItem({...item, item_type: e.target.value})}
                    >
                        <option value="WEAPON">Weapon</option>
                        <option value="RANGED_WEAPON">Ranged Weapon</option>
                        <option value="TWO_HANDED_WEAPON">Two-Handed Weapon</option>
                        <option value="ARMOR">Armor</option>
                        <option value="CONSUMABLE">Consumable</option>
                        <option value="QUEST_ITEM">Quest Item</option>
                        <option value="MISC">Miscellaneous</option>
                    </select>
                </label>

                <label>
                    Subtype:
                    <input
                    type="text"
                    value={item.subtype}
                    onChange={(e) => setItem({...item, subtype: e.target.value})}
                    placeholder="sword, potion, etc."
                    />
                </label>

                <label>
                    Value:
                    <input
                    type="number"
                    value={item.value}
                    onChange={(e) => setItem({...item, value: parseInt(e.target.value)})}
                    min="0"
                    />
                </label>

                <label>
                    Weight:
                    <input
                    type="number"
                    step="0.1"
                    value={item.weight}
                    onChange={(e) => setItem({...item, weight: parseFloat(e.target.value)})}
                    min="0"
                    />
                </label>

                <label>
                    Max Stack:
                    <input
                    type="number"
                    value={item.max_stack}
                    onChange={(e) => setItem({...item, max_stack: parseInt(e.target.value)})}
                    min="1"
                    />
                </label>

                <label>
                    Equip Slot:
                    <select
                    value={item.equip_slot}
                    onChange={(e) => setItem({...item, equip_slot: e.target.value})}
                    >
                        <option value="">None</option>
                        <option value="head">Head</option>
                        <option value="body">Body</option>
                        <option value="hands">Hands</option>
                        <option value="legs">Legs</option>
                        <option value="feet">Feet</option>
                        <option value="main_hand">Main Hand</option>
                        <option value="off_hand">Off Hand</option>
                        <option value="both_hands">Both Hands</option>
                        <option value="neck">Neck</option>
                        <option value="finger">Finger</option>
                    </select>
                </label>
            </div>

            <button type="submit">Create Item</button>
            <button type="button" onClick={() => navigate('/items')}>Cancel</button>
            </form>
        </div>
    );
}

export default ItemCreate;